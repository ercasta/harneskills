# §5 — Active Semantic Inference (ASI)

**Status:** Design spec — not yet implemented  
**Depends on:** §1–4, §13 (code generation layer)

---

## §5.0 Name and positioning

We call this framework **Active Semantic Inference (ASI)**.

- **Semantic** — the engine reasons about the *meaning* of a program (what it does, what it guarantees, what it can violate), not just its syntax.
- **Inference** — all semantic properties are derived via monotone fixpoint computation over causal rules, exactly as in Datalog-based program analysis.
- **Active** — the engine is not a passive query system. It drives its own knowledge acquisition: analysis is scheduled by the planner, executed as first-class tool actions, and feeds back into the fixpoint. The engine *wants* to understand a program because understanding is a precondition for the goals it has been given.

### Relationship to the literature

| Framework | Mechanism | Goal-directed? | Causal explanation? | Unified with action? |
|---|---|---|---|---|
| Datalog program analysis (Doop, CodeQL) | Monotone fixpoint over Horn clauses | No — passive query | No | No |
| Abstract interpretation (Cousot) | Fixpoint over abstract domains | No | No | No |
| Hoare / axiomatic semantics | Pre/postcondition proof rules | No | Partly | No |
| HTN planning | Goal decomposition + action scheduling | Yes | No | No |
| CEGIS (counterexample-guided synthesis) | Guess + verify loop | Yes | No | Partly |
| **ASI (this work)** | Monotone fixpoint + goal-directed planner | **Yes** | **Yes** | **Yes** |

The novel contribution is the **unity of analysis and action in a single goal-directed monotone loop**. The same engine that derives "this function is division-unsafe" also decides to apply `apply_zero_guard` and verifies the result, all driven by one objective function and one KB.

The causal chain is explicit and traceable end-to-end:

```
is_a.has_division_by_name              (observed: AST walker)
  → is_a.division_unsafe               (derived: CNL rule)
    → is_a.zero_guard_fix_needed        (derived: CNL rule)
      → apply_zero_guard scheduled      (planned: planner)
        → apply_zero_guard executed     (acted: dispatcher)
          → test_passed = True          (verified: run_tests tool)
```

Every arrow is a CNL rule or a planner decision. Nothing is a Python black box.

### On "causal semantics"

This is a fourth style of programming language semantics, complementing the three classical ones:

| Style | Describes | Expressed as |
|---|---|---|
| Operational | How programs execute (reduction steps) | Inference rules over configurations |
| Denotational | What programs mean (mathematical functions) | Domain equations |
| Axiomatic | What programs imply (pre/postconditions) | Hoare triples |
| **ASI** | **Why programs have properties, and what to do about them** | **Causal rules in CNL, evaluated by a goal-directed fixpoint** |

The distinguishing feature: ASI rules are simultaneously *explanations* (why is `f` broken?) and *instructions* (therefore do this). The KB is bidirectional in the same way the existing harness KB already is for parsing/generation — one set of rules, two directions of use.

---

## §5.1 The seam problem

The current architecture has an unavoidable seam at the Python/CNL boundary:

```
Python pre-classifier (black box)
  → emits is_a.division_unsafe
    → CNL: zero_guard_fix_needed derives when division_unsafe
      → planner schedules apply_zero_guard
```

The problem: `is_a.division_unsafe` is a collapsed conclusion. The Python tool has already decided it — the engine cannot inspect *why*. The two-step chain (has_division_by_name → division_unsafe) that the Python tool computed invisibly should instead be a CNL chain that the engine can trace, explain, and potentially override.

**The principle:** Python emits *atomic structural observations* (what is literally in the AST). CNL derives all semantic conclusions. No semantic reasoning happens in Python.

### Correct boundary

```
Python AST walker (structural observer — no semantic content):
  emits: is_a.has_division_by_name
         is_a.has_division_by_zero_literal  
         is_a.has_unguarded_raises
         is_a.has_negative_return
         (f, calls, g)                 ← call-graph edge

CNL Layer 2 (semantic derivation — no Python):
  division_unsafe derives when has_division_by_name
  definitely_division_unsafe derives when has_division_by_zero_literal
  exception_leaking derives when has_unguarded_raises
  negative_output_function derives when has_negative_return
  ... and interprocedural rules once call edges are supported
```

