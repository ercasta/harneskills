# §5 ASI — Design Critique and Recommendations

**Status:** Review companion to `05-active-semantic-inference.md`
**Grounded in:** `harneskills/rewriter.py`, `harneskills/engine.py`, `harneskills/planner.py` (read 2026-06-24)
**Audience:** engine authors deciding what to build for ASI Phases A–E

---

## §C.0 Summary verdict

The core idea is sound and the novel claim — *unifying analysis and action in one
goal-directed monotone loop, with business logic and program semantics in the same
KB* — holds up. The architecture is pointed the right way. Two things stand between
it and "scales + sound":

1. a real evaluation engine underneath (Datalog-grade incremental matching), and
2. confronting the monotonicity-vs-refinement tension head-on (now resolved — see §C.3).

Neither requires abandoning the design; both are additive.

The §5.9.1 "critical unknown" (does the rewriter join two distinct entity variables?)
is **already solved in code** — see §C.1. Phase C's blocking risk is smaller than the
spec fears.

---

## §C.1 What already works (better than the spec hedges)

`find_all_matches` (rewriter.py:323) handles multi-entity binding today:

- `_extract_vars` (rewriter.py:159) collects every distinct variable across all
  segments in first-appearance order.
- `_backtrack` (rewriter.py:292) binds each variable, constraining candidates via
  already-resolved segments with set-intersection (`_candidates_for_var`, rewriter.py:222),
  and final-checks every segment with `_all_satisfied` (rewriter.py:276).

So `?caller calls ?callee AND ?callee is a X` joins correctly. The interprocedural
rules in §5.4 are parseable *and* evaluable now. The Phase C "verify the rewriter join"
task is effectively done — write the tests to lock it in, but do not expect a redesign.

---

## §C.2 The seam is relocated, not eliminated

§5.1's principle ("Python emits atomic structural observations; CNL derives all
semantics") is leaky in a way worth stating plainly.

§5.4 defines `has_negative_return` as firing "when a Return value *could be* negative
(e.g. `a - b`)." That "could be" is an abstract-interpretation judgment already baked
into Python. The walker's **choice of atom vocabulary is the semantic commitment** now.

This is still a real win — the seam shrinks to a smaller, more auditable surface — but
"no semantic reasoning in Python" is aspirational, not achieved. The atom layer is the
new trusted base.

**Recommendation:** make the AST→atom mapping a *versioned, golden-tested contract*.
Spec it formally and pin it with fixtures. Treat the walker as the trusted kernel;
everything above it is auditable CNL.

---

## §C.3 Monotonicity vs. "override" — resolved via retraction tombstones

§5.1 promises the engine can "trace, explain, and *potentially override*." But
`run_rewrites` hard-rejects `delete_lhs` (rewriter.py:587–595) — the reasoning fixpoint
only accumulates. Naively, that contradicts override and blocks refinement
("was unsafe, now proven safe").

**Resolution (no engine change, stays monotone):** model retraction as a *tombstone
edge*, not a deletion.

- To retract fact `F`, add a marker edge `(F, retracted, by_X)`.
- NAC-gate every consumer of `F` on the *absence* of that edge.

The fixpoint never deletes; the tombstone shadows the fact. This is strictly better
than a `delete_lhs` tier:

- monotone — least fixpoint preserved, termination still guaranteed;
- auditable — the graph records *what* retracted *what*, and why;
- composable — retractions can themselves be derived by CNL rules.

NAC is already implemented (`_any_nac_fires`, rewriter.py:373), so this needs no new
engine primitive. Costs: one NAC clause on each downstream rule, and the extra fixpoint
pass to propagate tombstones. Fair price.

The same pattern expresses "override" generally: derive a positive counter-evidence
predicate (e.g. `division_guarded`) and NAC-gate the conclusion (`division_unsafe`) on
it. "Override" = positive counter-evidence + NAC, never deletion. Document this as the
canonical idiom.

---

## §C.4 Scalability — the idea scales; this engine does not yet

Two concrete blockers in the current code.

### §C.4.1 Everything is recomputed from scratch

- `planner.plan` rebuilds the reasoning graph and runs the *full* `ALL_RULES` fixpoint
  on every `step()` (planner.py:69–76).
- `_system2_expand` rebuilds a `SemanticGraph` from the entire DM after *every* tool
  execution (engine.py:84–91).

For an N-function codebase needing N analysis steps, that is N full fixpoints — already
quadratic-plus before counting matching cost.

### §C.4.2 Matching is neither semi-naive nor indexed

