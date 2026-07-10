# Design — goal → plan → act → replan, entirely as rules (2026-06-28)

> **Status: IMPLEMENTED + RANKED COMMITMENT (2026-06-29)** — `harneskills/planning.py`,
> `examples/coffee.py`, 10 tests in `tests/test_new_core.py` (46 green). All four
> "decisions made" below are realized; the act/observe boundary is a single tool
> (`act`). **Phase C is now multi-option RANKED commitment** (see phase C below): the
> `rank_by_cost` §8 tool emits `cheaper_than` facts and the `dominated`/`best`/`choose`
> rules select the cheapest viable op — criterion in facts, gadget enacts. Read
> `docs/vision.md` (§4 stupid planner, §5 two layers, §6 token passing,
> §13 graded layer) first. **Two design refinements found during implementation:**
> (1) markers must use DISTINCT relation predicates (`O --viable--> <yes>`, not
> `O --is--> viable`) — `stratify` is predicate-NAME granular, so overloading one `is`
> predicate makes it see a false `block↔viable` negation cycle and raise; (2) a SINGLE
> stratified pass does not compute the reachability fixpoint (reach_effect feeds
> reachable feeds block/viable, a cycle through negation), so the driver LOOPS the
> stratified bank until the edge set is stable — stratification only fixes the
> within-step NAC race; the outer loop is the semi-naive iteration. Full notes and known
> limitations in `docs/CHANGELOG.md` (arc history: `docs/attic/handoff_redesign.md`).

The north star: **the planner stays stupid** — it only fires enabled rules. "Planning"
is not a search algorithm we write; it is a *computation that emerges* from a rule bank
rewriting the graph. The whole loop rides the two-layer split: a **monotone fact layer**
(domain causal knowledge + observed state) under a **non-monotone control layer** (the
planning scaffolding) that we freely build up and tear down. Replanning *is* tearing
down control and letting the rules re-fire.

The existing **ice cream** domain is the degenerate case of this: reactive, 1-step
routing. This is its multi-step generalization on the same engine.

---

## Vocabulary (all nodes + relations — nothing typed)

| Thing | Encoding | Layer |
|---|---|---|
| **Condition** (a fact that can hold) | a node, e.g. `have_coffee`, `at_home` | — |
| **Current state** | `<now> --true--> C` for each holding condition | fact (observed) |
| **Operator** (domain causal knowledge) | node `O`; `O --pre--> C`, `O --add--> C`, `O --del--> C`, `O --cost--> n` | fact (authored) |
| **Goal** | `<goal> --want--> C0` | seed |
| **Need / subgoal** | `<need> --for--> C` | control |
| **Reachable** | `C --is--> reachable` (connects to current state) | control |
| **Block** | `O --blocked_by--> C` (an unmet precondition) | control |
| **Viable option** | `O --is--> viable` | control |
| **Committed step** | `O --is--> chosen`; ordering `O1 --before--> O2` | control |
| **Execution cursor** | `<exec> --ready--> O`, `O --is--> done` | control |
| **Replan trigger** | `<replan>` present | control |

---

## The rule chain — five phases, one bank (`PLANNING_RULES`)

### A. Relevance — backward from the goal (which operators even matter)
- `expand_goal`:  `<goal> --want--> ?c`  ⇒  `<need> --for--> ?c`   *(NAC: need already exists)*
- `offer_options`:  `<need> --for--> ?c`, `?o --add--> ?c`, `?o --pre--> ?p`  ⇒  `?o --candidate--> ?c`, `<need> --for--> ?p`   *(NAC dedups needs)*

Sprays out the **AND-OR tree**: every operator that *could* produce a need is a
candidate (OR-branches = the "options"); each one's preconditions become fresh needs
(AND-branches). Terminates because needs are per-condition and deduped → finite.

### B. Connection — forward from the current state (which options actually reach back)
- `ground_state`:  `<now> --true--> ?c`  ⇒  `?c --is--> reachable`
- `block`:  `?o --candidate--> ?g`, `?o --pre--> ?p`  ⇒  `?o --blocked_by--> ?p`   *(NAC: `?p --is--> reachable`)*
- `unblock` *(control retraction)*:  `?o --blocked_by--> ?p`, `?p --is--> reachable`  ⇒ **drop** `?o --blocked_by--> ?p`
- `viable`:  `?o --candidate--> ?g`  ⇒  `?o --is--> viable`   *(NAC: `?o --blocked_by--> ?anyp`)*
- `reach_effect`:  `?o --is--> viable`, `?o --add--> ?c`  ⇒  `?c --is--> reachable`