This eliminates the seam. The engine can explain the full causal chain. Python never reaches a semantic conclusion — it only observes structure.

---

## §5.2 CNL Form 11 — current state

**Form 11 already supports multi-condition AND and multi-variable binding.**

From `corpus_reader.py`, `_parse_derives_when` splits conditions on `' and '` and accumulates each condition into `lhs_branches`. All branches must match for the rewrite rule to fire. Variable binding across conditions works via `NT(var=...)` in conditions and `Ref(...)` in the conclusion.

The following is therefore **already parseable today**:

```cnl
?caller is a may_raise derives when ?caller calls ?callee AND ?callee is a raises_exception
```

This compiles to a `RewriteRule` with four LHS branches:
- `[NT("?caller", var="?caller"), T("calls")]`
- `[T("calls"), NT("?callee", var="?callee")]`
- `[NT("?callee", var="?callee"), T("is_a")]`
- `[T("is_a"), NT("raises_exception")]`

And the conclusion binds `?caller` via `Ref`:
- `[Ref("?caller"), T("is_a")]`
- `[T("is_a"), NT("may_raise")]`

**Verification required:** confirm that `rewriter.py`'s graph-join correctly handles the two-entity binding (`?caller` bound in branch 1, reused in branches 2 and 5; `?callee` bound in branch 2, reused in branches 3–4). This is the key implementation question before writing interprocedural CNL rules.

The `calls` relation is already in `RELATION_PHRASES` (it was added in a prior session). No parser extension is needed.

---

## §5.3 What does need to be built

### §5.3.1 — Analysis tools as engine actions (no pre-pass)

Currently, pre-classification runs *before* the engine loop. This must change: structural analysis becomes a tool the planner schedules.

```cnl
# corpus/structural_analysis.cnl

tool.analyze_function requires needs_analysis for ?func
tool.analyze_function causes analysis_complete
tool.analyze_function precondition_value is_a.function_entity

narrate.analyze_function is "Analysing {func_name}."
```

The tool runs the AST walker and writes structural `is_a` atoms back to the entity's DM scope. `_system2_expand` then fires, deriving semantic facts from those atoms. The planner can now schedule fix tools.

**Engine implication:** `_system2_expand` runs after every tool execution (already the case). No engine changes required for this step.

### §5.3.2 — Dynamic entity creation mid-loop

For interprocedural analysis, `analyze_function` on `f` may discover that `f` calls `g`, where `g` is not yet an entity in the DM. The tool must be able to create new entity scopes mid-run. Currently only the scenario setup creates scopes.

**Design:** tools return `new_entities` in their raw output alongside the usual delta. The inbound mapper (or a new `EntitySeedMapper`) writes them as new entity scopes. The engine then includes them in the next planner step.

```python
# Proposed tool output shape
{
    "patched": True,
    "new_entities": [
        {
            "function_name": "g",
            "source_file": "/path/to/g.py",
            "is_a": ["function_entity"],
            "fix_needed": True,
        }
    ]
}
```

The inbound mapper calls `dm.new_entity_scope()` for each entry and seeds it. The planner sees `needs_analysis` on the new scope and schedules `analyze_function` automatically.

**Engine change required:** `DomainModel.apply()` needs to handle `new_entities` in `ToolResult`. Small, isolated change.

### §5.3.3 — Propagating `needs_analysis` via call edges

Once call-graph edges are in the DM as triples `(caller_scope, calls, callee_scope)`, a CNL rule propagates the analysis goal automatically:

```cnl
# In structural_analysis.cnl
?callee is a needs_analysis derives when ?caller calls ?callee
```

This makes the fixpoint-driven exploration work: as the engine analyses `f` and emits call edges, the rewriter derives `needs_analysis` on each callee, the planner schedules `analyze_function` on them, and so on — until the entire reachable call graph is analysed. The engine implements the worklist algorithm without being told to.

**Note:** call edges must reference entity scopes, not function names, for this rule to fire. The AST walker must resolve callee names to existing entity scopes (or create new ones via §5.3.2) when emitting `calls` edges.

### §5.3.4 — Procedure summaries as entity-level facts

