"""
Session — the stateful engine API behind the TUI/CLI.

One `Session` holds a persistent KB graph + the firing journal, and exposes the things a
user does: assert CNL, ask questions, load a `.cnl` file, list facts, check consistency,
and explain a derivation. The UI (`repl.py`, or a future rich front-end) is a thin driver
over this — no engine logic lives in the UI.

The KB is LAZY (docs/coreference_design.md): asserting a line records facts and runs the
domain/universal reasoning, but it does NOT eagerly coref same-named mentions or detect
contradictions. Those are PULLED on demand by a query (`submit` of a question) or a
consistency read (`contradictions`), which seed `<demand>` tokens naming the entities to
resolve. A rule turns each demand into a coref `<call>` (a materialized tool call,
dispatch.py) which the ENGINE services inline (the `coref_walk.coref_request_handler` passed to
`run` as `tools`), running selective coreference that
links an entity's mentions only if reasoning stays consistent (two genuinely distinct
`Paul`s stay separate — vision §3 disambiguation). The genuinely ambiguous residue (a
consistent link whose identity is underdetermined) is referred to the user through an
optional `Oracle` (the ask-user tool, `interaction.py`); with no oracle, a consistent link
is kept.

The pipeline per asserted line: tokenize -> recognition forms (facts + native rules +
constraint declarations) -> graded rules -> strip surface -> derive (domain + universal +
`same_as` propagation, to a fixpoint). Coreference and detection are deferred to the
demand-driven read paths.

RECOGNITION REPORTING (the key UX fix). A line that matches no form produces no canonical
*content*, and is reported as unrecognized rather than silently doing nothing. The signal
is "did this line add a content relation?" — NOT "did any rule fire", because the grammar's
greedy 4-word loose-imperative form fires on arbitrary text (a known weakness). Content =
the recognition forms' meaningful RHS predicates, excluding surface scaffolding and the
speculative loose annotations. KNOWN v1 limit: re-asserting an already-known fact adds no
content and is therefore also reported unrecognized; refine when it bites.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ugm.cnl.authoring import (
    DEGREE_CNL, FACT_FORMS, RULE_SOURCE_FORMS,
    degree_grammar_forms, expand_loose_from_graph, expand_rules, graded_rules,
    plural_universal_forms, verb_neg_forms,
)
from ugm.coref_walk import coref_request_handler
from ugm.demand import DEMAND, DEMAND_COREF, seed_demand
from .driver import Phase, drive
from .interaction import Oracle, disambiguation_resolver
from ugm.cnl.forms import (
    DEFAULT_ARTICLES, FORM_RULES, WH, declared_definites, declared_determiners,
    declared_prepositions,
    declared_pronouns, declared_relations, declared_verbs, expand_pronouns_text, expand_universals,
    form_keywords, nary_forms, nary_question_forms, normalize_lexical, normalize_surface,
    relation_forms, subject_name, SCAFFOLD_PREDS, SURFACE_TAGS, surface_forms, tokenize,
)
from ugm.cnl.query import QUESTION_FORMS, ask, ask_goal, recognize
from ugm.lowering import run_bank
from ugm.cnl.rule_graph import (
    CONSTRAINT_FORMS, contradictions, expand_relation_properties, rules_in_graph,
)
from ugm.cnl.surface import explain
from ugm.cnl.universal import entailed_negation_rules, UNIVERSAL_RULES, same_as_rules
from ugm.world_model import Graph

# Every recognition form: facts + native rules/lexicon/loose + constraint declarations.
RECOGNITION_FORMS = FORM_RULES + FACT_FORMS + RULE_SOURCE_FORMS + CONSTRAINT_FORMS

# The MEANINGFUL (semantic) predicates the forms emit — what a user thinks of as facts.
# Curated, NOT auto-derived: the forms also emit a lot of rule-fold/tagging scaffolding
# (k_pred, rl_lhs, is_kw, in_rule, …) that is NOT content. Recognition of a *rule* line is
# detected separately, by the reflected-rule count growing (see `_assert`). Extend this set
# as the grammar grows (e.g. when n-ary / generic-binary forms land).
CONTENT_PREDS = {
    "is_a", "is", "wants", "in", "has",          # facts
    "every_is_a",                                # universal law ("every X is a Y")
    "is_unique",                                 # explicit single identity ("X is one thing")
    "rel_property", "disjoint_from",             # constraint declarations
    "before", "target", "type",                  # ordering / goals
    "subj", "obj",                               # n-ary event positional roles; the prepositional
}                                                # role predicates are added per declared preposition
# Surface + rule-fragment scaffolding that must never appear as a displayed fact's
# subject/object (rule-source builds k_*/in_rule/rl_* fragments in the graph).
_SCAFFOLD = {"next", "first", "u_verb", "u_adj", "u_adverb", "in_rule",
             "k_pred", "k_subj", "k_obj", "k_adv", "<topic>"}


# The default degree declarations as (adverb, value-string) pairs, parsed from the canonical
# CNL data (DEGREE_CNL). Seeded into each Session's KB so the graded scale lives there as facts.
_DEFAULT_DEGREES = [(ln.split()[0], ln.split()[-1])
                    for ln in DEGREE_CNL.splitlines() if ln.strip()]


# Coreference df cap (vision §14 metareasoning, content-blind): a name borne by more than this many
# nodes is a STOPWORD — a relation predicate or category word, not a specific entity — so resolving
# its O(k²) mention pairs is pointless and can hang. Structural (a count), never meaning.
COREF_DF_CAP = 24


def _is_rule_line(line: str) -> bool:
    """Is `line` a universal RULE (`if BODY then HEAD`, or the native `HEAD when BODY`)? A
    content-blind keyword test: its pronouns are bound variables, not discourse anaphora, so the
    assert path skips pronoun resolution and subject tracking for it."""
    toks = line.lower().split()
    return (bool(toks) and toks[0] == "if" and "then" in toks) or "when" in toks


def _queried_names(q: dict) -> list[str]:
    """The entity names a recognized query names (for demand-driven coreference). Binary: the
    subject + object; n-ary: the known role values (the `<wh>` slot and the verb are not
    entities)."""
    if q.get("qtype") == "nary":
        return [v for v in q.get("roles", {}).values() if v != WH]
    return [q.get("s"), q.get("o")]


@dataclass
class LineResult:
    """What happened to one submitted line."""
    line: str
    recognized: bool
    is_question: bool = False
    answer: list[str] = field(default_factory=list)
    new_facts: list[str] = field(default_factory=list)
    contradictions: list[dict] = field(default_factory=list)
    error: str | None = None


class Session:
    def __init__(self, oracle: Oracle | None = None) -> None:
        self.kb = Graph()
        self.journal: list = []
        self.rules: list = []                 # executable domain rules reflected from the KB
        self._unparsed: list[str] = []        # session metadata, NOT KB content (canonicalize
                                              # would mangle in-graph markers — a known crudeness)
        self._last_subject: str | None = None  # discourse subject of the last line; a following
                                              # pronoun resolves to it (§14 recency policy, Tier 3b)
        # Optional human-in-the-loop oracle (interaction.py). When set, a coreference link
        # that reasoning leaves CONSISTENT-but-ambiguous is referred to the user; with no
        # oracle, such a link is kept (the headless default).
        self._oracle = oracle
        # The degree scale lives in the KB as DATA (vision §13): seed the default declarations
        # (`very is 0.8`, ...) as facts. The graded write rules + rule-grammar forms are then
        # generated from these (graded_rules / degree_grammar_forms), and a user can add or
        # override a degree just by asserting it. Nothing about the scale is hardcoded in the
        # rule layer — it is read back from these facts.
        for adverb, value in _DEFAULT_DEGREES:
            self.kb.add_relation(self.kb.add_node(adverb), "is", self.kb.add_node(value))

    # ------------------------------------------------------------------ reading
    def _content_relations(self) -> set[str]:
        g = self.kb
        # declared relations AND prepositions (n-ary role markers) are content too
        content = CONTENT_PREDS | declared_relations(g) | declared_prepositions(g)
        out: set[str] = set()
        for r in g.nodes():
            nm = g.name(r)
            if nm not in content:
                continue
            # skip provenance in-edges (a `proves` node points into this relation, vision §9)
            subj = next((n for n in g.into(r) if not g.is_inert(n)), None)
            obj = next(iter(g.out(r)), None)
            if subj is None or obj is None:
                continue
            sn, on = g.name(subj), g.name(obj)
            if sn in _SCAFFOLD or on in _SCAFFOLD:
                continue
            # A node whose NAME is a relation word (e.g. `before`) is also an ENTITY when
            # declared (`before is a relation`); reading that concept node as a relation
            # fabricates junk. A real relation instance points at an ENTITY object, never at
            # another relation node — so skip when the object is itself a relation predicate.
            if on in content:
                continue
            out.add(f"{sn} {nm} {on}")
        return out

    def facts(self) -> list[str]:
        """Canonical content relations 'subject predicate object'."""
        return sorted(self._content_relations())

    def contradictions(self) -> list[dict]:
        """Consistency ON DEMAND. A consistency read is a standing demand
        (`demand(<contradiction>)`, docs/coreference_design.md §2): it resolves coreference
        for every multiply-mentioned entity (so provably-distinct same-name mentions are
        disambiguated, vision §3) and then detects the contradictions that remain — those on
        a SINGLE entity (e.g. a self-loop, or an explicitly-identified individual). Bare
        repeated mentions never contradict; they are read as distinct witnesses."""
        self._check()
        return contradictions(self.kb)

    def unparsed(self) -> list[str]:
        """Lines no form recognized (no canonical content produced)."""
        return list(self._unparsed)

    def _unique_names(self) -> set[str]:
        """Names declared an EXPLICIT SINGLE IDENTITY (`X is one thing`, `X is the same as Y`, or a
        DEFINITE reference `the X` under an opt-in `the is a definite`) -> `X is_unique <yes>`. All
        mentions of such a name are ONE individual, so `_merge_unique` collapses them to one node,
        and a user-stated single entity's incompatible facts surface as a real contradiction
        instead of being read as distinct witnesses (the pure-§3 default for a BARE mention)."""
        g = self.kb
        out: set[str] = set()
        for r in g.nodes_named("is_unique"):
            subj = next((n for n in g.into(r) if not g.is_inert(n)), None)
            if subj is not None:
                out.add(g.name(subj))
        return out

    def _open_predicates(self) -> frozenset[str]:
        """The concepts/predicates declared OPEN-world — the OWA opt-in over the CWA default
        (decision-cwa-default): for these, an underivable goal is `unknown` (absence != false) and
        triggers evidence-gathering, rather than the defeasible `no`. Empty for now: the surface
        opt-in (`X is open world`, and the deontic-triggered "better check" escalation) is the
        follow-up; the default is closed-world so an agent decides on the best of current knowledge."""
        return frozenset()

    def _force_coref_unique(self) -> None:
        """Link every mention of a single-identity name (`_unique_names`) with an ADDITIVE `same_as`
        (never a merge) — the §5-preserving replacement for the old destructive `_merge_unique`. The
        user asserted these mentions are ONE individual, so they are force-coreferenced through the
        SAME demand/dispatcher handshake the submit query uses (`_resolve_coref(force_names=...)`): a
        `<demand>` is seeded, the rule `DEMAND_COREF` turns it into a coref `<call>`, and the engine
        services it in FORCE mode (commit every pair unconditionally, no clash-check, no retraction) —
        the coref DECISION is a rule firing on a token, not a Python call. Their facts then COMPOSE
        across the link via `same_as` propagation, so a name known to denote one individual with
        incompatible facts (`ice is a solid` + `ice is a liquid`) surfaces as a REAL contradiction —
        WITHOUT deleting a single fact edge (the merge cut them). Bounded to the declared unique names;
        idempotent (already-linked pairs are skipped)."""
        unique = self._unique_names()
        if unique:
            self._resolve_coref(list(unique), force_names=unique)

    def explain(self, s: str, p: str, o: str) -> list[str]:
        return explain(self.kb, self.journal, self.rules + UNIVERSAL_RULES, s, p, o)

    # ------------------------------------------------------------------ writing
    def _surface(self, forms: list) -> tuple[set, list]:
        """`(subject_keywords, strata)` for surface normalization over `forms`. The grammar's
        function words are DATA (bound-literals in `forms` + declared relation/verb/prep words);
        `surface_forms` builds the determiner/decomposition banks from them + the declared
        determiner set. `subject_keywords` (function words + determiners/articles) is what
        `subject_name` skips to find the discourse subject."""
        dets = declared_determiners(self.kb)
        keywords = (form_keywords(forms) | declared_relations(self.kb)
                    | declared_verbs(self.kb) | declared_prepositions(self.kb))
        strata = surface_forms(keywords, determiners=dets, definites=declared_definites(self.kb))
        return keywords | dets | set(DEFAULT_ARTICLES), strata

    def _reason_bank(self, g: Graph) -> list:
        """The reasoning bank, reflected from the graph: the domain rules + universals + the
        `same_as` propagation that composes facts across coreference links. Propagate only the
        KNOWN content predicates (not a structural guess — an entity that is a subject in one
        fact and an object in another would be misread as a predicate, and the junk rules blow
        up against `same_as` transitivity).

        `decided_negation=False` (matching the answer path, `submit`): a closed-world `is not P`
        stays a plain NAC here too. The forward `_derive` runs via `run_rules` (no retraction pass),
        so the aggressive `decide` completion — which relies on defeat-by-retract to repair its
        over-assertion — would over-assert `is_not P` with NO repair. Closed-world negation is
        ANSWERED backward (`ask_goal`, demand-completion); the forward compose step only needs the
        NAC, so this both removes that latent over-assertion and keeps the two paths consistent."""
        self.rules = (expand_rules(g, decided_negation=False)
                      + expand_loose_from_graph(g) + expand_universals(g))
        prop = same_as_rules(sorted(CONTENT_PREDS | declared_relations(g)
                                    | declared_prepositions(g)))
        return self.rules + UNIVERSAL_RULES + prop

    def _derive(self, seeds: list[str] | None = None) -> None:
        """Run the REASONING plan (no detection) through the generic driver: a stratified
        phase of the domain rules + universals + `same_as` propagation. Detection is NOT
        here — it is pulled on demand (`contradictions`), because under selective coreference
        detection must run only AFTER coreference has been resolved for the queried/checked
        entities, and stratifying detection across several constraints would falsely look
        like a negation cycle.

        `seeds` is the initial change frontier for semi-naive matching: an incremental assert
        seeds on the new line's nodes so each step restricts to matches touching the delta
        (matching itself is unbounded — the hop-radius neighbourhood is retired, walkers §6).
        With `seeds=None` (the default — e.g. the coref read path) it reasons over the graph."""
        plan = [Phase("reason", self._reason_bank, stratified=True)]
        drive(self.kb, plan, seeds=seeds)

    # ---- demand-driven coreference (selective; the lazy read path) ----------
    def _resolve_coref(self, names, *, force_names=()) -> None:
        """Selective coreference for `names`, ON DEMAND and via the dispatcher handshake —
        no hardcoded coref call. Seed a `<demand>` naming each entity; a rule (`DEMAND_COREF`)
        turns it into a coref `<call>`, which the ENGINE services inline (the `coref` handler
        passed as `tools`) — linking an entity's mentions only where reasoning stays consistent
        (provably-distinct mentions are rejected; the ambiguous residue is referred to the
        oracle if one is set). Then re-derive so facts compose across the kept links.

        `force_names` (a subset declared an explicit single identity, `_unique_names`) are
        resolved with `force=True`: their mentions are linked unconditionally so a user-stated
        single entity's incompatibilities surface as contradictions. The force set is DATA
        (the `is_unique` facts), threaded to the handler — still no hardcoded coref decision.

        A name borne by MANY nodes is a STOPWORD (vision §14 metareasoning — content-blind df):
        coreferencing it is O(k²) pairs + `same_as` saturation for no benefit (it is a relation
        predicate or a category word, not a specific entity to disambiguate). We skip any name whose
        mention count exceeds `COREF_DF_CAP`, which also makes the resolver robust to a mis-parsed
        query that lands a predicate in an entity slot (else it hangs). A count is structure, not
        meaning, so this stays on the right side of the content-blind line."""
        names = [n for n in dict.fromkeys(names)
                 if n and 1 < len(self.kb.nodes_named(n)) <= COREF_DF_CAP]
        if not names:
            return
        for nm in names:
            seed_demand(self.kb, nm, nm)          # name the entity in a demand (role-agnostic)
        resolver = disambiguation_resolver(self._oracle) if self._oracle else None
        handler = coref_request_handler(resolver, force_names=force_names)  # incident preds auto
        # ISA forward driver (Phase 0.5): the demand->coref-request rules mint a `<call> coref`,
        # serviced at run_bank's tool fixpoint; the handler runs the coref walk (also run_bank).
        run_bank(self.kb, DEMAND_COREF, tools={"coref": handler}, provenance=True)
        for d in list(self.kb.nodes_named(DEMAND)):   # GC spent demand tokens (calls consumed)
            self.kb.remove_node(d)
        self.kb.gc_disconnected()
        self._derive()                            # compose across the kept `same_as` links

    def _check(self) -> None:
        """The consistency demand: detect the contradictions present over the graph AS-IS.

        Under pure §3 disambiguation (the chosen semantics) bare repeated mentions are
        DISTINCT witnesses, so they cannot contradict each other — a `same-name` clash means
        two different things, not an inconsistency. So a consistency check does NOT coref
        bare repeats globally (that would also be the dense `same_as` saturation the engine
        can't yet do fast): it detects the contradictions that remain over distinct witnesses.

        The ONE exception is an EXPLICIT SINGLE IDENTITY (`X is one thing`/`the X` -> `is_unique`):
        the user has asserted those mentions are one entity, so they are MERGED (`_merge_unique`,
        bounded to the declared names) BEFORE detection, and their composed facts trip the
        constraint schemas. That is how a genuine one-entity mistake is caught under pure §3.
        Coreference of ordinary queried entities happens on the query path (`submit`); a kept link
        there persists and is detected here too."""
        self._clear_detection()
        self._force_coref_unique()                # single identities: additive `same_as` (no merge)
        self._derive()                            # compose (rules + `same_as` propagation) post-link
        drive(self.kb,
              [Phase("detect", lambda g: rules_in_graph(expand_relation_properties(g)))])

    def submit(self, line: str) -> LineResult:
        """Process one line: answer it if it is a question, else assert it."""
        line = line.strip()
        if not line:
            return LineResult(line, recognized=True)
        try:
            # KB-derived question forms: an n-ary question (`who gives book to bob`) is only
            # recognizable once the verb is declared. A binary relational yes/no (`does the dog eat
            # the squirrel`) needs no per-relation form — the generic `ask.yesno.does` in
            # QUESTION_FORMS binds the predicate freely (gated by the `does` marker).
            qforms = nary_question_forms(self.kb)
            # Same surface normalization as the assert path, over the question grammar, so a
            # determiner / multi-word entity in a question resolves to the KB's names. A pronoun in
            # the read-only question is expanded in the query TEXT to the discourse subject (a
            # macro expansion — the question matches the KB by name; the assert path resolves
            # pronouns as graph coreference, never by text).
            _, qstrata = self._surface(list(QUESTION_FORMS) + list(qforms))
            qline = expand_pronouns_text(line, declared_pronouns(self.kb), self._last_subject)
            q = recognize(qline, qforms, strata=qstrata)
            if q is not None:
                # Pull coreference for the queried entities first (the query is the demand),
                # so a same-name fact composes across kept links / a wrong link is rejected.
                # Declared single identities are forced (kept unconditionally) AND always
                # resolved — even when not the queried name — so a fact stated under one name of
                # a cross-name identity (`clark is the same as superman`) composes when the
                # OTHER name is asked. Declared identities are few, so this stays bounded.
                unique = self._unique_names()
                self._resolve_coref(list(unique) + _queried_names(q), force_names=unique)
                if q["qtype"] in ("yesno", "who"):
                    # BACKWARD ANSWERING (decision-attrgraph-rehost Phase B): demand just the
                    # question's goal through the ISA machine (`ask_goal`/`GoalSolver`) rather than
                    # matching a forward-materialized graph. Coref was composed FORWARD by `_derive`
                    # (its `_reason_bank` carries the `same_as` propagation), so the facts are already
                    # spread across the wired mentions before this reads them — `ask_goal` needs no
                    # coref DECLARATION of its own (coref-following is gated on those rules being in the
                    # bank; here it is coref-blind and correct). `decided_negation=False` keeps a
                    # closed-world `is not P` a NAC the solver completes on demand. CWA-DEFAULT
                    # (decision-cwa-default): an underivable goal is a defeasible `no` (act on the
                    # best of current knowledge), UNLESS its concept is declared OPEN — then absence
                    # is not false (`unknown` -> gather evidence). Entailed negation (disjointness ->
                    # `is_not`) gives a HARD `no`; the hard-vs-assumed KIND for metareasoning is TODO.
                    goal_rules = (expand_rules(self.kb, decided_negation=False)
                                  + expand_loose_from_graph(self.kb)
                                  + expand_universals(self.kb)
                                  + entailed_negation_rules(self.kb) + UNIVERSAL_RULES)
                    answer = list(ask_goal(self.kb, qline, goal_rules,
                                           open_preds=self._open_predicates(),
                                           extra_forms=qforms, strata=qstrata))
                else:
                    # n-ary (reified event match) / why (provenance trace) stay on the forward
                    # answerer — reasoning shapes not yet on the goal path.
                    answer = list(ask(self.kb, qline, journal=self.journal,
                                      rules=self.rules + UNIVERSAL_RULES, extra_forms=qforms,
                                      strata=qstrata))
                # A question's subject is a topic too — a following pronoun resolves to it.
                if q.get("s"):
                    self._last_subject = q["s"]
                return LineResult(line, recognized=True, is_question=True, answer=answer)
            return self._assert(line)
        except Exception as e:                       # surface engine errors, don't crash the UI
            return LineResult(line, recognized=False, error=f"{type(e).__name__}: {e}")

    def _strip_surface(self) -> None:
        """Remove the surface token chain (`next`/`first`/`<sentence>`) once a line has been
        recognized, keeping only canonical content + the rule fragments. This is essential
        for an incremental session: the demand-driven coreference links same-named nodes, and
        the surface KEYWORD tokens (`a`, determiners — not predicates, so unprotected) would
        otherwise link across sentences and tangle the chains. Stripping the scaffolding
        leaves a clean content graph for coreference + reasoning. (Cost: the surface
        provenance for deep `:why` explanations is not retained across lines.)"""
        g = self.kb
        for nm in ("next", "first", *SURFACE_TAGS):   # chain + surface-normalization tags
            for r in list(g.nodes_named(nm)):
                g.remove_node(r)
        for a in list(g.nodes_named("<sentence>")):
            g.remove_node(a)
        g.gc_disconnected()

    def _clear_detection(self) -> None:
        """Remove prior `<contradiction>`/`about`/`violates` markers. They are re-derived
        from scratch every `_check()`, and leaving them in the graph would let coreference
        link the (unprotected) `about`/`violates` relation nodes across lines and tangle the
        markers together. Clearing first keeps each check's detection clean."""
        g = self.kb
        for nm in ("<contradiction>", "about", "violates"):
            for n in list(g.nodes_named(nm)):
                g.remove_node(n)
        g.gc_disconnected()

    def _assert(self, line: str) -> LineResult:
        # The KB is LAZY: asserting records facts and runs domain/universal reasoning, but it
        # does NOT coref or detect — those are pulled by the read paths (`submit` of a question
        # resolves coref for the queried entities; `contradictions` resolves coref for all and
        # detects). KNOWN REMAINING SEAM: this body is still a short hardcoded Python SEQUENCE
        # (tokenize -> run(forms) -> run(graded) -> strip -> derive). Fully dissolving it into
        # one `drive(plan)` needs forms/graded as Phases + the per-sentence SEED (re-running
        # forms over old chains misfires) + `_strip_surface` as a step + the recognized-content
        # diff moved out. Deferred deliberately. See docs/handoff_redesign.md "De-hardcoding".
        before = self._content_relations()
        rules_before = len(self.rules)
        # `are` -> `is` (copula morphology, a mechanical lexical step, §8) so `they are young`
        # parses by the one copula grammar. Then resolve a pronoun to the discourse subject
        # before tokenizing (§14 recency policy, Tier 3b): "it is happy" after "the bald eagle is a
        # bird" -> "eagle is happy". EXCEPT in a universal RULE (`if ... then ...`): there the
        # pronouns (`someone`/`they`/`it`) are BOUND VARIABLES, not anaphora
        # (decision_quantification_coreference), so they must NOT resolve to the last subject —
        # `expand_rules` maps them to rule variables instead. A rule line is detected by its
        # keywords (content-blind, like the §14 recency policy itself).
        line = normalize_lexical(line)
        is_rule = _is_rule_line(line)
        if not is_rule:
            line = expand_pronouns_text(line, declared_pronouns(self.kb), self._last_subject)
        anchor = tokenize(self.kb, line)
        # Recognition = the static forms (incl. the `X of C` context-qualifier forms) + a
        # generated form per already-declared relation/verb/degree-adverb/auxiliary/variable-noun (so
        # `monday before tuesday` parses once `before is a relation`, `alice gives book to bob` once
        # `gives is a verb`, a graded condition once the adverb's degree is declared, `X doth not V Y`
        # once `doth is an auxiliary`, and `Cold critters are kind` once `critters is a variable`).
        forms = (RECOGNITION_FORMS + relation_forms(self.kb) + nary_forms(self.kb)
                 + degree_grammar_forms(self.kb) + verb_neg_forms(self.kb)
                 + plural_universal_forms(self.kb))
        # Surface normalization (Tier 3, ALL rules — forms.surface_forms): strip determiners,
        # DECOMPOSE multi-word noun phrases into head + attribute ("the bald eagle" -> `eagle`,
        # `eagle is bald`), and link a pronoun to the discourse subject (`<topic>` control node)
        # by `same_as`. Runs BEFORE the content forms so they see a normalized chain.
        keywords, strata = self._surface(forms)
        normalize_surface(self.kb, anchor, strata)
        # Decomposition ("the bald eagle" -> `eagle is bald`) is NORMALIZATION, not clause
        # recognition: measure recognition AFTER it, so a bare NP or gibberish ("glorp the flarn
        # wibbit") is not "recognized" on the strength of an attribute alone — a real CLAUSE
        # (copula / relation / is_a) must fire. `before` still drives `new_facts` (attributes are
        # genuine new facts to report).
        after_norm = self._content_relations()
        subj = subject_name(self.kb, anchor, keywords)   # this line's discourse subject
        # Rule-source recognition on the ISA forward driver (`run_bank`) — the "one engine" move
        # (Phase 0.5). Whole-graph is correct here: `normalize_surface` already stripped every PRIOR
        # sentence's `next`/`first` chain, so the forms only see THIS sentence (no seed frontier needed
        # — the semi-naive `<fresh>` SEED was a red herring, finding-session480-not-phase41). The former
        # "double NAC" was a `fired`-keying bug: the `forms` list has duplicate rule keys (default forms
        # + per-KB regenerated defaults), which `run_bank` now suppresses per (rule.key, sig) like
        # `rewriter`. run_bank returns a count (recognition firings are not surfaced in `explain`), so
        # nothing is added to the journal.
        run_bank(self.kb, forms)
        # graded uses the chain; the degree VALUES come from the KB (graded_rules reads them). On the
        # ISA forward Machine (`run_bank`, propagate -> EMIT) — the "one engine" move (Phase 0.4); it
        # writes embedding degrees (not relation firings), so nothing is added to the explain journal.
        run_bank(self.kb, graded_rules(self.kb))
        self._strip_surface()                         # drop surface (keep canonical content)
        # Reasoning runs WHOLE-GRAPH (no seed) deliberately: law/universal rules match by NAME
        # (`?u is_a person`), which is NON-LOCAL — the law mention and a fact mention are
        # DISTINCT, disconnected nodes under the lazy no-coref model. A per-line seed would make
        # SEMI-NAIVE restrict each step to matches touching the new line's delta and miss the
        # name-connected law (matching scope itself is unbounded now — seed-from-ground via the
        # index, walkers §6); reseeding per line is only safe once mentions are coref-connected.
        # Link single-identity mentions with an additive `same_as` (definiteness / `is one thing` /
        # `same as`) BEFORE deriving, so a name's facts split across mentions compose across the link
        # (and, with `same_as` transitivity, join a cross-name identity too). Additive — no fact edge
        # is deleted (the old merge cut them). Bounded to the declared unique names; idempotent.
        self._force_coref_unique()
        self._derive()                                # reflects rules into self.rules, no coref/detect
        # Recognized iff the line added a semantic FACT/constraint or a RULE (not just
        # scaffolding or a speculative loose `<use>`). KNOWN limit: re-asserting a fact
        # already known adds nothing and is reported unrecognized.
        recognized = (len(self._content_relations()) > len(after_norm)
                      or len(self.rules) > rules_before)
        if recognized and subj is not None and not is_rule:
            self._last_subject = subj             # this line's subject anchors the next pronoun
            # (a rule's subject is `someone`/a variable — never a discourse antecedent)
        if not recognized:
            self._unparsed.append(line)
        return LineResult(
            line, recognized=recognized,
            new_facts=sorted(self._content_relations() - before),
        )

    def load_text(self, text: str) -> list[LineResult]:
        """Load a multi-line CNL corpus (lines starting with '#' are comments)."""
        results = []
        for raw in text.splitlines():
            s = raw.strip()
            if s and not s.startswith("#"):
                results.append(self.submit(s))
        return results

    def load_file(self, path: str | Path) -> list[LineResult]:
        return self.load_text(Path(path).read_text(encoding="utf-8"))