**The technical crux.** "**All** preconditions met" is a universal, which a single
positive NAC cannot state. The idiom: assert a `blocked_by` marker per *unmet*
precondition, **retract** it (control layer!) as that precondition becomes reachable,
and declare the operator viable only when *no* block remains (single-pattern NAC).
Reachability then flows forward through viable operators. **An option that never
connects to the current state keeps a block that never clears → never viable →
silently dies.** That is "only one connects," with no backtracking.

### C. Commitment — pick the cheapest chain (RANKED, 2026-06-29)
- `dominated`:  `?o --viable--> <yes>`, `?o --add--> ?c`, `?x --viable--> <yes>`, `?x --add--> ?c`, `?x --cheaper_than--> ?o`  ⇒  `?o --dominated--> <yes>`
- `best`:  `?o --viable--> <yes>`  ⇒  `?o --best--> <yes>`   *(NAC: `?o --dominated--> <yes>`)*
- `choose`:  `<need> --for--> ?c`, `?o --best--> <yes>`, `?o --add--> ?c`  ⇒  `?o --chosen--> <yes>`   *(NAC: some op already chosen for `?c`)*
- `order`:  `?o1 --chosen--> <yes>`, `?o2 --chosen--> <yes>`, `?o1 --add--> ?c`, `?o2 --pre--> ?c`  ⇒  `?o1 --before--> ?o2`

When several options are viable, **selection is not search** — it is the standing
guardrail made concrete: the CRITERION lives in the **fact layer** (operator `cost`),
and the control gadget only ENACTS the exclusion. The hard comparison is offloaded to
the **`rank_by_cost` TOOL** (§8): it reads the opaque `cost` datum-nodes (`O --cost-->
"n"`), compares them, and emits the *result* — `O1 --cheaper_than--> O2` FACTS. The
rules then SELECT over that result: `dominated` = a cheaper *viable* rival exists, `best`
= viable ∧ ¬dominated, `choose` commits one best per need. With a total cost order this
picks exactly one; **equal costs dominate neither rival → both `best` → both commit, an
HONEST tie** (choosing among true equals with *no* criterion would be fabrication, not
control). `cheaper_than` is a derived FACT (survives replan); `dominated`/`best` are
control. The `chosen` + `before` edges *are* the plan, a DAG sitting in the graph.

> **Why a tool, not a rule, for the comparison** (rejected Alt-3 revisited): comparing
> two opaque cost names is arithmetic on datum-nodes (vision §1) — exactly a calculator's
> job (§8). The tool emits only relational *results* (`cheaper_than`); the SELECTION
> logic ("cheapest = not-dominated") stays in rules, so the decision is never buried in
> the tool. This generalizes: an arbitrarily complex comparison (scores, weights,
> lexicographic keys) lives inside the tool and surfaces as facts the rules pick over.

### C'. External cost lookup — rules DEMAND a value, a tool FETCHES it (2026-06-29)
Cost need not be authored in the KB; with `seed_operator(..., priced=True)` it lives
OUTSIDE (a price DB / web call) and is fetched ON DEMAND. The rule layer never calls the
tool (§12.5) — they handshake through nodes, the same pattern as `<exec> --ready--> O` /
`act`, generalized to the *knowledge* boundary (the dumb dispatcher of §6):

    a RULE emits a REQUEST token  →  the DISPATCHER runs the registered TOOL  →
    the tool emits RESULT / ERROR nodes  →  RULES fire on the results.

- `request_price`:  `?o --viable--> <yes>`, `?o --needs_price--> <yes>`  ⇒  `<price-request> --want--> ?o`   *(NAC: `?o --price_known--> <yes>`)*
- dispatcher `service_requests` runs `price_handler(db)`: dereferences the op's NAME against the opaque `db`, emits a `price` result FACT (or `<error>`), sets `price_known`, consumes the request token.
- `cost_settled`:  `?o --price_known--> <yes>`  ⇒  `?o --cost_settled-->`  ; OR  `?o --viable-->` *(NAC `?o --needs_price-->`)*  ⇒  `?o --cost_settled-->`  *(static/no-cost path)*. BOTH `dominated` and `best` now require `cost_settled` so commitment WAITS for the cost to exist (the dispatcher services requests after the rule pass) — and waits for FRESH prices on replan.
- `failed_yields_to_priced`:  `<price-request> --failed--> ?o`, a viable cost-settled rival for the same need  ⇒  `?o --dominated-->`   *(the specific error policy over the generic `<error>` node)*.

