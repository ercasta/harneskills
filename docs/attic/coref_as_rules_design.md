# Design — coref_on_demand → rules (the serialized cursor) (2026-07-02)

> **Status: DONE (2026-07-02), CHECK-BEFORE-COMMIT (187 tests).** The `coref_on_demand` seam is
> migrated to rules and the old Python machinery is deleted. After the step-4 finding (below), the
> design pivoted from serialize+retract to **CHECK-BEFORE-COMMIT** (user call, "now; generalize
> later only if no harder-later lock-in" — verified no lock-in). Coref is now purely ADDITIVE: for
> each pair the cursor waits on the `settle` barrier (endpoints' sorts current), checks a
> disqualifying clash, and COMMITS the link only if there is none. No hypothesize, no cascade, no
> retraction — so no propagation-fight. The whole walk is ONE `run(provenance=True,
> tools=SETTLE_TOOLS)` driven by rule firing + the engine's service cycle (NO Python loop).
>
> LANDED: `Rule.meta` per-rule provenance; the `<coref>` cursor (`coref_walk.py`: materializer,
> `settle` barrier tool, `PROBE`/`CHECKED`/`COMMIT`/`ADVANCE`, generated `clash_rules(graph)`);
> **`force`** (`X is one thing` — `FORCE_COMMIT` links every pair so a single-identity mistake
> surfaces a real `<contradiction>` under detection); **resolver** (`RESOLVE_EMIT` + a `resolve`
> tool wrapping the oracle); **`resolve_coref` + `coref_request_handler`** wired into
> `Session._resolve_coref`; the old `coref.py` loop, `cascade_retract`, and the whole `<quarantine>`
> cluster DELETED (`retract`/`RETRACT_RULES` is the sole TMS path). `tests/test_coref_walk.py`,
> `tests/test_meta_provenance.py`; two-Pauls + transitive-clash are order-robust.
>
> KEY FIX (instance-vs-name): `clash_rules` are generated PER `A disjoint_from B` declaration with
> the cat names as LITERALS (like `_disjoint_rule`), so they match across distinct same-name
> instances — a single generic `?s1 disjoint_from ?s2` rule missed in `Session` because the pauls'
> `is_a`-object and the disjoint declaration are different `teacher` nodes.
>
> NON-DETERMINISM NOTE: the greedy outcome (which compatible link is kept when a mention is
> compatible with two disjoint others) depends on the hash-randomized `nodes_named` order — SAME as
> the original `coref_on_demand`; the order-robust invariant holds (consistent, direct clashes
> always rejected, never both of two mutually-exclusive links).
>
> DEFERRED (separate arcs, NOT loose ends of this migration): the general propagate-then-retract
> path (the generalization hook, for non-endpoint-checkable constraints); retiring `canonicalize`
> from the batch load path (gated on universals→laws per `decision_quantification_coreference`).
>
> ---
> ORIGINAL PLAN (serialize + retract — SUPERSEDED by check-before-commit for the common case;
> retained as the GENERALIZATION HOOK for non-endpoint-checkable constraints). Decisions that
> still hold: `Rule.meta`; no Python loop; the `settle` barrier as the "detection settled" signal.
>
> The de-pythonization follow-up flagged in
> `docs/depythonization_design.md` §6 (seam #4). Read `docs/attic/coreference_design.md`
> (the original coref design, historical) and `docs/depythonization_design.md`
> (provenance-matchable, `rewire`/interposition, RETRACT_RULES) first.

## The seam we are closing

`coref_on_demand(graph, name, …)` (`coref.py`) is *already* invoked as a tool — a
`<demand>` becomes `<call> coref` (`demand.DEMAND_COREF`), the engine services it, and the
`coref` handler runs. So the seam is **not** "Python drives from outside." It is that the
handler runs a **Python generate-and-test loop that inspects `<contradiction>` and decides
which `same_as` links to keep** (`coref.py:115-137`):

```
for each pair (a,b) of name's mentions, unlinked & unrejected:
    wire a same_as b            # hypothesis (control)
    run(propagation)            # same_as_rules over incident predicates
    if force: keep; continue
    run(detection)              # constraint schemas -> <contradiction>
    if <contradiction> about name:  cascade_retract(link); record not_same_as   # REJECT
    elif resolver(a,b)=="distinct": cascade_retract(link); record not_same_as   # REJECT
    else: keep                                                                  # KEEP
```

The KEEP/REJECT decision is reasoning in Python. The migration moves it into rules and swaps
`cascade_retract` (the last Python TMS driver) for `retraction.RETRACT_RULES` — which lets
`cascade_retract` be **deleted** (its only remaining non-test caller).

## Why the serialized shape (recap of the A-vs-B call)

Aggressively linking all of a name's pairs at once and repairing with a defeat rule (the
"mirror decide" shape) fails here where it works for decide, because **coref hypotheses
interact**: `same_as` is transitive and propagates facts across the whole class, so (i) a
`<contradiction>` cannot be attributed to *one* link (which to retract is a minimal-hitting-set
problem, not a match), and (ii) linking all pairs of one name reintroduces the O(k²) `same_as`
saturation the on-demand loop exists to prevent (coreference_design §0). Decide's aggressive
form is sound only because completed negatives are **independent**; coref's are not.

So we keep **one hypothesis live at a time** — the faithful rules-encoding of the current
loop. Correct by construction, preserves the bounding invariant.

## No Python driver loop — the control flow is emergent (the load-bearing decision)

An earlier draft of this note proposed a thin Python `while` loop (run → if reject, retract →
advance → repeat). That is a *fixed control flow* smell, and the substrate should express
iteration as **emergent rule + tool firing**, the way the walker runs a whole BFS inside one
`run()` with no domain loop. Reading the engine (`rewriter.Rewriter.run`) shows the loop is
avoidable. Two facts:

1. **The fixpoint-then-service cycle IS an engine-provided iteration loop** (`rewriter.py`
   ~743-755), not domain Python. When rules quiesce, the engine services pending `<call>`s,
   folds their output in as the new change frontier, sets `force_all=True`, and re-runs — until
   BOTH rules and tools quiesce. The walker's BFS and the old decide loop both iterate purely
   through this. So "genuine iteration" is already rules+tools within one `run()`.

2. **Per-rule provenance dissolves the on/off split.** Provenance is *currently* a run-level
   flag, but it is applied **per firing** (`rewriter.py:737`, `premises=prem if provenance else
   None`). Making it per-rule is a tiny, principled change — and it is *already* conceptually
   per-rule: the depythonization design DEFINES meta/TMS rules as "fire with `provenance=OFF`
   (regress guard)," today enforced by running them in a separate `run(prov=False)`. A
   `Rule.meta=True` flag (provenance-silent) lets those rules coexist in ONE run with prov-on
   reasoning rules. `retraction.retract` (its own separate prov-off pass) collapses into this.

So the whole process runs in **one `run(graph, coref_rules, tools=…)`**:

- `hypothesize` / `propagate` / `detect` — provenance **ON** (cascade needs the support chain).
- a rule emits a trivial `<call>` barrier for the current pair; the engine services it **only
  at quiescence** → it stamps `{pair} settled`. The tool does NO inspection — its mere
  post-quiescence servicing IS the "detection has settled" signal. That signal is irreducibly
  the engine's to give: a rule cannot match "no other rule can fire," and "keep = no
  contradiction" is negation-as-failure, which in a single monotone fixpoint reads true BEFORE
  detection has derived the contradiction. This is the same primitive the walker (`dec`) and
  the old decide barrier use — an engine mechanism, not a fixed control flow.
- `reject` / `RETRACT_RULES` / `record-rejection` — provenance **OFF** (`meta=True`), seeded
  when `{pair} settled` coexists with a `<contradiction>` about one of the token's mentions.
- `advance` moves the cursor → re-triggers `hypothesize` for the next pair → new `<call>` → the
  engine's own service cycle iterates. No Python `while`.

The two remaining Python pieces are §8-legitimate, NOT reasoning: the **demand seed**
(materialize the mention set as a walkable chain by name — same category as `seed_demand` /
`spawn_walker` locating nodes by name) and the **tool handlers** (the trivial quiescence
barrier; the resolver oracle `<call>`).

### Why rules cannot gather the mentions themselves

The matcher binds on graph *structure* (edges), not name-equality; two mentions are distinct
node ids that merely share a name string. `coref_on_demand` uses `graph.nodes_named(name)` (a
name-index lookup) to get them, so a rule has nothing to traverse until the seed wires the
mention chain. This is demand *scoping*, not the DECISION — which stays in rules.

## The design — a `<coref>` cursor token + verdict rules + a dumb driver

### Materialize (thin driver, demand scope)

For demanded name `N` with mentions `m₁…m_k` (`nodes_named(N)`): create a `<coref>` token and
wire an ordered walk so pair enumeration is deterministic (no same-stratum multiple-fire
hazard):

```
<coref> --name--> N
m₁ --next--> m₂ --next--> … --next--> m_k          (an order over the mentions)
<coref> --anchor--> m₁ , <coref> --probe--> m₂     (cursor = the pair currently under test)
```

(Only mentions not already `not_same_as`/`same_as`-settled need enter the chain; skipping
settled ones keeps idempotence — a re-demand re-tests nothing.)

### Test the current pair (rules, provenance on)

```
hypothesize:  <coref> anchor ?a, <coref> probe ?b, NOT ?a not_same_as ?b, NOT ?a same_as ?b
                  =>  ?a same_as ?b
propagate:    same_as_rules(incident predicates ∪ {is_a})          [reused verbatim]
detect:       rules_in_graph(expand_relation_properties(graph))    [reused verbatim]
```

`propagate`/`detect` are the *existing* rulesets — no new reasoning. Incident-predicate
auto-detection (`coref._incident_predicates`) and `axiomatize` (base facts survive the
cascade) stay as the materializer's setup, unchanged.

### Barrier (a trivial quiescence `<call>`)

Hypothesize also emits `<call> settle` for the current pair. The engine services it only once
rules have quiesced (propagation + detection done); the handler just stamps `<coref> settled ?b`
— no inspection. This is the ONLY sound "detection is complete" signal (see the emergent-flow
section). After it fires, `force_all=True` wakes the verdict rules on the fresh `settled` node.

### Verdict (rules, `meta=True` where they seed retraction)

The reject condition is a rule matching a contradiction about one of *this token's* mentions
(the `mention`/chain edges make "about N" a structural match, replacing the Python
`_contradiction_about`):

```
reject:  <coref> anchor ?a, <coref> probe ?b, <coref> settled ?b, ?a same_as ?b,
         <contradiction> about ?x,  <coref> mention ?x
             =>  <retract> targets (?a same_as ?b) , ?a not_same_as ?b     # meta=True (prov off)
```

- **REJECT** ⇒ `<retract> targets link` seeds `RETRACT_RULES` (already in the ruleset,
  `meta=True`), which cascade-hides the link and its propagated consequences in the SAME run;
  `?a not_same_as ?b` blocks re-hypothesis (the `hypothesize` NAC). The orphaned
  `<contradiction>` shell's `about`/`violates` edges are hidden by the cascade, so it can no
  longer match — no `gc_disconnected()` needed for correctness.
- **KEEP** (settled, no contradiction about a mention) ⇒ the link simply stands; `advance` fires.
- **`force` mode** (`X is one thing` → `is_unique`): the reject rule carries a NAC on an
  `is_unique`-derived marker on the token, so a forced token never rejects — link unconditionally
  (the current `force=True` branch). The force set stays DATA (`is_unique` facts).
- **resolver** (consistent-but-ambiguous): when settled with no contradiction and a resolver is
  configured, a rule emits a `<call>` to the disambiguation oracle
  (`interaction.disambiguation_resolver`, already `<call>`-shaped); a `distinct` verdict seeds
  the same `<retract>` + `not_same_as`.

### Advance (rule)

```
advance:  <coref> settled ?b, (verdict done)  =>  probe := next(?b);
          at end of chain, anchor := next(anchor), probe := next(anchor); clear settled
```

Deterministic single-threaded iteration — the Python double loop, now a token walk driven by
the engine's own service cycle. When the cursor runs off the end the token is spent; a terminal
rule can `drop` the token + chain (cleanup, not control).

### Putting it together — one `run()`, no domain loop

```
def resolve_coref(graph, name, *, resolver, force):        # thin SEED, not a loop
    materialize <coref> token + mention `next`-chain + axiomatize(incident preds)   # demand scope
    run(graph, COREF_RULES + same_as_rules(preds) + detection + RETRACT_RULES,
        tools={settle, resolver_oracle})                   # emergent iteration to fixpoint
```

`COREF_RULES` = hypothesize / reject / (force-skip) / advance / terminal-cleanup, plus the
reused `same_as_rules`, detection, and `RETRACT_RULES`. Contrast the earlier draft's `while`:
the cursor-advance + `<call>`-service cycle replaces it entirely. Compare `decide`'s final form
(aggressive completion + defeat, all rules, no loop) — same spirit, one run.

## What gets reused vs. new

- **Reused verbatim:** `same_as_rules`, `expand_relation_properties`/`rules_in_graph`
  (detection), `RETRACT_RULES`/`seed_retract` (retraction), `record_rejection`/`is_rejected`,
  `_incident_predicates`, `axiomatize`, `disambiguation_resolver`, the `DEMAND_COREF` →
  demand plumbing (retargeted to seed a token instead of the old `coref` call, or the `coref`
  tool re-pointed at the new driver).
- **New:** a `Rule.meta` flag + the one-line engine change (per-rule provenance suppression);
  the `<coref>` token vocabulary + materializer (demand seed); the hypothesize / reject /
  advance / terminal-cleanup rules; the `record-rejection` rule; the trivial `settle` barrier
  tool. **No driver loop.**
- **Deleted:** `coref.py`'s Python generate-and-test loop; `retraction.cascade_retract` (+ its
  helpers `quarantine_fact`/`quarantine_j`/`_live_support`/`is_quarantined`/`quarantined_nodes`
  if nothing else uses them — confirm by grep); the two tests that call `cascade_retract`
  directly are rewritten onto the rule path. `retraction.retract`'s separate prov-off `run`
  may also fold away (its callers can include `RETRACT_RULES` in their main run).

## Open sub-decisions for sign-off

1. **Per-rule provenance via a `Rule.meta` flag.** A `meta=True` rule fires provenance-silent
   even in a prov-on run (regress guard), letting reasoning + TMS rules share ONE `run()`. This
   is the enabling change and it is aligned with the existing meta-rule category (currently
   enforced by a separate prov-off run). **Proposed: add the flag.** Alternative considered and
   rejected: derive silence from `_pats_touch_prov` — but `INTERPOSE` isn't provenance-matching
   yet must be silent, so an explicit flag is more honest.
2. **No Python loop — emergent flow via the fixpoint-then-service cycle + a trivial `settle`
   barrier.** **Proposed** (replaces the earlier driver-loop draft, per the substrate
   principle). The barrier `<call>` is the irreducible engine primitive for "detection settled."
3. **Cursor chain vs. "one testing-marker" NAC.** The ordered `next`-chain cursor is
   deterministic and dodges a same-round multiple-hypothesize hazard, at the cost of the small
   materializer. **Proposed: the chain.**
4. **Where the seed lives.** A `coref.resolve_coref` module fn the `coref` tool calls (smallest
   blast radius on `Session._resolve_coref`), vs. dissolving into `DEMAND_COREF` seeding the
   token directly. **Proposed: module fn first; dissolve later.**
5. **Termination / well-foundedness** unchanged from coreference_design §5 (coref support is
   tree-shaped; `acyclic` pre-empts cyclic `is_a`). Cursor advance is monotone-forward + the
   `not_same_as` NAC blocks re-hypothesis, so the single fixpoint terminates.

## Build order

1. **`Rule.meta` + engine change** (`production_rule.Rule`, `rewriter.Rewriter.run` line 737);
   a test that a `meta=True` rule emits no `<j:>` in a prov-on run, and reasoning rules still do.
   Fold `retraction.retract` to rely on it (RETRACT_RULES marked `meta=True`).
2. **Token vocabulary + materializer + `advance` rule + `settle` barrier tool**; a test that the
   cursor visits every pair of a 3-mention name in order within one `run()` (no reasoning yet).
3. **`hypothesize` + reuse `propagate`**; verify one kept link composes facts (the consistent
   pair) — still no reject.
4. **`reject` rule (`meta=True`) + `RETRACT_RULES` in the ruleset + `record-rejection`**; port
   the "two Pauls stay separate" test onto the rule path. Verify it all happens in one `run()`.
5. **`force` variant + resolver `<call>`**; port the remaining `coref.py` tests; wire
   `Session._resolve_coref` to the new seed.
6. **Delete `cascade_retract`** (+ dead helpers); rewrite `test_walkers.py:124` /
   `test_new_core.py:1947` onto the rule path. Retire `forms.canonicalize` from the `Session`
   path (coreference_design §8 tail) — the downstream cleanup this unblocks.

## FINDING (build step 4, 2026-07-02) — retraction cannot share a run with propagation

Steps 1-3 landed clean (185 tests): `Rule.meta` per-rule provenance; the cursor mechanics
(materializer, `settle` barrier, `advance`); `hypothesize` + a KEPT link composing facts, all
in one `run()`. **Step 4 (reject) exposed a real flaw in the "one run, RETRACT_RULES in the
ruleset" plan.**

Empirically (2-mention "two Pauls", `max_steps` bisection): the walk reaches quiescence and
`reject` fires fine, but once `RETRACT_RULES` start cascading **in the same run as the monotone
`same_as` propagation**, the two FIGHT — cascade hides a `same_as` fact, the deleting step sets
`force_all`, propagation re-derives it, cascade re-marks it, provenance J's + `<retracted>`
interposers accrue without bound (nodes 74→240→642→1830 over four steps; `same_as.*` firings
explode). This is the re-derive/re-retract non-confluence the `RETRACT_RULES` doc already warns
of — and it is exactly why `cascade_retract` / `decide.solve` run retraction as a SEPARATE,
isolated pass with no reasoning rules active.

So the premise "put RETRACT_RULES in the coref ruleset and let it all run in one fixpoint" is
wrong. Two consequences:
- **Retraction must be phase-isolated** from propagation (a cascade that runs to completion
  before propagation re-fires). The engine's fixpoint-then-service cycle can give that isolation
  (retraction as a serviced tool / a gated stratum), but it makes each pair a **sequential
  multi-barrier protocol**: `hypothesize → [settle barrier] → reject → [retract barrier] →
  advance`. Emergent (no Python loop), but intricate — multiple completion markers per pair,
  `reject` stratified before `advance`, and `advance` gated on retraction-complete for a
  rejected pair vs. settled-and-not-rejected for a kept one.
- **A cleaner alternative surfaced: CHECK-BEFORE-COMMIT (retraction-free).** Don't optimistically
  link-then-retract. The disqualifying clash is detectable from the two endpoints' *current
  class sorts* BEFORE committing: `cursor (a,b), a is_a ?s1, b is_a ?s2, ?s1 disjoint_from ?s2
  ⇒ reject` (record `not_same_as`, do NOT link); otherwise COMMIT `a same_as b` and propagate.
  Coref becomes purely ADDITIVE — it only ever commits consistent links, never withdraws — so
  there is NO cascade, NO interposition, NO propagation-fight, and `cascade_retract`'s last
  caller vanishes anyway (goal met by ELIMINATING coref's need to retract, not replacing the
  driver). Still needs a per-pair barrier (a commit's propagation must settle before the next
  pair's check, for transitive-clash awareness), but ONE barrier, no retract phase.
  - Trade-off / open question: check-before-commit detects an *endpoint-checkable* clash
    (disjoint sorts — the only kind the current coref tests exercise). The original
    `<contradiction>`-based coref is fully general (any declared constraint, visible only after
    propagation). If coref must stay that general, generality reintroduces propagate-then-retract.

Also learned: a NAC is fine when it is **barrier-gated** (evaluated after the settle barrier
guarantees detection/propagation is complete) — that is just STRATIFIED negation, which the
vision permits (§11). The "drop the keep-NAC" instinct applies to *premature* NAF in a monotone
fixpoint, not to a barrier-stratified one. So `keep`/`commit` may use a barrier-gated NAC.

## Honest scope

Comparable to the decide arc, not a quick cleanup: an enabling engine change (per-rule
provenance) + new rule vocabulary, ~6 build steps. But the payoff is larger than first scoped —
the whole thing runs as ONE `run()` with emergent control flow (no domain loop), the last real
TMS seam is closed, `cascade_retract` is deleted, and `Rule.meta` cleans up the retraction
module too.
