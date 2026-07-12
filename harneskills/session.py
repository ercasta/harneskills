"""
Session — the stateful harness API behind the TUI/CLI, over UGM's Session layer.

Post repo-split (2026-07-12) the multi-turn driver lives in UGM (`ugm/intake.py` §8): one
utterance routes *itself* to fact / question / rule / rule-disable / focus / unrecognized by
which recognition FORMS fire (no caller-side classifier), composing the CNL surface across
turns and streaming an `Event` per step boundary. The old harness `Session` hand-rolled its
own lazy coreference + contradiction detection on the now-retired `demand`/`coref_walk`
modules; that machinery is GONE. This `Session` is a THIN stateful wrapper over
`ugm.ingest` / `ugm.converse` — it holds the persistent KB graph + accumulated rules and the
optional human oracle, and translates a UGM `Outcome` into the harness's `LineResult`. No
reasoning lives here; it is another consumer sitting above UGM's stance line (architecture §8).

  submit(line)  -> ugm.ingest(kb, rules, line)  -> Outcome  -> LineResult

Coreference is now DECLARED rules in UGM (`same_name_coref_rules`, injected by the CNL load
path), not a Python demand walk. The human-in-the-loop escalation is UGM's mid-chain ask: a
derivation blocked on an OPEN premise yields an `ask` event, which this Session answers through
the injected `Oracle` (interaction.py) — the §8 calculator-is-a-person pattern, unchanged.

RECOGNITION REPORTING. A line that produces no content fact / rule / question routes to the
`unrecognized` outcome (UGM's habitability signal) and is reported as such rather than
silently ignored. `new_facts` is the content-relation delta this line added to the KB.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ugm.intake import ingest, converse, Outcome, Event
from ugm.cnl.authoring import (
    DEGREE_CNL, FACT_FORMS, RULE_SOURCE_FORMS,
    expand_rules, expand_loose_from_graph, _coref_propagation,
)
from ugm.cnl.forms import FORM_RULES, declared_prepositions, declared_relations
from ugm.cnl.rule_graph import (
    CONSTRAINT_FORMS, contradictions as _read_contradictions,
    expand_relation_properties, rules_in_graph,
)
from ugm.cnl.surface import explain as _explain
from ugm.cnl.universal import UNIVERSAL_RULES, same_name_coref_rules
from ugm.cnl.authoring import run_rules
from ugm.lowering import run_bank
from ugm.world_model import Graph
from .interaction import Oracle

# Kept for back-compat with earlier callers: every recognition form (facts + native rules +
# constraint declarations). UGM's intake recognizes these internally now; exposed here only so
# a consumer that inspected `RECOGNITION_FORMS` still finds it.
RECOGNITION_FORMS = FORM_RULES + FACT_FORMS + RULE_SOURCE_FORMS + CONSTRAINT_FORMS

# The MEANINGFUL (semantic) predicates the forms emit — what a user thinks of as facts. Curated,
# NOT auto-derived: the forms also emit rule-fold / tagging scaffolding (k_pred, in_rule, is_kw, …)
# that is NOT content. Extend as the grammar grows.
CONTENT_PREDS = {
    "is_a", "is", "wants", "in", "has",          # facts
    "every_is_a",                                # universal law ("every X is a Y")
    "is_unique",                                 # explicit single identity ("X is one thing")
    "rel_property", "disjoint_from",             # constraint declarations
    "before", "target", "type",                  # ordering / goals
    "subj", "obj",                               # n-ary event positional roles
}
# Surface + rule-fragment scaffolding that must never appear as a displayed fact's subject/object.
_SCAFFOLD = {"next", "first", "u_verb", "u_adj", "u_adverb", "in_rule",
             "k_pred", "k_subj", "k_obj", "k_adv", "<topic>", "<mention>"}

# The default degree declarations as (adverb, value-string) pairs, parsed from the canonical CNL
# data (DEGREE_CNL). Seeded into each Session's KB so the graded scale lives there as facts.
_DEFAULT_DEGREES = [(ln.split()[0], ln.split()[-1])
                    for ln in DEGREE_CNL.splitlines() if ln.strip()]


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
    """A persistent KB + accumulated rules driven by UGM's unified intake.

    `oracle` (interaction.py) answers UGM's mid-chain ask when a derivation needs an OPEN
    premise a human must supply; with no oracle, an unknown open goal stays unknown (the
    headless default). `attention` selects UGM's reasoning mode: "global" (whole KB) or
    "focus" (bounded attention to the current focus working set — the session-accretion fix).
    `policy` is an optional UGM `FirmwarePolicy` (CWA/OWA + cycle stance)."""

    def __init__(self, oracle: Oracle | None = None, *, policy=None,
                 attention: str = "global") -> None:
        self.kb = Graph()
        self.rules: list = []                 # executable domain rules, grown by rule utterances
        self.policy = policy
        self.attention = attention
        self._oracle = oracle
        self._unrecognized: list[str] = []
        # The degree scale lives in the KB as DATA (vision §13): seed the default declarations
        # (`very is 0.8`, …) as facts so graded rules/forms are generated from them.
        for adverb, value in _DEFAULT_DEGREES:
            self.kb.add_relation(self.kb.add_node(adverb), "is", self.kb.add_node(value))

    # ------------------------------------------------------------------ ask bridge
    def _ask_bridge(self):
        """Bridge the injected `Oracle` to UGM's `ask_user(subj, rel, obj) -> True/False/None`
        mid-chain gather. Absence of an oracle => no handler (an open goal stays unknown)."""
        if self._oracle is None:
            return None

        def ask(subj: str, rel: str, obj: str):
            answer = self._oracle(
                f"Is it true that {subj} {rel} {obj}?", ["yes", "no", "unknown"])
            a = (answer or "").strip().lower()
            if a.startswith("y"):
                return True
            if a.startswith("n"):
                return False
            return None
        return ask

    # ------------------------------------------------------------------ reading
    def _content_relations(self) -> set[str]:
        """The content facts as canonical `subject predicate object` strings. A relation's
        PREDICATE is read via `g.predicate` (post name-demotion a relation node carries no name —
        its predicate is the domain graded key), enumerated off each entity's `relations_from`
        cursor. Coref/marker scaffolding (`<mention>`, `<focus>`, `same_as` self-links) is filtered."""
        g = self.kb
        content = CONTENT_PREDS | declared_relations(g) | declared_prepositions(g)
        out: set[str] = set()
        for subj in g.nodes():
            sn = g.name(subj)
            if not sn or sn.startswith("<") or sn in _SCAFFOLD or g.is_inert(subj):
                continue
            for r, o in g.relations_from(subj):
                pred = g.predicate(r)
                if pred not in content:
                    continue
                on = g.name(o)
                # object must be a real ENTITY: not a marker, scaffolding, or a predicate word.
                if not on or on.startswith("<") or on in _SCAFFOLD or on in content:
                    continue
                out.add(f"{sn} {pred} {on}")
        return out

    def facts(self) -> list[str]:
        """Canonical content relations 'subject predicate object'."""
        return sorted(self._content_relations())

    def unparsed(self) -> list[str]:
        """Lines UGM's intake recognized as nothing (no fact / rule / question produced)."""
        return list(self._unrecognized)

    def explain(self, s: str, p: str, o: str) -> list[str]:
        """A derivation trace read from the in-graph support (UGM `surface.explain`)."""
        return _explain(self.kb, None, self.rules + list(UNIVERSAL_RULES), s, p, o)

    def contradictions(self) -> list[dict]:
        """Consistency as a guarded read. Runs the accumulated domain rules + universals to
        closure, then the relation-property / disjointness constraint rules (a later phase — a
        single stratified bank can't hold both reasoning and detection without looking like a
        negation cycle), then surfaces the `<contradiction>` markers. Detection only ADDS
        markers (UGM vision §5, monotone); `_read_contradictions` dedupes the guarded read."""
        self._clear_detection()
        reason = self.rules + list(UNIVERSAL_RULES)
        if reason:
            run_rules(self.kb, reason)                 # compose facts before detecting over them
        detect = rules_in_graph(expand_relation_properties(self.kb))
        if detect:
            run_bank(self.kb, detect)                  # non-stratified detection phase
        return _read_contradictions(self.kb)

    def _clear_detection(self) -> None:
        """Remove prior `<contradiction>`/`about`/`violates` markers so each check re-detects
        cleanly (they are re-derived from scratch every call)."""
        g = self.kb
        for nm in ("<contradiction>", "about", "violates"):
            for n in list(g.nodes_named(nm)):
                g.remove_node(n)
        g.gc_disconnected()

    def _reasoning_rules(self) -> list:
        """The standing reasoning bank, recomputed from the live graph — the same bundle
        `ugm.load_corpus` returns: graph-reflected rules (universal laws + rule-source) + loose
        annotations + declared same-name coreference + `same_as` propagation over the present
        content predicates. Recomputed per turn so a law/relation declared this session takes
        effect on the next question. Graph-derived, so it never double-counts a user `HEAD when`
        rule (those live only in the accumulator, `self.rules`)."""
        g = self.kb
        return (expand_rules(g) + expand_loose_from_graph(g)
                + same_name_coref_rules() + _coref_propagation(g))

    # ------------------------------------------------------------------ writing
    def submit(self, line: str) -> LineResult:
        """Process one line through UGM's unified intake: it routes itself to fact / question /
        rule / rule-disable / focus / unrecognized by which recognition forms fire. A question is
        answered against the standing reasoning bank + the accumulated user rules; a `HEAD when`
        utterance is appended to the user accumulator (recovered after `ingest` mutates in place)."""
        line = line.strip()
        if not line:
            return LineResult(line, recognized=True)
        before = self._content_relations()
        bank = self._reasoning_rules()
        combined = bank + self.rules                   # reasoning bank first, user rules after
        try:
            outcome = ingest(self.kb, combined, line, policy=self.policy,
                             ask_user=self._ask_bridge(), attention=self.attention)
        except Exception as e:                         # surface engine errors, don't crash the UI
            return LineResult(line, recognized=False, error=f"{type(e).__name__}: {e}")
        self.rules = combined[len(bank):]              # user rules (old + any newly appended)
        return self._to_result(line, outcome, before)

    def _to_result(self, line: str, outcome: Outcome, before: set[str]) -> LineResult:
        if outcome.kind == "answer":
            return LineResult(line, recognized=True, is_question=True,
                              answer=list(outcome.answer or []))
        if outcome.kind == "unrecognized":
            self._unrecognized.append(line)
            return LineResult(line, recognized=False)
        # fact / rule / rule-disable / focus — recognized; report any content-relation delta.
        return LineResult(line, recognized=True,
                          new_facts=sorted(self._content_relations() - before))

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
