# De-Pythonization — provenance-as-substrate and the reasoning/mechanism line

> **Status: DESIGN + steps 1, 1b, 2, 3 landed (2026-07-02, 178 tests green).** Done: the matcher is
> provenance-aware per rule (§2, `tests/test_provenance_matchable.py`); the `rewire` cut/link
> primitive + retraction-by-interposition (§4, `tests/test_rewire.py`); the cascade as meta-rules
> (§4, `retraction.RETRACT_RULES`, `tests/test_retract_rules.py`); **the whole `decide`
> completion/defeat stack is now rules** (§5, `decide.completion_rule` + `DEFEAT_SEED`, the
> `complete_tool`/`recheck`/`<decide>` machinery deleted; `tests/test_decide.py` rewritten). The
> rest below is design. Captures a decision taken with the user:
> *provenance stops being a hard engine carve-out and becomes matchable by a labelled
> meta-rule discipline*, which is the keystone that lets the truth-maintenance layer
> (retraction, completion-defeat) be expressed as **rules** instead of Python drivers. Read
> after `docs/vision.md`. Supersedes the "provenance is inert to the matcher" framing in
> `docs/attic/coreference_design.md` and the `decide.py` / `retraction.py` docstrings where
> they conflict.

## 0. The question that triggered this

While making `decide.solve` engine-driven, the user pushed on two things:

1. *"Why do we need **tools** to trigger **decisions**? Why isn't it in rules? Did we create a
   seam? If we start moving logic into Python we are doomed."*
2. *"I don't understand why provenance must be inert to the matcher. I think it belongs in
   rules too. If we need a third category of rules, fine — but we need strong motivation (in
   the end this categorization is only ours; even control nodes are managed by rules)."*

Both are correct. This doc records the resolution and the follow-on audit of every Python
module for reasoning-in-Python that should be rules.

## 1. The line the vision actually draws

The system has exactly **three kinds of Python**, and only three are legitimate:

- **Mechanism** — the stupid runner: graph storage, the matcher + semi-naive delta, the
  lexical index, the fixpoint loop, canonicalize (structural node-merge), GC, the `<call>`
  dispatcher. This is "the CPU." It is content-blind and fixed (§4/§6).
- **§8 opaque calculators (tools)** — a *very* small instruction set that operates ONLY on
  the opaque *content* of nodes: the tokenizer (raw string → token nodes), arithmetic on a
  node whose name is `"0.2"`, embedding dot-product / α-cut / propagation, an external
  service call. A tool never inspects graph *structure* for meaning and never rewrites (§8).
- **Rules** — everything else. All reasoning, all control flow, all orchestration. "The
  program." Facts, control tokens, goals, plans, coreference, negation — all graph structure
  that rules rewrite (§2/§4/§6).

The mental model the user stated, which matches the vision exactly: **the graph is low-level
code; the engine is a dumb runner; tools are the ISA (add, jump) — minimal, only for what is
*genuinely impossible* in the low-level code; rules are the program.** The failure mode we are
guarding against is *reasoning leaking into Python* — a `.execute()`-style seam (§10), which
the vision says is fatal to the one-substrate commitment.

**The test for any Python function:** does it *calculate on opaque content* (tool) or *is it
the runner itself* (mechanism)? If neither — if it inspects structure/meaning to decide,
derive, seed, classify, sequence, or answer — it is **reasoning in the wrong place** and must
become rules.

## 2. Provenance is not special — inertness was an optimization, not a law