**Freshness is §5, not deletion.** A re-fetch emits a new result and wires `Rnew
--supersedes--> Rold` (an *added* marker); "current" = the result nothing supersedes,
read through a guard. The old fact is never deleted. A replan re-validates (teardown
clears `price_known` → re-ask → re-fetch); a superseding fetch invalidates the
`cheaper_than` incident to that op so the comparator re-derives. See `harneskills/
external.py`, `examples/coffee_external.py`. This is the first working instance of the
deferred tier-(b) `<retracted>`/supersedes machinery.

### D. Acting — token-passing execution (the §6 domino gadget, already proven)
- `fire_ready`:  `?o --is--> chosen`, every `?o --pre--> ?p` has `<now> --true--> ?p`  ⇒  **tool boundary**: actually perform `O`, assert observed `<now> --true--> ?c` for its effects, mark `?o --is--> done`, advance the cursor.

Execution is the same `<current>`-token advance as `test_homomorphic_token_passing_loop`
— the cursor walks the `before`-ordered chain. Two tool calls bound the loop: *do the
action* and *observe the result*. Everything else is rules.

**Real action tools — DONE (2026-06-29).** `act(graph, *, actions, failures)` now backs the
boundary with REAL §8 tools: for `<exec> --ready--> O`, if `actions[op_name]` is registered
it performs externally and emits the OBSERVED effect (which may differ from the operator's
DECLARED `add`); otherwise `simulate_effects` materializes the declared effect (the prior
behavior, kept for un-backed ops + tests). This mirrors the lookup boundary (`external.py`):
lookups READ the outside world, actions WRITE it and observe. Crucially it makes
**divergence real** — expected (declared) vs observed (what the tool reports) — so
`detect_divergence → replan` is driven by reality, not only the `failures` injection. The
`observe(added, removed)` helper builds a tool with a fixed observed effect (matching the
plan = success; differing = divergence). `solve(..., actions=...)` threads them through.