Once a callee is fully analysed, its properties should be available for callers to reason about. This is the **procedure summary** pattern from compositional program analysis.

In ASI terms: after `analyze_function` runs on `g`, entity `g`'s scope in the DM holds facts like `is_a.raises_ValueError`. When `f`'s caller analysis runs, the CNL rule:

```cnl
?caller is a may_propagate_exception derives when ?caller calls ?callee AND ?callee is a raises_ValueError
```

fires automatically during `_system2_expand`. The summary is not a separate data structure — it is the entity's DM scope, which is already a persistent store. No new mechanism is needed beyond §5.3.1–3.

**Scheduling:** For bottom-up ordering (callees before callers), the precondition on the caller's analysis tool should require callee summaries:

```cnl
tool.analyze_caller requires callees_analysed for ?func
tool.analyze_caller precondition_value is_a.all_callees_complete
```

Where `all_callees_complete` is derived via `all_complete` protocol once all callees have `analysis_complete`. The planner then naturally schedules leaves first without being explicitly instructed to.

---

## §5.4 Structural atoms — the observation vocabulary

The Python AST walker emits these atoms. No semantic content — only structural observations. CNL derives everything from here.

### Intra-function atoms

| Atom | Observed when |
|---|---|
| `is_a.has_negative_return` | A `Return` node whose value could be negative (e.g. `a - b`) |
| `is_a.has_division_by_name` | A `BinOp(Div)` whose right operand is a `Name` node |
| `is_a.has_division_by_zero_literal` | A `BinOp(Div)` whose right operand is `Constant(0)` |
| `is_a.has_division_by_assigned_zero` | Divisor is a `Name` that is assigned `0` earlier in the same function scope (single-pass constant propagation — no control-flow required) |
| `is_a.has_unguarded_raises` | Function body contains a call that can raise (detected from call target or existing `is_a.raises_*` facts on callee) |
| `is_a.has_no_try_except` | Function body has no `Try` node at top level |
| `is_a.is_leaf_function` | Function body makes no calls to user-defined functions |

### Call-graph atoms (interprocedural)

| Atom | Observed when |
|---|---|
| `(f, calls, g)` | Function `f`'s body contains a `Call` node targeting `g` |
| `is_a.is_recursive` | `(f, calls, f)` — self-call detected |

### Semantic derivations (CNL Layer 2 — not Python)

```cnl
# corpus/structural_semantics.cnl

# Intra-function semantic derivations
?f is a negative_output_function derives when ?f is a has_negative_return
?f is a division_unsafe derives when ?f is a has_division_by_name
?f is a division_unsafe derives when ?f is a has_division_by_assigned_zero
?f is a definitely_division_unsafe derives when ?f is a has_division_by_zero_literal
?f is a exception_leaking derives when ?f is a has_unguarded_raises AND ?f is a has_no_try_except

# Interprocedural semantic derivations
?caller is a may_raise_exception derives when ?caller calls ?callee AND ?callee is a raises_exception
?caller is a division_unsafe derives when ?caller calls ?callee AND ?callee is a may_return_zero
```

Note: `exception_leaking derives when has_unguarded_raises AND has_no_try_except` is a two-condition rule. This is a concrete use of multi-condition AND that's already supported (§5.2).

---

## §5.5 The active analysis loop — full picture

```
SEED: function_entity entities with needs_analysis, function.file, function.name
      Call graph: unknown (to be discovered)

LOOP:
  1. Planner sees is_a.needs_analysis + requires needs_analysis on analyze_function
  2. analyze_function executes:
       - AST walks function.file, function.name
       - emits structural atoms to entity DM scope
       - emits (scope, calls, callee_name) triples → inbound mapper resolves to scopes
       - if callee has no entity scope: creates one via new_entities, seeds needs_analysis
  3. _system2_expand fires:
       - derives semantic facts from structural atoms
       - derives needs_analysis on newly discovered callees
       - derives all_callees_complete when all callees have analysis_complete
  4. Planner sees new eligible actions:
       - analyze_function on newly seeded callees
       - fix tools on entities where fix strategy is derived
  5. Repeat until goal_reached or impasse

GOAL: all function_entity must have test_passed
```