Today the matcher is blind to provenance: `world_model._is_inert` makes the traversal skip
`proves` / `uses` / `unless` edges and `<j:…>` / `<axiom>` nodes, so no rule can match them.
That is a *class of nodes the engine hides by kind* — which is precisely what §1 ("exactly one
kind of thing, a node") forbids. So the burden is on inertness to justify itself. It does not
clear the bar. Everything inertness buys is either an optimization the engine's own strategy
already delivers, or a *separable* concern:

1. **Accidental matching** (a rule `?s ?p ?o` binding `J proves F`). Prevented already by
   **seed-from-ground** (§11): a rule anchors on its rarest *named* ground predicate and passes
   bindings sideways; a rule anchored on `is_a` never walks onto `proves`. Only a
   fully-free-predicate rule could — rare, and it should be explicit. Convention + linter,
   exactly like every other §7/§12 convention.
2. **Performance.** `proves` / `uses` are stopword-frequency names, but a truth-maintenance
   rule anchors on the *rare* thing (a specific fact, a `<retract>` request) and joins into the
   `uses` edge — it never *seeds* from `proves`. §14 already treats high-df names as stopwords.
3. **Canonicalize must not merge two firings' J-nodes.** Real — but that is the `<…>` **naming
   convention** (canonicalize skips `<`-prefixed nodes), *separable* from matcher visibility.
   Keep it.
4. **Clean domain readers / `explain`.** Real — but that lives on the *reader* side
   (`relations_from` hides provenance for tidy output), *separable* from whether *rules* can
   match it. Keep it.

Items 3 and 4 are legitimate and we keep them; 1 and 2 are covered by the strategy the engine
already uses. **None is strong motivation for hiding nodes from the substrate.**

**Decision — per-rule opt-in, not a blanket removal.** The audit pinned `_is_inert` as the *sole*
name-based special-case in the engine, load-bearing at exactly one matcher site (`rewriter._try_bind`,
"the matcher refuses to bind ANY token to an inert node") plus three *reader-side* sites
(`relations_from`, `within`, the subject-recovery idiom). We change **only the matcher-bind site**.

Note *why* it can't be "matchable only by a literal token": a truth-maintenance rule like
`?j uses ?f` must bind `?j` — a `<j:…>` node reached *through* the `uses` edge — via a **variable**,
so "a free variable never binds an inert node" is too strict (it would refuse `?j`). The real
danger `_is_inert` prevents is *accidental* binding: the `proves`/`uses` relation node appears as a
spurious predecessor of a fact node, so a domain rule `?s is_a ?o` seeding from `is_a` would, with
the refusal gone, bind `?s` to that `proves` node. The clean gate is therefore **per rule, not per
token**:

> A rule is **provenance-aware** iff any of its patterns (lhs / nac / rhs / drop) references a
> provenance name as a literal — `proves` / `uses` / `unless`, or a `<j:` / `<axiom>` /
> `<quarantine>` literal. For a provenance-aware rule the matcher **lifts the inert-bind refusal**
> (so its variables may bind `<j:…>` nodes reached through a named provenance edge). Ordinary rules
> keep the refusal, so they can never accidentally bind the spurious `proves` predecessor of a fact.

This is the "third category as a discipline" made *structural and cheap*: the opt-in IS the label —
a rule that names provenance is a meta/TMS rule; the linter flags a rule that names provenance but
is *supposed* to be a reasoning rule (a smell), enforcing "reasoning rules never touch provenance."
Implementation is localized: compute `touches_provenance` once per rule and thread it through
`_match` into `_try_bind`; `_triples` needs no change (it seeds via `nodes_named`/`pred`/`succ`,
none of which filter inertness — only `_try_bind` blocks). We **keep** the three reader-side sites
unchanged: canonicalize still skips `<…>` (J-nodes never merge), `relations_from`/`explain` still
hide provenance for tidy domain output, and the subject-recovery idiom still skips provenance
in-edges. (Fold in the COSMETIC fix: unify `within`'s inline inert list with `_is_inert` — it
currently omits `<quarantine>`.)

## 3. The one load-bearing worry — and why it is a *discipline*, not a type

The real risk of matchable provenance is **confluence of the fact layer**, not meaning. If
*reasoning* rules could derive object-facts from *derivation shape* ("F was proved by rule R in
3 hops ⇒ G"), a fact would depend on the evolving proof structure — potentially non-monotone,
non-confluent, and meta-regressive (deriving G makes provenance another rule reads to derive
H…). That must not happen on the monotone fact layer (§5).

What protects it is a **discipline on a rule class**, not a hidden node class — which is exactly
the "third category" the user is willing to accept, understood as a *label* (for humans + the
linter), not an engine mechanism:

- **Reasoning rules** (monotone fact layer) — MUST NOT match provenance. Linter-enforced.
- **Control rules** (already exist, §5) — may delete control edges, token-gated.
- **Meta / truth-maintenance rules** (the new label) — MAY match `proves` / `uses` / `unless`,
  because they only **mark or delete control**, never derive object-facts from proof shape.

This is the same kind of line as fact-vs-control already is: "which rules touch what," enforced
by convention and the linter, **not** a new node type in the engine. The engine stays uniform.
Strong-motivation bar: the separation is real (confluence), and it lives at the discipline
layer, where it costs nothing structural.

**The regress guard — meta-rules fire with provenance OFF.** A meta-rule that matches `?j proves
?f` and *fires normally* would create its OWN justification `<j:meta> proves (its output)`, which
`?j proves ?f` then re-matches — spawning another justification, forever. (Surfaced writing
`tests/test_provenance_matchable.py`.) So the discipline has a concrete enforcement, not just a
convention: **meta/TMS rules run with `provenance=False`**, and their outputs are control markers
(`<retracted>` / `<defeated>`), so no new `<j:>` is minted, no new provenance appears, and the
retraction fixpoint terminates over the *finite, already-existing* provenance graph. "Meta-rules
only mark/delete control" is thereby mechanically true: firing them produces no derivation to
regress on. (The linter can additionally flag a provenance-aware rule whose RHS creates a
non-control fact.)

## 4. Truth-maintenance as rules (what this unlocks)

With provenance matchable, the JTMS de-pythonizes into a handful of meta-rules — the vision's
own §4 `<retracted>`-marker approach:

```
# a justification that USES a retracted fact is defeated
?j status <defeated>        when  <retracted> marks ?f  and  ?j uses ?f
# a DERIVED fact whose justifications are all defeated (and which is not a base/axiom) is retracted
<retracted> marks ?f        when  ?j proves ?f  and  ?j status <defeated>
                            not   (?j2 proves ?f  and  ?j2 NOT status <defeated>)
                            not   (<axiom> proves ?f)
```

That is `retraction.cascade_retract` — the function whose *own docstring admits it is a Python
driver because "'drop ALL of a node's edges' is not a pattern"* — expressed as two meta-rules.
Completion-**defeat** (`decide.recheck`) and the `unless` edge collapse the same way: a live
positive coexisting with a completed negative is just another meta-rule that requests the
retract. The `recheck` tool disappears.

**The one tradeoff — and how we hide a fact WITHOUT teaching the matcher anything.** Marking a fact
`<retracted>` while leaving its edge intact adds a **guard tax**: every fact-consuming rule would
need `NOT <retracted> marks ?f`. That guard tax is *exactly why* `retraction.py` chose
edge-severing instead (fast matching, no guard — at the cost of a Python cascade). We avoid both by
**interposition** (the user's proposal), which hides a fact through ordinary graph rewriting rather
than any new matcher behavior:

> **Interposition (chosen retract mechanism).** A fact is the 2-hop path `S → [rel] → O`. To retract
> it, **splice a `<retracted>` node into the path** — turn `rel → O` into `rel → <retracted> → O`.
> The matcher walks `S → rel → O`, so with `O` no longer a direct successor of `rel` the fact
> **simply does not match** — no marker check, no guard, the matcher stays completely dumb. To
> **resurrect**, a rule matches the spliced shape and removes the detour, restoring `rel → O`
> losslessly. The splice IS a control rewrite (retraction is control editing control, §5), and
> unlike severing it is a *single reversible edit*, so it is expressible as a rule, not a
> "drop-all-edges" driver.

Resolved at build time (2026-07-02):
- **`drop` removes a whole *relation node*** (`_remove_relation` → `remove_node`), so it cannot
  splice a single edge. We therefore added a minimal general **`rewire`** control-layer primitive to
  the rule vocabulary — `rewire=[("cut", a, b), ("link", a, b), …]` edits *raw edges* between bound
  nodes (`apply_rule`). This is the identity/provenance-preserving structural edit `drop`+re-add
  can't express; it is broadly useful (retraction now, true coref-merge later, DPO-style reshaping),
  and it is the more fundamental addition than a matcher special-case. **DONE + tested**
  (`tests/test_rewire.py`).
- **Interposition uses `rewire`:** hide = `cut(rel,O); link(rel,<retracted>?); link(<retracted>?,O)`
  (fresh `<retracted>` per fact); resurrect = the inverse, matched off the interposed shape. The
  `rel` node — and its `J→proves→rel` provenance — survives. **DONE + tested.**
- **`<retracted>` is INERT** (`world_model._is_inert`), so the transient `S→rel→<retracted>` reading
  can't leak as a spurious domain fact, while a meta/resurrect rule that *names* `<retracted>` is
  provenance-aware and may traverse it. (The linter should still flag a fully-free-slot consumer of
  a retractable predicate, and an ungated / malformed-relation `rewire` — TODO.)
- **The cascade stays meta-rules (next).** Interposition hides *one* fact; the transitive "retract
  everything a retracted fact supported" is the §4 meta-rules over now-matchable provenance, whose
  action is a `rewire` interposition. Not yet built.

Net after this line of work: **provenance visible (per-rule opt-in); TMS = meta-rules; a fact is
hidden by splicing a `<retracted>` node into its path (ordinary rewriting, matcher untouched) and
resurrected by the inverse rule; the `retraction.py` cascade tool and the `decide.recheck` tool are
deleted.** The earlier "matcher-visibility marker" idea is dropped in favor of interposition
(interposition needs no new matcher mechanism at all).

## 5. Consequences for the in-flight `decide` refactor

- Completion **materialization** becomes a generated **NAC rule** (`?c is_not P when <positive
  residual> and P closes <closed_world>, NOT ?c is P`). Sound timing falls out of stratified
  negation for free (the NAC on `is P` puts completion in a stratum after P's producers). This
  needs *none* of the provenance work — it can land independently.
- Completion **defeat** becomes a meta-rule over matchable provenance (§4), not
  `RECHECK_TRIGGER` + `recheck_tool` + `cascade_retract`.
- `<decide>` demand tokens, `seed_decide`, `complete`, `complete_tool`, `demand_rule`, and the
  `unless` bookkeeping are all removed. `declare_closed_world` / `is_closed_world` /
  `positive_holds` / `negative_holds` stay as thin marker read/write helpers (not reasoning).

Sequencing (build order): **§2–§4 provenance-matchability first** (the keystone), then the
completion refactor lands cleanly on top with defeat-as-rules. Doing completion-materialization
first is safe if we want an early win, but defeat should wait for §4 so we don't build a second
`recheck` tool we then delete.

---

## 6. Module-by-module audit — reasoning-in-Python that should be rules

Full pass over every `harneskills/*.py` module against §1's three-bucket test. Severity:
**BLOCKS** (foundational; other work builds on it), **SHOULD** (clear seam, schedule it),
**COSMETIC** (minor / gray reflection-or-render / authoring-in-Python).

### Headline

**The engine is clean.** No module derives facts, decides the crisp truth of a query, ranks
hypotheses, resolves *which* mentions corefer, or *selects* a plan in Python. Derivation,
contradiction detection, coreference propagation, universal laws, and planner selection are all
**already rules / handlers**, and `match` is the blessed technical matcher. The matcher +
substrate (`rewriter.py`, `world_model.py`) are pure content-blind mechanism; `demand.py`,
`walker.py`, `universal.py` are model citizens (magic-sets, walkers, universals all expressed as
rules-as-data); `external.py`, `driver.py`, `kb.py`, `lint.py`, `surface.py`, `interaction.py`,
`repl.py`, `procedure.py` are clean tools/plumbing/render.

**So there are no BLOCKS.** What remains is a small set of **orchestration seams** (Python
sequencing reasoning that should be token-gated phases) and a few **reasoning pockets**, plus a
recurring **authoring-in-Python** cosmetic axis. In priority order:

### SHOULD — the real seams (schedule these)

1. **The truth-maintenance layer → meta-rules** (`retraction.cascade_retract`, `decide.recheck` /
   `unless`, `forms.canonicalize`). This is the subject of §2–§5 and the reason for this doc. The
   cascade is a Python fixpoint driver whose own docstring admits it resists rule expression;
   with provenance matchable (§2) it becomes ~2 meta-rules (§4). **This is the keystone** — the
   `decide` completion-defeat and any future retraction build on it. Do first.

2. **`query.ask` → answer-rules** (`query.py`). Question *recognition* is properly emergent (forms
   fire), but *answering* is a Python dispatcher on `qtype` (yesno / who / n-ary / why) that,
   per branch, extracts+sorts subjects or **builds a multi-`Pat` join from the n-ary roles** or
   calls `explain`. Per §3/§6 the `<query>`/`<qevent>` node should trigger rules that materialize
   an `<answer>` node; `match` stays the technical matcher. The n-ary join construction is the
   most reasoning-like. (Defensible-as-reflection by its docstring, but it exceeds mechanical
   reflection.)

3. **`session._assert` → token-gated phases** (`session.py`). A hardcoded Python *sequence*
   (tokenize → run forms → run graded → strip → derive) + per-line seeding + a `recognized`
   content-diff judgment. Self-admitted seam, parked by the user (a documented standing
   constraint). §6 says the phase ordering belongs in a `drive(plan)` of token-gated phases, not
   a Python method. Much of the harness rides on this pipeline — foundational, but it's an
   *orchestration* seam already slated to dissolve, so SHOULD, not BLOCKS. (Respect the user's
   park until we choose to unpark it.)

4. **`coref.coref_on_demand` → walker** (`coref.py`). The coref *decision* is already rules
   (`contradictions` over `rules_in_graph`), but the **hypothesize → propagate → detect →
   inspect → retract, pairwise over all mentions** loop is Python orchestration. The vision's own
   walkers/locality decision names a walker (control token + fuel) with `same_as`-materializing
   rules as the target. No meaning is inspected in Python — it's a control seam.

5. **`rule_graph` property-law synthesis** (`_property_rule` / `_disjoint_rule` /
   `_contradiction_rhs`). These **switch on a property keyword's meaning** (`transitive` → build a
   transitivity rule; `acyclic`/`asymmetric` → closure + contradiction) and hand-synthesize the
   reasoning-rule *templates* in Python — reasoning-shape as Python (§6/§10). **Blocked by the
   quote/eval gap** below, so it cannot move yet; keep on the list as the concrete "universals →
   laws" target.

### COSMETIC — cleanups and the authoring axis

- **`forms.canonicalize`** name-merge crutch — already superseded by additive
  `wire_same_as`/`coref_in_context`; retire it (memory `decision_quantification_coreference` plans
  this). `coref_in_context`'s "different context ⇒ distinct" is the only mild reasoning left in the
  coref tools; the name-linking itself is the accepted §8/§14 name-op boundary.
- **`planning._invalidate_cheaper_than`** hard-deletes `cheaper_than` *fact* edges on a price
  change — inconsistent with the additive `supersedes` freshness discipline used for prices right
  next to it (§5 nit).
- **`session.CONTENT_PREDS`** classifies relations as "content" by a curated predicate-name set —
  meaning-based classification in Python (§12.2 smell); display/UX only, not load-bearing.
- **`query._parse_question`** hardcodes "prefer the n-ary reading over binary" — a disambiguation
  policy in Python.
- **`world_model.within`** inert-list divergence (omits `<quarantine>`) — unify with `_is_inert`.
- **`walker.py`** non-`is_a` path still assembles rulesets from Python factories (the `is_a` path
  is already CNL).
- **`forms.expand_pronouns_text`** resolves a pronoun by text substitution — a coref decision, but
  vision §14 explicitly blesses anaphora as a minimal name-op outside the grammar. Leave.

### Cross-cutting gaps (not per-module — they gate several SHOULD items)

- **The quote/eval (meta-circular authoring) gap.** A `Pat`-rule RHS cannot mint a node *literally
  named* `?a` (the reader treats `?a` as a variable), so a rule that must *generate rules with
  fresh pattern variables* can't be authored in CNL today. This is the real blocker under
  `rule_graph` property-laws (SHOULD #5) and the "universals → laws" retirement of `canonicalize`.
  Closing it is a prerequisite, not a nicety.
- **Authoring-in-Python (data, not reasoning).** Many `Rule` literals live in Python
  (`universal.py`, the machine/prose/rule_graph *forms*, `planning`'s seeders). This is *data in
  Python*, not *reasoning in Python* — a lower-priority axis (the homoiconic-limit "load the rules
  from CNL too"), distinct from the seams above. Track separately; don't conflate with de-seaming.

### Build order implied by the audit

1. **[DONE] Provenance matchable (§2)** — `rewriter._try_bind`/`_match` are provenance-aware per
   rule (`_pats_touch_prov`); ordinary rules unchanged, meta-rules opt in by naming provenance.
   `tests/test_provenance_matchable.py` (capability + accidental-match safety).
1b. **[DONE] `rewire` primitive + interposition (§4)** — `cut`/`link` raw-edge ops in the rule
   vocabulary (`Rule.rewire`, `apply_rule`); `<retracted>` inert; hide-by-splice + resurrect as
   rules. `tests/test_rewire.py`. 178 tests green.
2. **[DONE] TMS cascade as meta-rules** (run with `provenance=False`, §3) — `retraction.RETRACT_RULES`
   (aggressive/single-support `CASCADE` + `INTERPOSE`), seeded by `<retract> targets ?rel`, hides by
   `rewire` interposition over now-matchable provenance. `tests/test_retract_rules.py`. The EXACT
   "all justifications defeated" form is non-stratifiable (§11) → the aggressive form + monotone
   re-derivation is the multi-support path (re-derivation not wired yet — single-support is the need).
   `cascade_retract` stays until coref (its other caller) migrates; linter guards for `rewire`
   (ungated / malformed-relation) still TODO; retire `canonicalize` onto additive coref (COSMETIC).
3. **[DONE] `decide` completion/defeat as rules.** Completion = a generated rule
   (`decide.completion_rule`, emitted by `authoring._completion_rules` in place of the `<decide>`
   demand rule); defeat = `DEFEAT_SEED` (`?c is ?p and ?c is_not ?p` → `<retract> targets` the
   negative) onto `RETRACT_RULES`. `decide.solve` = derivation+completion (provenance on) then, iff
   a defeat was seeded, the retraction pass (off). Deleted: `complete`/`complete_tool`/
   `COMPLETE_TRIGGER`/`recheck`/`recheck_tool`/`RECHECK_TRIGGER`/`DECIDE_TOOLS`/`seed_decide`/
   `pending_decisions`/`demand_rule`/`<decide>`. **Key subtlety:** completion is AGGRESSIVE +
   MONOTONE (no NAC) — a NAC on `?c is P` would false-cycle through the overloaded copula `is`
   (object-blind stratification: completion NACs on `is cleared`, consumer produces `is thief`),
   which is the very gotcha the Python `complete` originally dodged. So complete unconditionally +
   let DEFEAT repair — the mirror of aggressive-retract + re-derive. (A cleaner future fix:
   object-aware stratification for the copula, retiring the over-completion churn.)
4. Then, opportunistically and each independently: `query.ask` → answer-rules; `coref_on_demand`
   → walker; the quote/eval gap → unlocks `rule_graph` property-laws.
5. `session._assert` remains parked until the user unparks it.

### Reference — this is "knowledge compilation" (topology as data)

The interposition instinct — pick an encoding where *hide fact* / *resurrect fact* are O(1) local
rewrites instead of global recompute — is precisely a **knowledge-compilation** choice (Darwiche &
Marquis, *A Knowledge Compilation Map*, JAIR 2002: succinctness × tractability — which ops stay
polynomial per representation). Adjacent, directly useful: **e-graphs / equality saturation** (egg,
Willsey et al. 2021) separate *the graph* from *what is currently believed equal* — the same
structure/belief split as our `same_as` + retract topology; and the **JTMS vs. ATMS** contrast
(Forbus & de Kleer, *Building Problem Solvers*) is exactly a provenance-topology cost tradeoff
(single-context cheap retraction vs. multi-context labels). **Caution that matches our vision:** keep
"smart topology" as *authored / materialized structure* (data), never as smartness in the engine's
traversal — the dumb fixpoint must stay trivial at runtime (§6, no branch-selection). Do the smart
thing once, at encoding time.
