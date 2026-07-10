# Design — a CNL surface for authoring planning operators, state, and goal (2026-07-06)

> **Status: IMPLEMENTED (first slice)** — `harneskills/planning_kb.py`
> (`load_planning_kb`, `PLANNING_KB_FORMS`), example `corpus/coffee_kb.cnl` +
> `examples/coffee_cnl.py`, tests in `tests/test_new_core.py`. Reproduces
> `examples/coffee.py` from a `.cnl` file. Read `docs/planning_design.md` first.

## The gap this fills

The planning loop (`planning.py`) runs over three kinds of monotone FACT — an operator's
preconditions/effects/cost, the observed state, and the goal — but a *problem instance* could
only be authored in Python (`seed_operator` / `seed_state` / `seed_goal`). This is the CNL
surface for the SAME edges, so a whole instance lives in one `.cnl` file and is handed straight
to `planning.solve`. Nothing about the planner changes; only the *authoring* moves out of Python.

## The target edges (unchanged)

| Thing | Edge(s) the seeder produces |
|---|---|
| operator precondition | `O --pre--> C` |
| operator effect (add) | `O --add--> C` |
| operator effect (delete) | `O --del--> C` |
| operator cost (criterion) | `O --cost--> "n"` (cost is an OPAQUE node named `n`) |
| operator external cost | `O --needs_price--> <yes>` |
| current state | `<now> --true--> C` |
| goal | `<goal> --want--> C` |

Conditions `C` are SHARED nodes (get-or-create by name), so one condition named by two
operators is one node the planner joins on.

## The sentence forms (chosen surface)

Single-token operator / condition names (the planner's own convention — `make_coffee`,
`have_coffee`), one fact per line:

| CNL | Edge |
|---|---|
| `make_coffee needs water` | `make_coffee --pre--> water` |
| `make_coffee produces have_coffee` | `make_coffee --add--> have_coffee` |
| `make_coffee removes water` | `make_coffee --del--> water` |
| `make_coffee costs 3` | `make_coffee --cost--> "3"` |
| `fetch_water is priced` | `fetch_water --needs_price--> <yes>` |
| `we have water` | `<now> --true--> water` |
| `we want have_coffee` | `<goal> --want--> have_coffee` |

`we have …` / `we want …` are a symmetric state/goal pair. `costs X` is CRITERION-AGNOSTIC:
the cost object is opaque (vision §1), exactly as `seed_operator(cost=)` — see graded note below.

## What was reused vs added

**Reused.** The whole approach mirrors `procedure.py`: dedicated recognition FORMS
(graph-rewrite rules, like `PROCEDURE_FORMS`), parsing each line in its OWN throwaway graph
(an interaction, like `query.ask` / `parse_procedures`), then a mechanical §8 reader that
transfers the recognized triples into the real graph BY NAME through `planning._hub`
(get-or-create) — which is where node-sharing happens. The forms are bare-triple forms in the
same idiom as `authoring.FACT_FORMS` (a leading subject token + a bound-literal keyword +
object, with a last-token NAC). Nothing in the engine or planner changed.

**Added.** `harneskills/planning_kb.py`:
- `PLANNING_KB_FORMS` — seven forms (pre/add/del/cost/priced/state/goal), each folding a
  surface line into the exact target triple. The operator/goal SEMANTICS live in these forms
  (data/CNL), not Python branches.
- `load_planning_kb(text, graph=None) -> Graph` — the entry point (below).
- One mechanical detail worth noting: the goal keyword `want` collides in NAME with the target
  predicate `want`, so the surface token `want` is a node named `want` distinct from the emitted
  relation. The reader skips any relation whose subject/object is a surface-chain node
  (`first`/`next`/`<sentence>`), which drops that one spurious reading. It is the only
  keyword/predicate collision.

## Integration contract (what the TUI calls)

```python
from harneskills import load_planning_kb   # also: harneskills.planning_kb.load_planning_kb
g = load_planning_kb(kb_text)              # build/seed a graph from CNL
planning.solve(g, ...)                     # run the unchanged planning loop
```

`load_planning_kb(text, graph=None)` creates a graph if none is given, or seeds into an existing
one (so operators/state/goal can be layered, or added to a graph that already holds rules). Lines
starting with `#` and blank lines are ignored; an unrecognized line contributes nothing (silently
skipped — controlled recognition, matching `parse_procedures`).

## Graded-friendliness (means-selection)

The constraint was not to bake a scalar-only cost path. The `costs X` form lowers the datum
OPAQUELY (`O --cost--> "X"`, a node named `X`), exactly as `seed_operator(cost=)` does. Today the
`rank_by_cost` §8 tool parses those names as floats and emits `cheaper_than` facts the commitment
rules select over; a *graded* criterion (e.g. `costs cheap`, or a `prefers`/`is cheap` surface
compared by a fuzzy tool) is a drop-in TOOL change with NO grammar change — the surface already
carries the criterion opaquely and the selection logic stays in rules. So the surface is aligned
with `docs/graded_means_selection_design.md`'s direction rather than committed to scalars.

## Verification

`test_planning_kb_cnl_reflects_to_python_seeders` asserts the coffee KB lowers to the EXACT edge
set of `examples/coffee.py`'s seeders; `test_planning_kb_plan_and_solve_reach_the_goal` runs
`plan`/`solve` from the CNL graph (cheapest producer chosen, costlier dominated, dead option dies,
goal reached). `del` / `is priced` / `we have` are covered separately.

## Limitations / handoffs (grow from here)

- **Single-token names** for operators and conditions (the planner's convention; multi-word
  conditions want the n-ary / NP-decomposition work — the same gap `procedure.py` documents). A
  multi-token object is left UNRECOGNIZED (reported by absence), never mis-parsed.
- **One precondition/effect per line.** Author several lines — they share condition nodes by name.
  A conjunctive `needs water and beans` surface is a natural follow-up (reuse the `and` domino).
- **State/goal surface** is `we have …` / `we want …`. The noted equally-natural alternative for
  the goal is `the goal is C` (needs a two-token `the goal` lead + determiner handling); `we want`
  was chosen for symmetry with `we have` and because it needs no determiner machinery.
- The loader parses per-line in a throwaway graph (like `parse_procedures`); it is NOT routed
  through `Session`. `Session` is the incremental NL-assert path (coref/detection/pronouns) — a
  different job. If a future TUI wants operators asserted line-by-line INTO a Session KB, the
  forms here can be registered as recognition forms there; deferred until needed.