### E. Divergence → replan (the two-layer payoff)
- `detect_divergence`:  `?o --is--> done`, `?o --add--> ?c`  ⇒  `<replan>`   *(NAC: `<now> --true--> ?c` — expected effect didn't materialize)*; plus a variant for a chosen-but-not-done op whose precondition silently went false.
- `replan` *(control teardown)*:  `<replan>` present  ⇒ **drop** all control markers (`need/reachable/blocked_by/viable/candidate/chosen/before/cursor`), keep facts + updated `<now>` + `<goal>`.

The plan lives entirely in the **deletable control layer** while world state and
operators are **monotone facts**, so replanning is just *"drop the scaffolding; the same
rules re-fire from the new state."* No special replanner — observing a divergence and
clearing control automatically re-runs A→D against reality.

---

## How this honors the vision
- **Stupid scheduler**: every rule is local fire-when-enabled; no beam search, no HTN. Planning is the fixpoint.
- **Options without backtracking**: dead branches aren't pruned by a searcher — they never reach `viable`. Monotone, no rollback.
- **"Think harder" = radius**: regression/reachability explores within `radius` hops of the goal/frontier; a deeper plan is a bigger N.
- **Tools only at the world boundary**: act + observe. Reasoning never leaves the substrate.

---

## Decisions made (chosen path)
1. **Search shape = HYBRID**: backward relevance (phase A) + forward connection (phase B).
2. **"All preconditions met" = the `blocked_by` + NAC + control-retraction idiom** (phase B).
3. **Plan = explicit `chosen` + `before` edges in the graph** (not journal-extracted).
4. **Replan = full control teardown** first (partial repair is a later optimization).

---

## Alternatives NOT chosen (recorded for future review)

### Alt-1 — Search shape: pure-forward reachability *(rejected)*
Drop phase A entirely; from `<now>` mark reachable, fire any operator whose preconditions
are all reachable, mark its effects reachable, stop when the goal is reachable; extract
the plan by back-tracing. **Pro:** simplest, fully monotone, maximally "stupid-scheduler"
(just a closure). **Con:** explores *every* operator in the domain regardless of relevance
to the goal — blows up in large domains; computes a reachability graph far bigger than the
plan. **Revisit if:** domains stay small, or we want the full planning-graph (relaxed
reachability) as a heuristic/admissible distance estimate to *guide* selection in phase C.

### Alt-2 — Search shape: pure-backward regression *(rejected)*
Only phase A, extended so "solved" propagates *up* the AND-OR tree: a need is solved if
true-in-state OR some operator achieving it has all its sub-needs solved; the top goal
solved ⇒ plan exists. **Pro:** strictly goal-directed, never touches irrelevant operators.
**Con:** the upward "all sub-needs solved" propagation is the same universal-quantifier
problem as phase B *and* needs explicit **cycle handling** (op A needs B, op for B needs A)
via visited-markers/NAC to avoid non-termination; more fragile than letting forward
reachability settle the connection. **Revisit if:** the forward sweep in phase B proves
too broad and we want connection computed purely along the relevant tree.

### Alt-3 — "All preconditions met": counting / aggregation *(rejected for now)*
Instead of `blocked_by` markers, count an operator's preconditions and count how many are
reachable; fire `viable` when the two counts match. **Pro:** arguably more direct; one
marker per op instead of one per unmet precondition. **Con:** requires **arithmetic on
datum-nodes** — numbers are nodes named "3", parsed only by a calculator tool (vision §1) —
so it pulls a tool into the inner planning loop and needs the not-yet-built datum-node
encodings. The `blocked_by` idiom stays purely structural (NAC + control retraction), no
arithmetic. **Revisit when:** datum-node arithmetic tools exist and we want numeric plan
metrics (cost sums, lengths) anyway.

### Alt-4 — Plan representation: extract from the firing journal *(rejected)*
Don't materialize `chosen`/`before` edges; recover the plan by reading the append-only
journal (which operator-firing grounded the goal), like `surface.explain` does for
derivations. **Pro:** no extra control edges; reuses provenance we already record.
**Con:** execution and replanning would have to operate on a *journal trace* rather than on
**graph structure** — harder to walk with a cursor token, harder to tear down selectively,
and the journal mixes exploration firings with committed ones. Explicit edges keep
everything in the one substrate that rules can match on directly. **Revisit if:** we want a
read-only "explain the plan" view distinct from the executable plan (could use *both*:
edges to execute, journal to narrate).

### Alt-5 — Replan granularity: partial repair *(deferred, not rejected)*
On divergence, keep the still-valid plan prefix (steps already `done` and steps whose
preconditions still hold) and only re-plan the broken suffix. **Pro:** cheaper, more
stable execution, avoids redoing work. **Con:** must precisely scope which control markers
to drop vs. keep, and prove the kept prefix is still sound under the new state — real
complexity. Full teardown is trivially correct. **Plan:** ship full teardown first, add
partial repair as an optimization once the loop is proven.

---

## Proposed first implementation slice (when resumed)
- A `harneskills/planning.py` module exposing `PLANNING_RULES` (phases A–E) as a `Rule`
  bank, plus tiny seed helpers (`seed_operator`, `seed_state`, `seed_goal`).
- A worked example `examples/coffee.py`: conditions `have_coffee`, `water`, `beans`;
  operators `make_coffee`(pre water,beans; add have_coffee), `fetch_water`(add water),
  `get_beans`(add beans); state empty; goal `have_coffee`.
- Tests in `tests/test_new_core.py`:
  1. plan exists — `make_coffee --is--> chosen`, ordered after `fetch_water`/`get_beans`;
  2. a dead option (an operator whose precondition is never reachable) stays non-viable;
  3. execution drives `<now> --true--> have_coffee`;
  4. inject a divergence (an effect fails to appear) → `<replan>` fires → control torn
     down → a fresh plan re-derived.
- Keep the act/observe boundary as plain Python stubs first (simulate); promote to §8
  tools later.

## Pointers
- This doc is the resume point for the planning loop; the active plan is
  `docs/implementation_plan.md`. Memory: `decision_one_substrate_vision.md`.