- `apply_rule` calls `find_all_matches(rule.lhs, graph)` over the whole graph each
  iteration (rewriter.py:468).
- `_candidates_for_var` returns `graph.nodes()` for any unconstrained leading variable
  (rewriter.py:273).

The `seen` set and `likely_next` frontier (rewriter.py:618) trim re-*firing* but not
re-*matching*. On a whole-codebase call graph this is O(rules × nodes^vars) per
iteration — fine for the ice-cream demo, hopeless at thousands of functions.

### Recommendation

Do not reimplement 40 years of Datalog optimization inside a backtracking matcher.
Compile the Layer-2 structural-semantics CNL down to a real Datalog engine (Soufflé, or
an embedded semi-naive evaluator) for the *bulk* fixpoint. Keep the novel contribution —
the goal-directed planner that schedules tools and acts — as the outer loop on top. You
lose nothing conceptual and inherit incremental evaluation, indexing, and stratified
negation for free.

---

## §C.5 Soundness — syntactic atoms are lint-grade, not sound

`division_unsafe derives when has_division_by_name` (§5.4) will fire on nearly every
real divisor. Without dataflow or path sensitivity, false-positive rates on real code
will be high. The procedure-summary story (§5.3.4) is just accumulating `is_a` facts —
there is no lattice, hence no join/widening, hence no compositional soundness.

This is the gap between "demo that fixes 7 seeded bugs" and "analysis you would trust on
an API."

**Recommendations:**

- Pull §5.9.4 (concrete-first / Daikon-lite) **forward, do not defer it.** Dynamic
  observations are the cheapest way to kill false positives from purely syntactic atoms,
  and the engine already runs the tests — the observations are nearly free.
- Make analysis-precision knobs (lattice height, k-CFA depth) KB-configurable so the
  soundness/cost tradeoff is explicit rather than frozen.

---

## §C.6 Concrete code-level issue — injective matching forbids self-relations

`_backtrack` enforces injectivity across *all* variables (rewriter.py:309–310:
`if node in used: continue`). A two-variable rule therefore can never bind
`?caller == ?callee`.

Consequence: `is_a.is_recursive derives when ?f calls ?f` (§5.4, §5.9.2) **cannot fire**,
and any reflexive interprocedural rule is dead on arrival. This will bite in Phase C.

**Recommendation:** add a per-rule `injective=False` flag (or special-case reflexive
relations) before writing interprocedural rules that touch recursion or self-edges.

---

## §C.7 Self-bootstrapping CNL rules from API code

Feasible, but not with the engine as-is: **it derives facts, not rules.** The monotone
fixpoint has no generalization/induction operator.

What fits the "active" framing (a Phase E, not currently sketched):

1. Run the engine on API code to collect `(observed atoms → test/behavior outcome)` pairs.
2. An LLM proposes candidate CNL rules generalizing those correlations (ILP-style
   hypotheses, but in human-readable CNL).
3. **The engine becomes the verifier** — exactly CEGIS (already cited in §5.0). Induced
   rules are quarantined, run against held-out examples, and promoted only on passing.

The uniform CNL representation is what makes this credible: induced rules are auditable,
not opaque weights.

Requirements the current spec lacks:

- negative examples and a generalization operator;
- a non-monotone *rule-management* tier (promote/retract induced rules) — which must live
  in the GC/maintenance tier, **not** the monotone reasoning fixpoint. (Fact-level
  retraction uses the §C.3 tombstone; *rule*-level retraction is an operational concern.)

---

## §C.8 Bridging business logic — the real payoff

The strongest part of the design: because a business invariant ("discount must never be
negative") and a structural observation ("this function `has_negative_return`") are both
CNL derivations over the same DM scopes, rules can chain *across the seam*:

```cnl
?f violates discount_floor derives when ?f computes discount AND ?f is a negative_output_function
```

Nothing in the §5.0 literature table does this. It is the genuinely new capability and
should stay front and center in how ASI is positioned.

---

## §C.9 Recommended priority order

1. **§C.6** injective-matching fix — small, unblocks recursion in Phase C.
2. **§C.3** retraction tombstone + NAC-override idiom — small, resolves the design
   tension, needs only authoring conventions.
3. **§C.2** atom-vocabulary contract + golden tests — defines the trusted kernel.
4. **§C.5** pull Daikon-lite forward — biggest precision lever.
5. **§C.4** Datalog-grade bulk evaluation — biggest scalability lever; do before any
   whole-codebase ambition.
6. **§C.7** self-bootstrapping (CEGIS) — last; depends on 1–5 being solid.