The worklist is implicit — the fixpoint and the planner ARE the worklist. No explicit queue management.

---

## §5.6 New CNL files

| File | Layer | Purpose |
|---|---|---|
| `corpus/structural_analysis.cnl` | 3 | Tool rules for `analyze_function`, goal, narration |
| `corpus/structural_semantics.cnl` | 2 | Derives-when rules from structural atoms to semantic properties |
| `corpus/structural_properties.cnl` | 2 | Interprocedural rules using `calls` relation |

The existing `python_semantics.cnl` and `python_bugs.cnl` migrate their pre-classified `is_a` seeds to become CNL derivations from the new structural atoms. The Python pre-classifier (`_classify_pytest_failure`) becomes a thin structural observer.

---

## §5.7 Implementation phases

### Phase A — Structural ingester (intra-function, no interprocedural)

1. Write the AST walker in `corpus/demos/python_bugfix.py` that emits structural atoms.
2. Write `corpus/structural_semantics.cnl` with intra-function derives-when rules.
3. Move pre-classification from Python to CNL: `_classify_pytest_failure` becomes an emitter of atoms only.
4. Verify that existing 990 tests still pass (behaviour unchanged — different path to same facts).
5. Verify multi-condition AND in the rewriter by adding `exception_leaking derives when has_unguarded_raises AND has_no_try_except` and testing it.

### Phase B — Analysis as engine action

1. Refactor `analyze_function` from pre-pass into a registered tool.
2. Seed entities with `is_a.function_entity` and `needs_analysis` only — no pre-analysis.
3. Extend `DomainModel.apply()` to handle `new_entities` in tool output.
4. Write `corpus/structural_analysis.cnl` with tool rules.
5. Extend tests: the engine loop should now include `analyze_function` steps before fix steps.

### Phase C — Interprocedural call graph

1. AST walker emits `(scope, calls, callee_scope)` triples (creating new scopes via §5.3.2 as needed).
2. Verify that the rewriter correctly handles two-entity binding in `derives when ?caller calls ?callee AND ?callee is a X` rules (read and test `rewriter.py`).
3. Write `corpus/structural_properties.cnl` with interprocedural derives-when rules.
4. Add multi-function test scenarios that verify interprocedural fact propagation.

### Phase D — Procedure summaries and bottom-up scheduling

1. Add `all_callees_complete` derivation via `all_complete` protocol on `analysis_complete`.
2. Add `analyze_caller` tool with `requires callees_analysed` precondition.
3. Test: callee with `raises_exception` causes caller to derive `may_propagate_exception`.
4. Test: planner naturally schedules leaves before callers (no explicit ordering code).

---

## §5.8 What does NOT change

- The engine loop (`_run_loop`, `_system2_expand`) — no structural changes.
- The planner — no changes; analysis tools are just tools.
- The KB grammar and Form semantics — no new forms required (multi-condition AND already works).
- The existing bugfix and generation scenarios — migrate to the new atom-based seeding in Phase A without changing observable behavior.
- The 27 CNL Forms — sufficient as-is.

The only engine change is `DomainModel.apply()` accepting `new_entities` (§5.3.2). Everything else is CNL authoring and Python tool refactoring.

---

## §5.9 Open questions

1. **Rewriter join semantics** — the critical unknown. Does the rewriter correctly bind `?caller` and `?callee` as distinct variables in a single rule and join the two sets of triples? Must be verified against `rewriter.py` before Phase C.

2. **Cyclic call graphs** — the `calls is transitive` declaration (Form 17) would handle transitivity, but for recursive functions the fixpoint must terminate. The rewriter's `max_steps` limit on `RewriteRule` is the safety valve; verify it applies to interprocedural rules.

3. **Scope identity for callees** — when the AST walker sees `f` calls `g`, it needs to map the name `"g"` to an entity scope. If `g` is in a different file, the scope doesn't exist yet. The `new_entities` mechanism (§5.3.2) handles this, but the walker needs a scope registry to avoid creating duplicate scopes for the same callee.

4. **Concrete-first execution** (spec §14, "Daikon-lite") — running the function with test inputs and observing actual values is complementary to static structural analysis. This remains a separate future direction; ASI Phase A–D is purely static.
