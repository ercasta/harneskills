# Handoff — current state and next step

> The live resume point for the one-substrate rebuild. Read `docs/vision.md` (design
> philosophy), `docs/vision_agentic.md` (the code / business-semantics / SLM application
> direction — CANONICAL as of 2026-07-04), and `docs/architecture.md` (system as built)
> first. Full history is in `docs/CHANGELOG.md`. This file stays SHORT — only the current
> state and the immediate next step. When work lands, summarize it in `CHANGELOG.md` and
> update this file's "next step"; do not append a running log here.
>
> **Direction reoriented 2026-07-04.** A first-principles design conversation
> (`docs/discussion/discussion.md`) independently re-derived the substrate we built and
> mapped what it is *for*: a deterministic reasoning substrate serving small language
> models in agentic coding. The synthesis is `docs/vision_agentic.md`. The reasoning-
> expressiveness and NL-surface arcs below are **not abandoned** — they are re-slotted as
> supporting work under that direction, and re-prioritized accordingly (see "Next step").

## Current state (2026-07-07)

> **LATEST — 2026-07-07 (session 8), 423 tests green. HONEST GATE both speed parity wins DONE
> (seed-from-ground + semi-naïve delta), PLUS deeper walker integration (a deferred non-arc slice).**
> The ISA arc is SEMANTICALLY complete (Phase 0–3); the gate is production parity so `GoalSolver` can
> retire `rewriter.run` (the reference proves SEMANTICS, not SPEED). Slice 1 (seed-from-ground, prior
> session) cut n=80 tabling 107s → 15s; this session landed slice 2 (semi-naïve delta) AND, since both
> speed wins removed the asymptotics block, the first deferred non-arc slice (walkers). Everything
> additive in `harneskills/isa/{goal,walker}.py`, NO shipped-engine change, uncommitted on top of
> `a31e264`. What landed:
> - **Deeper walker integration** (`harneskills/isa/{walker,goal}.py`; `tests/test_isa_goal_walker_linear.py`,
>   8 tests). (a) LINEAR RECURSION over a DIFFERENT base: `_closure_bases` maps a derived relation that is
>   the transitive closure of a base (`anc(a,b):-parent(a,b)`, `anc(a,c):-parent(a,b),anc(b,c)`, left- or
>   right-recursive) → that base, and `Walker` gained `mint_rel` so it WALKS `parent` while materializing
>   the shortcut AS `anc`; walkable only when the derived relation's rules are EXACTLY {base, step} (else
>   fall back to tabling — a base-edge walk can't see other contributors). (b) A walker for an INTERIOR
>   ground reachability subgoal (the `_walk_applicable` check moved into the fixpoint loop), so a body
>   clause `anc(?x,?y)` with both ends SIP-bound lands on a walker, not the tabled chain. Plus the
>   soundness fix it surfaced: a transitive-closure walker answers ≥1 hop, so reflexive `rel(a,a)` holds
>   ONLY via a real cycle (the old 0-hop short-circuit was latently unsound). Differential-tested vs
>   tabling incl. a 300+-pair random sweep over cyclic `parent` graphs.
> - **Semi-naïve delta evaluation (parity win 2).** `solve` was a naive `while changed` fixpoint that
>   re-joined every demanded goal's WHOLE body every round, rediscovering answers it already had (the
>   O(rounds) round-churn keeping the curve ~O(n^3.8)). Now a goal's body is joined in FULL exactly once
>   — its first evaluation, the seed (`self._full_joined`) — and thereafter only against the previous
>   round's DELTA (`self._delta_by_rel`) via `_delta_join`/`_delta_matching` (the classic delta-
>   substitution: each body clause takes a turn drawing from the delta while the others stay full). Work
>   becomes ~proportional-to-derivations, not rounds × closure.
> - **The careful part — dual-channel delta — handled.** Answers flow through BOTH the join tables AND
>   the graph side-channel (`_facts_matching` reads materialized facts across DIFFERENT table entries on
>   the same relation). Correctness is kept by folding EVERY table growth into `next_new` — whether a
>   join derived it OR `_facts_matching` picked up a cross-materialized graph fact — so the delta
>   propagates through both channels and no derivation is dropped (the arc's "correctness never traded").
> - **MEASURED + PROVEN answer-preserving.** n=50 2.27s → 0.59s, **n=80 15s → 2.9s** (~5× on top of
>   slice 1, ~37× vs the original 107s); exponent ~O(n^3.8) → ~O(n^2.9), one full power of n gone.
>   `tests/test_isa_goal_semi_naive.py` (3): a RANDOMIZED differential test sweeps >1000 goals across
>   ~25 random interacting-rule programs (transitivity + linear recursion over a DIFFERENT base relation
>   + a two-relation join) and asserts each demand-driven answer equals the FORWARD CLOSURE
>   (`run_to_fixpoint`, the independent oracle) filtered to that goal — the strong catch for a silent
>   dropped delta; plus a structural pin (`solver.full_joins <= #demanded goals`, non-flaky proof the
>   round-churn is gone). All 415 tests green; suite got FASTER (48s → 38s).
> - **RESUME HERE → the honest gate is no longer blocked on asymptotics.** Both speed wins are in and
>   the first deferred non-arc slice (walkers) is done. The remaining move to actually RETIRE
>   `rewriter.run` is a re-hosting + deletion pass (port provenance/tools/the driver onto `GoalSolver`,
>   run the whole shipped suite through it, delete the `rewriter.py` matcher / NAC branch /
>   `graded_degree` / propagate handler) — a substantial, scope-with-the-user pass, not a quick edit. OR
>   keep `GoalSolver` as the reference and `rewriter.run` as production and pick up a remaining deferred
>   non-arc slice (in-graph-nodes-vs-rebuildable-bytecode fork; FUZZY over an ANN index / Tier-4
>   hub-flooding). Detail: `isa-reference.md` "Semi-naïve delta" + "Next slice".

> **PRIOR — 2026-07-07 (session 6), 407 tests green. ISA ARC — PHASE 3 DONE: the GOAL-DIRECTED PLANNER
> runs end to end on a NON-TOY bank** (plan → act/observe → replan), demand-forward, differential-tested
> against `planning.solve`, incl. the §8 rank `<call>` tool serviced goal-directed and the card-trader
> stress case. Everything additive in `harneskills/isa/`, NO shipped-engine change. What landed
> (`harneskills/isa/solve.py`; `tests/test_isa_solve.py` 16, `tests/test_isa_solve_cards.py` 4):
> - **The §8 rank `<call>` tool serviced GOAL-DIRECTED** (Phase-3 item 1). `GoalSolver` gained a `tools`
>   registry mapping a TOOL-BACKED relation → a calculator `f(ag)`: when a subgoal on that relation is
>   first demanded, the calculator runs ONCE and the demand reads the facts it minted. `cheaper_than` is
>   backed by `rank_cheaper_than` (AttrGraph-native cost comparison), so a `dominated` subgoal demands the
>   ordering → the tool mints `cheaper_than` → `dominated`/`best` complete. So a COST preference (chain
>   step 1) now breaks a tie by cost, not the arbitrary fallback — the full `examples/coffee.py` (fetch(1)
>   beats deliver(5), dead buy_latte pruned, multi-need commitment) reproduces `plan()` exactly.
> - **The CARD-TRADER stress case** (Phase-3 item 2, the non-toy target). `run_to_goal` drives the real
>   `cards_frontier_kb.cnl` + value→plan bridge + full `POLICY_RULES` deontic override: the value→plan
>   BRIDGE (reasoning DERIVES an operator effect `?o add have_valuable when …`) is observed by the act
>   loop via demand-forward add-resolution (`_observe_simulated` demands `add(op, ?)` so DERIVED effects
>   are observed, not just base); OBJECT-SCOPED deontic exclusion (a predicate-NAC completion) and its
>   defeasible OVERRIDE both work on the demand path. `tests/test_isa_solve_cards.py` (value goal,
>   exclusion, override, forward parity on the clean scenario).
> - **PHASE 3 CORE** (plan → act/observe → replan), landed earlier this session:
> - **`derive_plan` — demand-forward plan derivation.** Drives the REAL `PLANNING_RULES` through
>   `GoalSolver`: demands `best` (which transitively pulls need/candidate/viable/cost_settled/dominated
>   ONLY along the goal's AND-OR chain), runs the `chosen` SELECTION per need, commits `chosen`, demands
>   `before`. Everything but `chosen` lowers to Phase-1/2 completion; the driver owns only the selection.
> - **The `chosen` selection = the ratified resolution CHAIN** (`decision_forcing_a_decision` spirit):
>   preferences (the `dominated`/`best` CNL machinery) resolve it first → a unique best is DETERMINISTIC
>   (the "selection" mostly SUBSUMED, like `DROP_CTRL`); a genuine TIE → a KB-prescribed `tie_break`
>   tool (the §8 seam); else a DETERMINISTIC-ARBITRARY pick (stable order, NOT RNG — reproducible /
>   provenance-safe). No operational policy hidden in the driver.
> - **Full solve loop `run_to_goal`** — act/observe + replan. Control (`chosen`/`done`/viable/ready/…)
>   is DRIVER-held and injected into a FRESH per-cycle `AttrGraph`; the persistent name-`Graph` carries
>   ONLY monotone facts (operators + goal + observed `<now> true`). So **the whole control-teardown bank
>   (`planning_teardown.cnl`, 15 gated drops) is SUBSUMED** — a replan is just a driver-state reset;
>   nothing control-layer is ever persisted, so there is nothing to tear down (the `DROP_CTRL`
>   subsumption of Phase 2, now for the entire replan machinery). Acting reuses `planning._perform_op`.
> - **Differential-tested vs `planning.solve`** on the coffee planner: happy path → `done`; a withheld
>   make_coffee effect → divergence → replan → `done`; a dead goal → `stuck` (all three match). PLUS the
>   two invariants the parity oracle is blind to: DIRECTION-PRESERVATION (goal-directed `reachable` is a
>   STRICT SUBSET of forward's — it never saturates the goal fact it doesn't need) and TEARDOWN-SUBSUMED
>   (the persistent graph stays purely monotone through a replan).
> - **PERF (pure, no semantics): version-keyed `derived_triples` cache.** `AttrGraph` gained a monotonic
>   mutation counter (`version`, bumped on attr/edge writes); `derived_triples` memoizes on it (returns a
>   frozenset). The goal solver takes that snapshot per subgoal across many nested solvers (profiling:
>   ~38k full-graph scans for one small plan → the dominant cost); the cache cut a plan derivation
>   ~12.7s → sub-second and the ISA test bucket ~18s → ~4s. Shared safely across all solvers over one `ag`.
> - **RESUME HERE → the ISA arc is now SEMANTICALLY COMPLETE on the planner** (all of Phase 0–3 landed).
>   What is left is NOT more coverage but the HONEST GATE (see "Next step"): the reference `GoalSolver`
>   proves SEMANTICS, not SPEED, so it cannot REPLACE `rewriter.run` until it reaches PRODUCTION PARITY
>   (df-indexed rarest-anchor SEED, hub-flooding avoidance, semi-naïve delta). Options: (a) push parity to
>   actually retire the shipped forward engine, or (b) the deferred non-arc slices (deeper walker
>   integration; in-graph-vs-bytecode fork; FUZZY over an ANN index). UNCOMMITTED on top of `e068b79`.

> **PRIOR — 2026-07-07 (session 6), 390 tests green. ISA ARC — PHASE 2 DONE (existential NACs +
> `DROP_CTRL` SUBSUMED).** The planner's ground negation shapes now lower goal-directed. Everything
> additive, isolated in `harneskills/isa/goal.py`, NO shipped-engine change. What landed:
> - **Existential NACs (¬∃)** — `_lower_nac` now PARTITIONS a rule's NACs by whether a clause
>   introduces a NAC-LOCAL free var (a binder the positive LHS does not bind): fully-bound → the
>   Phase-1 ground `R_not` completion path; free var → EXISTENTIAL, grouped by shared free var
>   (`_nac_groups_free`, the forward engine's `not (A and B)` vs `not A and not B` partition) and
>   applied per env as a demand-driven EMPTINESS check (`_exist_nac_blocks`/`_group_satisfiable`, the
>   group joined + solved to COMPLETION in a nested solve). Covers `not ?o blocked_by ?anyp` (¬∃p,
>   variable object) and grouped `not ?x A and not ?x B` (¬∃x, shared free subject). (Fixed a Phase-1
>   over-strictness: `not ?a consume ?b` with `?b` LHS-bound is a GROUND NAC, not ¬∃ — only a
>   NAC-LOCAL free var makes a clause existential.)
> - **`DROP_CTRL` is SUBSUMED, not needed** (the load-bearing finding). The block/unblock idiom's
>   `drop ?o blocked_by ?p …` exists only to retract a block the FORWARD engine asserts prematurely; on
>   the demand path `blocked_by` is computed against COMPLETE reachability, so no stale block is ever
>   asserted — the `drop` rule (empty rhs) is INERT on the goal path. DIFFERENTIAL-TESTED against the
>   ACTUAL planner driver (the repeat-`run_rules`-until-stable loop of `planning.plan`, where `drop` IS
>   load-bearing): over a 2-step precondition chain the goal solver reproduces the loop's final
>   `viable`={opa,opb} / `reachable`={water,coffee,done} exactly, `blocked_by` empty in both. (A lone
>   stratified `run_rules` sweep UNDER-derives — the mutual viable↔reachable recursion needs the loop,
>   which is why the loop is the oracle.)
> - **The one Phase-3 residual, ISOLATED** — the `chosen` commit rule's grouped NAC references its OWN
>   head (`not ?x chosen …`): a non-stratified SELECTION the forward engine resolves by commit-ORDER,
>   not completion. `_lower_nac` REJECTS it (a grouped existential NAC whose predicate == a head
>   predicate) — never silently mis-answers. Loading the WHOLE `corpus/planning.cnl` bank raises on
>   exactly this ONE rule; every other planner rule (positive, ground-NAC, ¬∃p) lowers. So Phase 3's
>   remaining scope is precisely operational choice for `chosen`, nothing else.
> - Tests: `tests/test_isa_goal_existential_nac.py` (10 — the block/unblock ¬∃p differential test +
>   `DROP_CTRL`-subsumed test + grouped ¬∃x differential test + independent-negations test + the
>   `chosen`/whole-bank selection-rejection tests). `test_isa_goal_nac.py` updated (the two old
>   "existential rejected" tests → a ground-NAC-not-existential test + a selection-rejection test; 9).
>   Docs: `isa-reference.md` (new "Existential NACs + DROP_CTRL subsumed" subsection; Next-slice now
>   Phase 3), `isa-card-trader-coverage.md` (Phase-2 rows → 🟩, frontier rewritten). **RESUME HERE →
>   Phase 3** (goal-directed planner; the `chosen` selection needs an operational choice, not a NAC).
>   UNCOMMITTED on top of `e068b79` (the user commits manually — [[feedback-no-commits]]).

> **PRIOR — 2026-07-06 (session 5), 380 tests green. THE ISA ARC STARTED — Phase 0 (coverage map) +
> Phase 1 (predicate-NAC generalization) DONE.** The migration onto the label-less / goal-directed
> machine (`harneskills/isa/`) began, with the card-trader banks as the differential-test oracle (the
> handoff "Next step" plan). Everything additive, isolated in `harneskills/isa/`, NO shipped-engine
> change. What landed:
> - **Phase 0 — the coverage map** (`docs/graph low level machine/isa-card-trader-coverage.md`): every
>   card-trader bank's rules vs the opcode set, each row marked COVERED / PHASE 1 / PHASE 2 / PHASE 3.
>   Finding: the BULK of domain reasoning was already covered (positive conjunction, transitive
>   closure, graded α-cut, MINT reification); the one load-bearing gap was NAC on relation markers.
> - **Phase 1 (THE MAIN GAP) — predicate-NAC completion** (`harneskills/isa/goal.py`): the
>   NAC→materialized-positive completion, previously copula-only (`not ?c is P` → `is_not`),
>   generalizes with NO new mechanism to an arbitrary relation — `not ?s R o` → positive body clause
>   `?s R_not o` (copula = the `R = is` case); `_neg_of[R_not] = R` recorded and handed to the nested
>   completion solver. Covers the whole card-trader negation surface (`overridden`, `stance`,
>   `excluded`, `reachable`, `needs_price`, `ranked`, `dominated`, `best`). Out of slice, REJECTED
>   explicitly (never silent): variable-object NAC (¬∃o, `not ?o blocked_by ?anyp`) and free-subject
>   grouped NAC (¬∃x, `not ?x chosen <yes>`) — the two existential shapes, deferred to Phase 2.
> - **Differential-tested against the STRATIFIED driver** (`authoring.run_rules`, NOT `rewriter.run`)
>   on the REAL `preference.cnl` stance bank + full `policy.cnl` override bank
>   (`tests/test_isa_goal_predicate_nac.py`, 6 tests): the goal-directed completion reproduces the
>   stratified answer EXACTLY, incl. the demo keystone (`today outranks standing` → `sell overridden`
>   → exclusion lifted). Oracle note (important): `rewriter.run` is a naive single fixpoint that
>   evaluates a NAC against a partial graph → derives the UNSOUND `op stance neutral` alongside
>   `op stance encouraged`; the completion's nested-complete-solve is the goal-directed analog of
>   stratifying the producer below the consumer, so it must match `run_rules`, not `run`.
> - `isa-reference.md` updated (a "Predicate-NAC generalization (DONE)" subsection + a Phase-2 "Next
>   slice" entry); `test_isa_goal_nac.py` clarified (relational GROUND-object NAC now lowers; only the
>   existential shapes are rejected — a test each). Memory `finding-isa-reference-machine` updated.
>   **RESUME HERE → Phase 2** (control layer / retraction + the two existential NAC shapes; see "Next
>   step"). COMMITTED as `eebb209 wip ISA` (working tree clean; session-4 card-trader work committed as
>   `f916126`). Also in that commit: `docs/file_index.md` (a codebase file-map doc, added alongside).

> **PRIOR — 2026-07-06 (session 4), 373 tests green. SECOND DEMO DOMAIN — the CARD TRADER (business
> semantics), and the IMMEDIATE NEXT is now the ISA ARC (see "Next step").** A collectible-card trader:
> PERSISTENT KB (operators, action classes, standing norms, card knowledge) + TRANSIENT daily policy
> ("don't sell", "take few risks today", derived market stance). Everything additive, NO engine change,
> all on the SHIPPED NAME-BASED engine (a parallel side-agent confirmed it uses none of `harneskills/isa/`).
> Memory `project-card-trader-demo`. What landed (each piece caught, twice, a near-hardcoding the user
> corrected to DATA — the motivation for the ISA pivot below):
> - **Deontic policy surface** (`harneskills/deontic.py`) — prohibition / encouragement / discouragement
>   over action classes, from a DATA-DRIVEN lexicon (`<phrase> means <polarity>` GENERATES the recognizer
>   forms, so a new phrasing needs no code — incl. the OBJECT-SCOPED frame `don't sell rare cards`); leading
>   source word tags authority; contractions normalized. Refactored from hardcoded forms after the user's
>   "no python for domain logic?" catch.
> - **Generic policy machinery** (`corpus/policy.cnl`) — defeasible-priority OVERRIDE (`today outranks
>   standing`; nothing outranks `law` → inviolable) via a monotone guarded-read `overridden` marker, plus
>   prohibition EXCLUSION; object-scoped norms are REIFIED (`deontic._mint_object_norm` → a `<norm:src:pol:
>   act:scope>` node, so they carry a source and compose with the SAME override). Wired into
>   `corpus/planning.cnl` (`candidate` gated on `not ?o excluded`; still 15 rules, reflection test green).
> - **Graded RISK filter** (`corpus/risk.cnl`) — `caution is high|medium|low` α-cut over a hedged risk
>   quality (prose graded rules; the adverb IS the threshold, reuses the built `graded_degree`).
> - **Discrete deontic RANKING** (`corpus/preference.cnl`) — encouraged > neutral > discouraged via the
>   REUSED planner `dominated` marker + an authored `outranks` tier order (bodiless fact-rules); NO
>   calculator (discrete tiers, not continuous numbers — user caught that the `compare` tool was unneeded).
> - **DEDUCTIVE reasoning** (`corpus/cards_reasoning.cnl`) — card value (`rare + in_demand → valuable →
>   premium → worth_holding`, multi-step, why-traceable) + the keystone: a reasoning rule HEAD is a deontic
>   fact, so `market is hot → sell encouraged today` OVERRIDES the standing `don't sell` (reasoned policy).
> - **Scenario HARNESS** (`harneskills/scenarios.py`) — a KB-level test/demo runner (`scenario NAME` /
>   `goal` / `expect done|stuck|[not] chosen`). `corpus/cards_kb.cnl` + `cards_scenarios.txt` = 13 days,
>   pass/fail (`python -m harneskills.scenarios`); GOTCHA fixed — `load_facts`'s `canonicalize` corrupts
>   planning's reified `add`/`pre` nodes, so `_transfer_facts` runs it ISOLATED and copies by name.
> - **Object-scoped / specific-card FRONTIER** (`corpus/cards_frontier_kb.cnl`, `tests/test_cards_frontier.py`)
>   — value→plan bridge (reasoning derives a planning effect; `have_valuable` picks the valuable card) and
>   object-scoped norms, FULLY CNL: `acts_on` added to `load_planning_kb`. FINDING: every frontier was
>   loader/surface plumbing, NOT an engine limit — the compositional core stretched with no engine change.
> - Tests: `test_deontic.py` (14), `test_scenarios.py` (7), `test_cards_reasoning.py` (6),
>   `test_cards_frontier.py` (5). Uncommitted on top of HEAD unless the user has committed mid-session.

> **2026-07-06 (session 3), 341 tests green. THE AGENTIC DEMO IS END-TO-END:** a mixed CNL KB
> → spawn the TUI → type a goal → watch the substrate drive the actions. This was the motivating target;
> it now runs. Everything additive, NO engine change. What landed:
> - **Textual TUI resurrected + wired** (`harneskills_tui/`, committed `6fe3fcd`). The old agentic-CLI shell
>   (deleted in `bba0afa` with the pre-redesign paradigm) was restored verbatim from `bba0afa^`; only the one
>   dead file — `session.py` `HarnessRunner` (it imported deleted `domain_model`/`planner`/`objective`/`engine`/
>   `corpus_reader`) — was REWRITTEN to drive `planning.solve`. Per-operator `StepEvent`s come from one choke
>   point: every operator is wrapped in the `actions` dict `solve` uses, so the wrapper performs the effect (a
>   real §8 tool / a withheld effect for a seeded failure / `simulate_effects`), posts the step, and honors
>   step-mode pause + stop — acting stays folded into canonical `solve`. Commands `/kb` `/goal` `/run` `/do`.
>   Launch `python -m harneskills_tui`. Verified headless AND via Textual `run_test` pilot. Memory
>   `project-tui-resurrection`.
> - **Procedures folded into the planning-KB loader** (completes "rules + facts + PROCEDURES in one file").
>   `planning_kb.load_planning_program(text) -> (graph, procedures)` recognizes `to NAME s1 then s2` (via the
>   existing `procedure.parse_procedures`) ALONGSIDE operators/state/goal; `load_planning_kb` stays graph-only
>   (backward-compat — the grammar-session tests untouched). TUI gained procedure mode (`/do NAME` →
>   `run_procedure`, same step wrappers). `corpus/barista_kb.cnl` = operators + goal + a procedure in ONE file:
>   `/run` drives the goal (planner derives the order), `/do morning_service` runs the AUTHORED order (planner
>   gap-fills unmet pres). Tests `test_planning_program_*` in `test_new_core.py` (+2). Surface registered in the
>   SLM track `docs/handoff_slm_surface_track.md`.
> - **Concurrency imported as the 2nd premise CLASS** (parallel-track agent; `bench/coverage_audit.py`
>   `CONCURRENCY_RULES`, 5 kind-agnostic rules, +2 tests). Data-race = a write + another access `touch` the same
>   state, concurrent, with no COMMON lock — the N5 NAC shares free var `?L`, evaluated as `¬∃L(a gb L ∧ b gb L)`.
>   GENERALIZED unbid to read/write and distinct-lock races (two-for-two with taint); isolated delta 76.5%→94.1%;
>   the residual fundamental miss is now ARITHMETIC only (value computation → `<call>` calculator by design, per
>   `finding-isa-reference-machine`). Memory `finding-coverage-composition-audit` (updated). Detail:
>   `docs/handoff_joern_arc.md`.
> - **README** gained a "Drive a goal" section (barista demo + how to run), and the landscape table gained a
>   **Production systems (OPS5 / Soar / ACT-R)** column + a "What arbitrates choice" row + an "Inherited, not
>   invented" note (goal-direction is CLASSIC — magic-sets / SLD / recognize–act; the departure is the
>   *combination* + loop-ownership, not goal-direction itself). Test count 325→341 refreshed.
> - **Worktrees cleaned up**: all 7 agent worktrees + branches removed (each verified an ancestor of `main`, no
>   committed work lost); only `main` remains. **UNCOMMITTED on top of HEAD `99a7519`** (the user commits
>   manually — [[feedback-no-commits]]): the procedures work (`planning_kb.py`, `__init__.py`, `harneskills_tui/*`,
>   `corpus/barista_kb.cnl`, `tests/test_new_core.py`, a row in `handoff_slm_surface_track.md`), the concurrency
>   work (`bench/coverage_audit.py`, `tests/test_coverage_audit.py`), and the README edit — suggest three commits
>   (feature / audit / docs). Memory: `project-tui-resurrection`, `project-slm-surface-debt`.

> **2026-07-06 (session 3, grammar sub-track) — 337 tests. Planning-problem CNL surface** (isolated, parallel-track
> work). A whole planning instance (operators + initial state + goal) can be authored in one `.cnl`
> and driven by the unchanged planning loop: `harneskills/planning_kb.py`
> (`load_planning_kb(text, graph=None)` — the ONE entry point the TUI calls — + `PLANNING_KB_FORMS`).
> Lowers readable lines (`make_coffee needs water`, `we want have_coffee`, `fetch_water costs 1`, …)
> to the EXACT edges `seed_operator`/`seed_state`/`seed_goal` produce (asserted equal in a test);
> reproduces `examples/coffee.py` from `corpus/coffee_kb.cnl`. REUSES the `procedure.py` pattern
> (per-line throwaway-graph parse + by-name `_hub` transfer); semantics in FORMS, NO engine change.
> Design note `docs/operator_goal_cnl.md`; CHANGELOG 2026-07-06 (top). **This new surface is SLM
> front-end DEBT** → registered NOT-COVERED in the new retrain track `docs/handoff_slm_surface_track.md`.

> **PRIOR — 2026-07-05 (session 2), 325 tests green.** The **label-less / ISA / goal-directed arc** was
> built out as a self-contained, isolated, non-throwaway reference implementation in **`harneskills/isa/`**
> (imports nothing from the shipped `rewriter.py`/`world_model.Graph`). This is the "cheap experiment" of
> `docs/graph low level machine/rule-isa-design.md` turned into running code, then steered by the user toward
> **goal-direction** ("switch from forward-rushing-to-fixpoint to acting toward a goal"). What landed, in order:
> - **`attrgraph.py`** — the label-less attribute substrate (opaque-identity nodes + closed-key
>   `(key,value,comparator)` attribute bundles + untyped edges; value is never an identity index).
> - **`machine.py`** — a reference ISA (`SEED`/`FOLLOW`/`JOIN`/`TEST`/`GRADE`/`FUZZY` matching, `MINT`/`EMIT`
>   monotone effects, `DROP_CTRL` control-only, `SAME`/`SET`/`DUP`) whose shape makes fact-edge deletion
>   *unrepresentable*; two-phase match-then-apply; min/product t-norm. VERDICT: positive core + monotone/control
>   effects + MINT enumerate cleanly (§5 invariant = property of opcode set; existentials = just MINT);
>   **aggregation does NOT fit** the per-state opcode shape → keep it a `<call>` calculator.
> - **`lowering.py`** — a dumb `Rule`→program lowering + name-`Graph`⇄`AttrGraph` bridge + `run_to_fixpoint`,
>   **differential-tested to reproduce `rewriter.run` EXACTLY** (conjunction, transitive closure, 4-clause SAME
>   join, graded α-cut = `graded_degree`, near-miss).
> - **`goal.py`** — `GoalSolver`, the **demand-forward** driver (rule-head index + SIP + tabling, positive core,
>   no NAF); measured to derive a strict subset vs the fixpoint (only demanded facts, never the irrelevant chain).
>   Now also: **walker wired in** (`walk_fuel=N` → a ground reachability goal on a transitive-closure relation is
>   carried by a fuel-bounded walker vs tabling the chain) and the **graded gate on the goal path**
>   (`_graded_degree` == `rewriter.graded_degree`; a demanded goal is filtered by the α-cut, records
>   `solver.degree[(rel,s,o)]`).
> - **`walker.py`** — the long-range demand primitive: a fuel-bounded BFS demand token ("think harder" = more
>   fuel), terminates through cycles, materializes a provenance SHORTCUT on arrival (repeat O(1)).
>
> Tests: `test_isa_machine.py` (14), `test_isa_lowering.py` (7), `test_isa_goal.py` (4), `test_isa_walker.py` (5),
> `test_isa_goal_walker.py` (6), `test_isa_goal_graded.py` (4), `test_isa_goal_nac.py` (8). Canonical writeup +
> honest verdict: **`docs/graph low level machine/isa-reference.md`**. Memory: **`finding-isa-reference-machine`**.
> The **README was reframed** to the ratified 2026-07-05 vision (label-less attribute nodes + goal-directed default
> as the headline, with a demarcated "What runs today" section separating the shipped name-based engine from this
> reference slice).
>
> **NAC → materialized-positive completion DONE (2026-07-06, 333 tests).** The last reasoning piece landed in
> `goal.py`: a rule's copula NAC `H :- BODY, not ?c is P` is rewritten (`_lower_nac`) into a POSITIVE body clause
> `?c is_not P`, and the negative is produced by ONE demand-driven COMPLETION step (`_complete_negative`) — to
> answer a demanded `is_not(c, P)`, solve the positive `is(c, P)` to COMPLETION in a self-contained nested solve,
> materialize `c is_not P` iff the positive has no answer. The matching core stays PURELY POSITIVE (no NAF/CHECK-
> ABSENT), negation lives at one producer, matched positively everywhere else (the `decide` line on the goal path,
> `harneskills/decide.py`, `decision_forcing_a_decision`). SOUNDNESS: the nested solve computes the positive's
> COMPLETE extension independently of the outer round, so a completed negative is final (a coexisting derived
> positive DEFEATS the default directly — no separate TMS pass needed on the goal path); a negative cycle is
> DETECTED (`_completing` guard → `NonStratifiable`), never silently mis-answered. `test_isa_goal_nac.py` (8)
> reproduces contract scenario 1's routing goal-directed (alice→express not regular; bob→regular not express) and
> pins the two edges (the negative is minted + matched positively; relational/variable/cyclic NAC rejected). Also
> hardened `_materialize` to mint-and-register a missing property-concept node (a completion object like `urgent`
> may live only as a rule literal). **RESUME HERE → NEXT SLICE: deeper walker integration** (walker for a
> transitive subgoal *inside* a larger tabled query; linear recursion over a *different* base relation, e.g.
> `anc(a,c) :- parent(a,b), anc(b,c)` — the `_transitive_closure_rels` note's later generalization). Full arc
> detail is in "Longer-standing arcs → Rule ISA" below. **This arc is DESIGN-HYGIENE, still not the nominal
> critical path** — graded means-selection (the "Next step" section) remains the orthogonal immediate build, unbuilt.

> **PRIOR — 2026-07-05 (session 1), 284 tests green.** The code-reasoning / real-Joern MDI arc advanced
> substantially: taint imported as a premise CLASS (audit 61.5%→86.7%), CPG matcher-scaling probe
> (survives real graphs; recognizer precision fixed), **real Joern set up + `parse_graphson`/`export_cpg`
> built**, recognizer rewritten for Joern's real `for`→`while`+iterator lowering, and a **real-corpus MDI
> number: 100% recall / 100% precision / 1 alias miss** through the live pipeline. Focused resume for
> this arc + the next rung: **`docs/handoff_joern_arc.md`**. Memory: `finding-joern-lowering`,
> `finding-cpg-scaling-precision`, `finding-coverage-composition-audit`. (The "Next step" section below
> still lists graded means-selection as the immediate build — that remains unbuilt and orthogonal.)

- **273 tests green** — `pytest tests/ -q` (~19s). Newest work: the **coverage / composition audit**
  (`bench/coverage_audit.py` + `tests/test_coverage_audit.py`, 8 tests) — the top open experiment, now
  MEASURED. 8 mechanism rules over one real domain (Python resource/collection safety), 21 CPG-frame
  scenarios, ZERO extraction. **Encoded-mechanism recall 100% (8/8, incl. 3 novel manifestations caught
  by composition with no dedicated rule); 0 false positives over 8 near-misses; overall real-bug recall
  61.5% (8/13).** Miss taxonomy (the finding) splits cleanly: 2 CHEAP (composable-but-unencoded, one
  general rule away) vs 3 FUNDAMENTAL (absent-premise: taint, concurrency, arithmetic — the irreducible
  Cyc-shaped risk, §12). Composition WORKS; the frontier moves by general rules + importing premise
  CLASSES, not by enumerating patterns. Two silent-drop findings pinned (see NL-surface gaps below).

- **265 tests green (prior)** — `pytest tests/ -q` (~18s). The user commits manually and has been committing
  along the arc; the SLM data-generator + Colab fine-tune is the newest work. The whole agentic arc is
  in: Stage-1 code-reasoning probe + behavioral contract suite + clingo scoped calculator (rule-driven
  aggregation) + Joern CPG extractor slice + the SLM exact-reward harness + NL→CNL data generator. Use
  `.venv/Scripts/python.exe` (system Python has no pytest); the ASP calculator needs the `asp` extra
  (`pip install clingo`, already in the venv). NB: the Edit tool has twice written a file as CRLF —
  check `tr -cd '\r' < file | wc -c` is 0 on touched files before finishing.

- **SLM NL→CNL fine-tune VALIDATED THE PILLAR (user-run on Colab): 95-98% frame-graph on held-out novel
  vocab.** A 0.5B QLoRA model learns structural NL→CNL with copy-through; `slm.grade` (frame-graph) was
  the exact reward. Two lessons banked in `slm_data.py` + `CHANGELOG`: (1) a first re-train regressed to
  79% from a DATA bug — a contiguous slice of the coda-sorted token pool made every train noun end `b`,
  every eval noun `g`, so the model learned the spurious regularity instead of copying; **a bigger model
  is the WRONG fix** (fixed by a decorrelating permutation so train/eval share one distribution,
  regression-tested). (2) The only residual misses are plural-universal depluralization of NONSENSE
  tokens — a synthetic artifact (real plurals `customers`→`customer` are pretrained, and unknown tokens
  are KB-backstopped), so NOT worth chasing to 100%. SLM PILLAR DONE.

- **SLM NL→CNL harness LANDS — reward + data generator; training is off-box** (`vision_agentic.md` §9).
  (1) `harneskills/slm.py` (`tests/test_slm_grader.py`, 6 tests): the exact reward — a candidate CNL is
  graded by comparing its frame graph to gold (`frame_graph`/`grade`/`reward`), catching the
  confidently-wrong translation (valid CNL, different frame) that parse-success/string-similarity miss.
  (2) `harneskills/slm_data.py` (`tests/test_slm_data.py`, 7 tests): the training-data generator — 4
  constructs, NONSENSE vocab (structure not vocabulary), every gold CNL validated by parsing, and a
  DISJOINT eval vocab so a correct eval prediction proves copy-through not memorization. (3)
  `scripts/finetune_nl2cnl.py` (NOT run by tests): the Colab QLoRA script (0.5-1B on a T4), grading
  with `slm.grade` (frame-graph). The USER has Colab; the training run is theirs. DEFERRED still:
  grammar-constrained decoding, richer NL via back-translation, and constructs beyond the 4 that
  currently parse (negation/relations wait on the NL-front-end gaps).

- **Joern CPG -> frames extractor slice LANDS** (`vision_agentic.md` §4/§5, §10 Stage 4,
  `harneskills/cpg.py`, `tests/test_cpg_adapter.py`, 5 tests, fixtures `tests/fixtures/cpg_*.json`) —
  the fact-producer half, built with NO live joern/JVM (java + joern are absent here; joern is a
  JDK/Scala tool, not pip). A normalized CPG export folds into `S P O` facts; recognizer rules
  materialize the SAME `Iteration`/`Mutation` frames the Stage-1 probe hand-authored (§5 the join),
  and the identical mechanism rules derive the hazard end-to-end. Variable identity via REF, "within"
  via transitive AST containment, loop-induction-variable excluded by a NAC (verified). Read-only
  iteration -> frame but no hazard. Two DEFERRED seams pending a real `joern-export`: `parse_graphson`
  (raw GraphSON wire decode, stubbed) and the frontend lowering (fixtures are a schema-faithful
  approximation). Runs as TWO phases (recognition then reasoning) to sidestep a stratifier ordering
  limit — authoring around it, not an engine change.

- **clingo scoped calculator LANDS** (`vision_agentic.md` §3, `harneskills/asp.py`,
  `tests/test_asp_calc.py`, 4 tests) — constructive disjunction / exactly-one, the one thing the
  stratified engine can't express, DELEGATED to clingo behind the §8 `<call>` boundary (not built into
  the fact layer). "Exactly one door hides the prize; not door1; not door2; therefore door3" — a
  positive conclusion by exhaustion that closed-world `decide` can't reach. Opaque discipline honored
  (atoms → anonymous indices, never parsed); sound (emits only the cautiously-entailed unique winner,
  nothing on ambiguity/unsat); composes in the engine loop (`run(..., tools=asp.TOOLS)`, result
  re-seeds reasoning). clingo is a LAZY, opt-in `asp` extra — the core imports without it.

- **Stage-1 code-reasoning probe LANDS — the agentic arc's go/no-go passed** (`vision_agentic.md` §10,
  `tests/test_code_frames.py`, 7 tests, ZERO extraction). The substrate reasons over hand-authored
  **code frames**: the queryset-mutation-during-iteration hazard is DERIVED by composing two
  mechanism-level rules (§6 coverage-by-composition), a recursion-shaped iteration triggers the SAME
  rule via the shared `Iteration` frame (§5 many-to-one), and the Stage-2 adversarial near-misses all
  refuse. QA + why-trace over frames work. This clears the substrate risk; the arc proceeds to
  extraction/calculators (see "Next step").

- **Behavioral CONTRACT suite** (`tests/test_contract.py`, 4 tests) — the swap-safety net. Asserts
  ONLY through the public surface (CNL in via `load_corpus`/`Session.submit`, answers out via `ask`/
  `.answer` — strings and booleans, NEVER internals), so it pins WHAT the system does independent of
  HOW, and any future engine swap (HRG-backed, clingo-delegated, SLM front-end, Joern extractor) must
  keep it green. Three scenarios span the substrate: graded+defeasible routing, closed-world
  elimination, the compositional code hazard. Contrast the internals-coupled regression tests
  (`test_new_core`/`test_code_frames`), which defend the CURRENT engine but can't survive a swap.
  Parametrize over an engine adapter only when a second engine is real (YAGNI).

- **Indefinite existentials (∃), question side, lands** (first reasoning-expressiveness gap, user-
  picked). `is anyone happy` / `is anything a dog` are now ∃ (bind a variable over all nodes), so a
  NAMED individual witnesses them (`bob is happy` -> `is anyone happy` = yes; was no). Existential
  FACTS already reason soundly in the un-canonicalized Session (witnesses forward-chain and stay
  distinct); the sound-under-canonicalization labelled-null representation + identification is the next
  slice. `query.EXISTENTIAL_SUBJECTS`, `tests/test_existentials.py`. Design rationale in memory
  `decision_existentials` (the constant-vs-variable / labelled-null discussion).

- **Elliptical copula conjunction/negation lands** (the prior "RECOMMENDED NEXT"). `if someone is
  round and big then …` / `is young and not rough` now parse: a shared-subject `and [not] <mod>`
  after a copula clause reuses the subject + `is`. In the shared body spine, so `if…then`, prose
  `when`, and machine grammars all get it; chains and mixes polarity. Raw-NL probe (depth-1, now 509
  sentences): **488/509 recognized, 95.2% accuracy, QDep-1 91%** (was 461/509, 90.1%, 79%). See
  CHANGELOG (newest) + `tests/test_universals.py`.

- **The NL front-end now carries ProofWriter-class reasoning end-to-end.** Raw-NL probe
  (`bench/proofwriter_nl.py`, depth-1, 25 theories): **284/311 sentences (91%) recognized, 198
  answered, 89.9% accuracy, QDep-0 97%, QDep-1 80%**, completes in seconds with NO hangs. Started
  the arc at ~52% sentences / 38% QDep-1. The whole NL surface is FORMS (graph rewrite rules); the
  lexicon is declarable DATA. This session's arc (detail in `CHANGELOG.md`, newest first; memory
  `decision_universals_to_laws`, `decision_verb_catalog`, `finding_raw_nl_coverage`):
  - **universals→laws** — `if BODY then HEAD` (`IF_THEN_FORMS`), plural-noun `Cold things are kind`
    (`plural_universal_forms`), and verb negation `S does not V O`→NAC (`verb_neg_forms`). The
    bound-variable surface is a quantifier+anaphor pair unified to `?x`/`?y` at reflection
    (`rule_var_name`, no `?x` node minted). Reuses the shared body spine + `rl_*` fragment.
  - **verb catalog** — undeclared verbs handled by a DECLARED lexicon (`eat is a relation`), NOT
    positional inference (no learning yet; §14 content-blind line). A declared word becomes a
    keyword → stops NP mis-decomposition AND folds in rules. Question side = one generic `does S P O`
    rule. CNL is 'caveman' (base verb form); English inflection is bench corpus-adaptation.
  - **definiteness → uniqueness → merge** (opt-in `the is a definite`) — `the X` = one individual
    (the definite/indefinite axis, `decision_quantification_coreference`); `_definite_forms` marks
    the whole NP span `is_unique`, `Session._merge_unique` collapses mentions to ONE node. Fixes the
    O(k²) coref + `same_as` saturation blowup (~1000×). Multi-word entities (`the bald eagle`→`eagle`)
    ride on this. `COREF_DF_CAP` (§14 stopword) makes coref robust to a mis-parsed high-df slot.
  - **object-aware stratification** — `_prod_key` keys strata on `(pred, literal-obj)` for EVERY
    predicate (content-blind, no relation name special-cased); unblocks `is not` copula universals
    that were degrading. Only refines deps; planning unchanged.
  - **lexicon-as-data cleanup** — the new grammar function words are `DEFAULT | declared-from-KB`:
    `declared_rule_variables` (`X is a variable`), `declared_auxiliaries` (`X is an auxiliary`),
    `declared_univ_nouns`; forms are graph-derived generators (like `degree_grammar_forms`). Added the
    `is an Y` form. See "Standing constraints" for the honest Python-that-stays list.

- The core scales beyond toy: on-demand reasoning is flat in KB size (WordNet 166k nodes); held-out
  monotone multi-step deduction is 100% exact. Memory `finding_matcher_is_matching_bound`,
  `finding_coverage_proofwriter`.

## Next step

> **Reprioritized 2026-07-06 (session 4): the IMMEDIATE NEXT is the ISA ARC.** Graded means-selection
> (the former immediate next, `docs/graded_means_selection_design.md`) is now effectively BUILT by the
> card trader — the graded α-cut RISK filter is the possibilistic selection, and the discrete deontic
> RANKING (`corpus/preference.cnl`) is `preferred_over`/`dominated` as specced (just discrete-tier, so no
> `compare` tool). What the card trader did NOT exercise — CONTINUOUS numeric preference — is the only
> residual, and it is optional (reuse `planning.rank_by_cost`). So the reasoning-expressiveness arc has a
> landed slice everywhere; the load-bearing next move is the ISA migration.

**IMMEDIATE NEXT — the ISA ARC: migrate the shipped reasoning onto the label-less / goal-directed machine
(`harneskills/isa/`), using the card-trader banks + scenario harness as a DIFFERENTIAL-TEST ORACLE.**

**Why now (user, 2026-07-06):** move to the ISA *asap*, partly to make hardcoding STRUCTURALLY IMPOSSIBLE.
With CNL → a DUMB lowering → a FIXED generic machine, domain reasoning has nowhere to hardcode — the
machine is domain-blind, the lowering mechanical, so all domain content MUST be CNL rules. This extends the
ISA's §5 philosophy ("never delete a fact edge" is *unrepresentable* in the opcode set, not lint-checked)
to "domain logic in the engine is unrepresentable." It directly kills the failure mode the card-trader
session hit THREE times (the deontic lexicon, the object-scoped form, the `compare` tool) — the guard stops
being *vigilance* and becomes *structure*. TWO structural moves are needed, not one: (1) the DUMB MACHINE
(reasoning can't hardcode — this arc), and (2) GENERATED-FROM-DATA grammar (parsing can't hardcode —
already the discipline: `deontic.deontic_forms`, `degree_grammar_forms`, `relation_forms`). Write both into
the guarantee; the ISA is move (1).

**The oracle (why the card trader is the right forcing function):** the harness (13 scenarios +
`test_cards_frontier.py`) asserts EXACT derived-marker sets (`excluded`/`overridden`/`chosen`/`is
valuable`). So validating an ISA lowering is mechanical and already the ISA slice's method: run each bank
through `isa/lowering.py` + the reference `Machine`, assert the derived sets match `planning.solve` /
`rewriter.run` exactly. Same discipline as `test_isa_lowering.py`, now on a non-toy program.

**Phases (do in order; the honest gate follows):**
- **Phase 0 — coverage map. DONE (2026-07-06).** `docs/graph low level machine/isa-card-trader-coverage.md`
  — every bank's rules vs the opcode set (`SEED`/`FOLLOW`/`JOIN`/`GRADE`/`FUZZY`/`MINT`/`EMIT`/`DROP_CTRL`),
  each row marked COVERED / PHASE 1 / PHASE 2 / PHASE 3. Confirmed already covered: positive conjunction,
  transitive closure (`is_a`), graded α-cut (risk filter → `GRADE`), and `MINT` (the reified `<norm:…>` nodes).
- **Phase 1 (THE MAIN GAP) — predicate-NAC generalization. DONE (2026-07-06).** `isa/goal.py`
  `_lower_nac`/`_complete_negative` generalized from copula (`is`/`is_not`) to an arbitrary relation:
  `not ?s R o` → positive body clause `?s R_not o`, `_neg_of[R_not] = R` recorded + handed to the nested
  solver. Covers the ground-object, body-bound-subject marker NACs (`overridden`/`stance`/`excluded`/
  `reachable`/`needs_price`/`ranked`/`dominated`/`best`). Differential-tested against `authoring.run_rules`
  (STRATIFIED, the correct oracle) on real `preference.cnl` + `policy.cnl` (`test_isa_goal_predicate_nac.py`).
  The two EXISTENTIAL NAC shapes (¬∃o `not ?o blocked_by ?anyp`, ¬∃x `not ?x chosen <yes>`) are rejected
  explicitly and rolled into Phase 2.
- **Phase 2 — control layer / retraction + the existential NACs. DONE (2026-07-07).** (a) The two
  EXISTENTIAL NACs (¬∃p `not ?o blocked_by ?anyp`, grouped ¬∃x) lower to a demand-driven emptiness check
  (`_lower_nac` partitions ground vs existential; `_exist_nac_blocks`/`_group_satisfiable`, nested-complete
  join). (b) `DROP_CTRL` turned out to be SUBSUMED, not needed: the `drop` retraction exists only to undo a
  premature forward assertion, and demand-driven `blocked_by` (computed against complete reachability) never
  asserts a stale block — DIFFERENTIAL-TESTED against `planning.plan`'s repeat-until-stable loop (the block/
  unblock oracle), `tests/test_isa_goal_existential_nac.py`. The `chosen` SELECTION (grouped NAC on its own
  head) is the isolated Phase-3 residual — REJECTED by completion (non-stratified choice); loading the whole
  `corpus/planning.cnl` raises on exactly that one rule. (The replan teardown on divergence is a `plan()`-loop
  concern, not a `run_rules` bank rule — it belongs to Phase 3's driver, below.)
- **Phase 3 CORE — goal-directed planner. DONE (2026-07-07).** `harneskills/isa/solve.py`
  (`derive_plan` + `run_to_goal`): the forward-fixpoint planning loop replaced by `GoalSolver`
  demand-forward — a goal PULLS only its AND-OR chain (measured strict-subset `reachable` vs forward).
  The `chosen` SELECTION is the ratified resolution chain (preferences → KB `tie_break` tool →
  deterministic-arbitrary). Control is driver-held + injected per-cycle, so the 15-rule teardown bank is
  SUBSUMED (persistent graph stays monotone). Differential-tested vs `planning.solve` (happy/replan/stuck)
  + direction + teardown-subsumed gates. See Current state.
- **Phase 3 REMAINDER — DONE (2026-07-07).** (1) The rank `<call>` tool serviced GOAL-DIRECTED:
  `GoalSolver` gained a `tools` registry (a tool-backed relation → a calculator run ONCE on first demand);
  `cheaper_than` is backed by `rank_cheaper_than`, so a cost preference (chain step 1) breaks a tie by
  COST and `examples/coffee.py` reproduces `plan()` exactly. (2) The CARD-TRADER stress case:
  `run_to_goal` drives the real `cards_frontier_kb.cnl` + value→plan bridge + full `POLICY_RULES` — the
  value→plan BRIDGE's DERIVED operator effect is observed via demand-forward add-resolution
  (`_observe_simulated`), object-scoped deontic exclusion + override work on the demand path
  (`tests/test_isa_solve_cards.py`). As predicted, no engine limits — one integration point (derived
  effects at the act boundary), not a wall.
- **HONEST GATE, slices 1 & 2 DONE (2026-07-07) — seed-from-ground + semi-naïve delta.** The ISA arc
  is SEMANTICALLY COMPLETE on the planner; the gate is production parity so `GoalSolver` can retire
  `rewriter.run` (it proves SEMANTICS, not SPEED). Slice 1 (session 7): `_facts_matching`/`_materialize`
  traverse LOCALLY from a bound endpoint (O(degree), zero `derived_triples` scans — the df-indexed
  rarest-anchor SEED) + a shared `_materialized` memo; n=80 tabling 107s → 15s. Slice 2 (session 8):
  SEMI-NAÏVE delta — a goal's body is full-joined once (the seed) then only against the previous round's
  delta (`_delta_join`/`_delta_matching`), delta propagated through BOTH the join tables and the graph
  side-channel; n=80 15s → 2.9s, exponent ~O(n^3.8) → ~O(n^2.9). Answer-preserving, PROVEN by a
  randomized differential test vs the forward closure (`tests/test_isa_goal_semi_naive.py`, 3).
- **RESUME HERE — the honest gate is no longer asymptotics-blocked.** To actually RETIRE `rewriter.run`:
  a re-hosting + deletion pass — port provenance/tools/the driver onto `GoalSolver`, run the whole
  shipped suite through it, delete the `rewriter.py` matcher / NAC branch / `graded_degree` / propagate
  handler. Win 3 (hub-flooding) is largely subsumed by the local seed — only a fully-free `R(?,?)`
  enumeration still scans. Alternatively the deferred non-arc slices (deeper walker integration;
  in-graph-vs-bytecode fork; FUZZY over an ANN index).
- **Non-issues:** no aggregation in the card trader (ranking is discrete/structural), so the one thing the
  ISA can't express isn't exercised; `<call>` tools (rank/act/price) stay Python calculators OUTSIDE the machine.

**The honest gate (do not paper over):** the reference machine proves SEMANTICS, not SPEED. `rewriter.run`
carries the profiled matching-bound wins (df-indexed rarest-anchor `SEED`, hub-flooding avoidance, semi-naïve
delta matching); the ISA must reach PRODUCTION PARITY or dropping `run` regresses the bottleneck. So "drop
the matcher / NAC branch / `graded_degree` / propagate handler from `rewriter.py`" (a substantial shrink,
re-hosting provenance/tools/driver) is gated on parity + Phase-1 predicate-NAC — NOT free. Phases 1–2 are
where the name-based engine does things the positive-core ISA has only shown on smaller fragments; expect
those to drive the work.

**THE SECOND GATE — DIRECTION-PRESERVATION (do not lose goal-direction to a parity oracle).** The arc's
acceptance method is "derived-marker sets match `planning.solve`/`run_rules` exactly" — a full-set
*fixpoint*-parity test. That oracle is BLIND to the entire point of goal-direction (`test_isa_goal.py`'s
result: `GoalSolver` derives a STRICT SUBSET — only demanded facts, never the irrelevant chain). A solver
could pass every parity test by demanding everything and DEGRADING into a forward fixpoint, and the tests
would not catch it. Full-set fixpoint-parity is the WRONG success metric for an agentic substrate, whose
cost model is "pull only what the goal needs" — the parity oracle actively rewards saturation. So:
- **Goal-direction is an ARC INVARIANT, not Phase 3's payoff.** EVERY phase lands on the `GoalSolver`
  demand-forward path; `run_to_fixpoint` / the forward `Machine` stays ONLY the differential-test harness,
  never the production path. (Do not read Phase 3 as "switch to goal-directed at the end" — that invites a
  forward-first Phase 1–2.)
- **A direction-preservation gate rides ALONGSIDE the parity gate.** For ≥1 non-toy scenario, assert
  `GoalSolver` derives a PROPER SUBSET of the forward closure — a test that FAILS if goal-direction silently
  degrades to saturation. Landed for Phase 2:
  `test_isa_goal_existential_nac.py::test_goal_direction_is_preserved_no_saturation` (demanding `viable opa`
  materializes `opa`/`water` only, never `opb`/`coffee`/`done`; `got < full`). Phase 3 must carry its own.
- **This is why Phase 2(b) went the way it did.** The forward, oracle-passing route was to PORT the 15
  drop-teardown rules onto `DROP_CTRL` — reintroducing a forward-firing retraction layer. The goal-directed
  route (taken) is that demand-driven completion against COMPLETE reachability makes the retraction
  *unnecessary* — `DROP_CTRL` SUBSUMED, not ported. Prefer the subsumption formulation everywhere; fall back
  to `DROP_CTRL` only for teardown that is control-only BY CONSTRUCTION and cannot be expressed as "computed
  against a complete extension" (e.g. the replan teardown on act/observe divergence — give it a DIRECTION
  test, not just a differential test).

**Start:** Phase 0–3 are ALL DONE (Phase 3 complete: 2026-07-07, session 6) — see Current state. The ISA
arc is SEMANTICALLY COMPLETE on the planner. **Resume at the HONEST GATE** (production parity to actually
retire `rewriter.run`), or the deferred non-arc slices. Full ISA context: memory
`finding-isa-reference-machine`; writeups `docs/graph low level machine/isa-reference.md` +
`isa-card-trader-coverage.md` (the Phase-0 map).

---

The direction is the code / business-semantics / SLM application arc in `docs/vision_agentic.md`. ALL
arc steps now have a landed slice AND the SLM pillar is empirically validated (Colab, 95-98%):
**Stage-1 substrate de-risk** (`tests/test_code_frames.py`), **clingo scoped calculator**
(`harneskills/asp.py`, rule-driven aggregation), **Joern CPG extractor** (`harneskills/cpg.py`), and the
**SLM harness + fine-tune** (`harneskills/slm.py`, `slm_data.py`, `scripts/`) — see Current state. What
remains on each is GPU/JVM-gated or incremental widening.

**TOP OPEN EXPERIMENT — the coverage / composition audit — DONE (2026-07-04).** The one load-bearing
assumption is now MEASURED (`bench/coverage_audit.py`, `tests/test_coverage_audit.py`): a small set of
mechanism-level rules DOES compose to cover real bugs (100% encoded recall incl. novel manifestations,
0 near-miss false positives), and the absent-premise tail is real but BOUNDED and characterizable
(61.5% overall recall; misses split 2 cheap / 3 fundamental). The Cyc-shaped risk is neither refuted
nor fatal — it is quantified: mechanism rules mitigate, whole-premise-CLASS omissions (taint,
concurrency, arithmetic) are the irreducible residual. FOLLOW-UPS if pushed further: (a) scale the
scenario set toward a REAL corpus (mine actual Django/sympy bugs into frames) to get a recall number
on non-synthetic manifestations — the honest next rung; (b) close the 2 CHEAP misses (alias propagation
for `use`, release-dominates-all-exits) to confirm they are one-rule fixes as classified; (c) import a
premise CLASS (a small taint ontology) and re-measure to watch a "fundamental" miss become reachable —
the clearest demonstration of the §12 mitigation lever. None is load-bearing; the go/no-go passed.
**UPDATE — lever (c) exercised TWICE: taint (2026-07-05) then concurrency (2026-07-06), each a few
kind-agnostic rules that GENERALIZED unbid. Residual fundamental miss is now ARITHMETIC alone (`<call>`
calculator by design). See `finding-coverage-composition-audit` + `docs/handoff_joern_arc.md`.**

**The arc steps (all have a landed slice; remaining follow-ups per step):**

- **DONE — clingo as a scoped `<call>` calculator** (`vision_agentic.md` §3): constructive disjunction
  / exactly-one delegated to clingo behind the `dispatch.py` `<call>` boundary, sound (cautious
  entailment only), opt-in `asp` extra. **(a) rule-driven aggregation DONE** (`asp.DISJUNCTION_RULES`):
  RULES now build the call from ordinary domain facts (a decision `?dec pred_of ?p` / `?dec domain_of
  ?type`, candidates `?d is_a ?type`, ruled-out `?d ruled_out ?p`) — one materializer rule + plain-
  variable accretor rules (a fresh `<call>?` token mints per firing, so it can't aggregate). The
  calculator now composes into pure reasoning, no driver. FOLLOW-UPS still open: (b) **optimization**
  (weak constraints / `#minimize`) — the same tool with a cost projection, when a "cheapest consistent
  set" case needs it. (c) authoring a constructive-disjunction RIDDLE end-to-end in NATURAL CNL — the
  decision facts are relational (declarable), but a "exactly one of …" surface + same-name identity for
  the shared `?p`/`?type` are GATED ON THE TWO NL-FRONT-END GAPS below (batch declaration-before-use;
  same-name merge). Stay native for ordinary defaults-with-exceptions; add **rule priority / specificity
  as data** (§8) there.
- **DONE (slice) — Joern as a fact producer** (`vision_agentic.md` §4, `harneskills/cpg.py`):
  normalized CPG -> `S P O` facts -> recognizer rules -> Stage-1 frames -> hazard, no live JVM.
  FOLLOW-UPS to make it a trusted extractor (need a JDK + joern-cli, absent here): (a) build
  `parse_graphson` and VERIFY the fixtures against a real `joern-export --format=graphson`; (b) add
  the `joern-export` shell-out as a `dispatch.py` tool; (c) widen the frame ontology + recognizers
  (while-loops, comprehensions, recursion — the §5 many-to-one shapes — and more `Mutation` forms);
  (d) move the mutator LEXICON from the Python list into KB `X is a mutator` facts.
- **DONE (reward + data; training is off-box) — The SLM NL→CNL loop** (`vision_agentic.md` §9):
  `harneskills/slm.py` (exact frame-graph reward), `harneskills/slm_data.py` (validated NL/gold-CNL
  generator, nonsense vocab, disjoint eval vocab for copy-through), `scripts/finetune_nl2cnl.py`
  (Colab QLoRA, grades with `slm.grade`). The user has Colab; running the fine-tune + reading the
  per-construct frame-match report is theirs. FOLLOW-UPS: (a) richer NL via back-translation with a
  larger model (templated NL is the current baseline); (b) grammar-constrained decoding (GBNF/outlines)
  so invalid CNL is unreachable; (c) more constructs (negation/relations wait on the NL-front-end
  gaps); (d) extend the grader to RULE-CNL via a behavioral probe — today `frame_graph` is fact-level.
  If the fine-tune underperforms per-construct, that construct's data pool is where to add examples.

**Reasoning-expressiveness gaps — now supporting work under the arc above (previously the standalone
pivot):**
- **Existentials, FACT side (labelled-null representation)** — still the near-term expressiveness item;
  the question side is DONE (above). A labelled-null witness (RDF-style `_:bN`, tagged so `canonicalize`
  + demand-coref SKIP it) keeps ∃x.P ∧ ∃y.Q distinct on the batch path, plus witness IDENTIFICATION via
  `same_as`, then `a/an <noun>` typed existentials. **Now motivated by `vision_agentic.md` §5**: typed
  `a <noun>` existentials are the determiner handling the code frame ontology and RDF/OWL import both
  want. Design rationale in memory `decision_existentials`.
- **Aggregation & arithmetic** — `count`/`sum`/`compare` as materialized `<call>` tools (reuses
  `dispatch.py`; aggregation over a completed set stratifies like negation). Lowest cost; the same
  "tools as calculators" seam clingo and Joern ride on. Unlocks quantitative KB rules.
- **Constructive disjunction / exactly-one** — RE-SLOTTED as the clingo-calculator case above, not a
  core-engine build. Wants existentials first if kept native for any sub-case.
- **Richer negation (well-founded/stable)** — the deferred §11 tail (3 non-stratifiable ProofWriter
  residuals + derived-copula NAF). Delegate the residual to clingo (§3) rather than adopting stable
  semantics in core. High cost, low yield, contentious — unchanged.

**NL-surface gaps (deprioritized but still open; pick by need):**
- **Batch loaders don't sequence declaration-before-use** (found 2026-07-04 building the contract
  suite). A declared-relation FACT (`iterate is a relation` then `loop1 iterate qs`) parses only on the
  SEQUENTIAL `Session.submit` path; `load_corpus`/`load_facts` fail to apply the catalog before the
  facts, so relational facts silently fall to raw tokens in batch (copula `is a` facts are fine). The
  contract suite's code-hazard scenario therefore authors via `Session`. Fix = make the batch loaders
  apply verb/definite declarations in a first pass before facts (or process line-order like Session).
- **`is a X` (is_a) RULE HEAD is silently dropped** (same session). `load_rules("?m is a hazard when
  …")` returns 0 rules with NO error — violates the "report malformed, never silently drop" linter
  philosophy (cf. `test_prose_rule_malformed_body_clause_raises`). Relational heads (`?m has_kind X`)
  and bare copula-marker heads (`?m is unsafe`) work. Fix = accept `is a` heads, or raise on an
  unrecognized head. Low effort, real silent-failure smell.
- **A body clause whose predicate is a RESERVED PROVENANCE NAME is silently dropped** (found 2026-07-04
  building the coverage audit; `tests/test_coverage_audit.py::test_finding_reserved_predicate_silently_dropped_from_body`).
  `load_machine_rules("… when … and ?u uses ?r and …")` drops the `?u uses ?r` clause with NO error
  because `uses` is provenance vocabulary (`h.USES`; likewise `proves`), collapsing the rule to its
  surviving clauses — a rule that silently means something WEAKER than authored (here "anything is_a
  access → hazard"). Same silent-drop family as the `is a X` head above. The audit worked around it by
  naming the domain predicate `accesses`. Fix = raise on a provenance-named predicate in an
  ordinary (non-`meta`) rule body, or reserve the names only under provenance opt-in.
- **A provenance predicate-concept node inherits a derived type** (same session;
  `test_finding_provenance_node_excluded_from_hazard_scan`). When provenance is on and a rule derives
  `x is_a T`, the `proves` node ends up with a real `is_a T` edge. Invisible to the public `ask`
  surface (`ask "is proves a hazard"` is not a recognized question), so it is benign for Q&A, but any
  raw all-nodes scan of derived facts must exclude the provenance vocabulary (`h.PROVES`/`USES`/`AXIOM`).
  Minor; a provenance-hygiene item, not on any arc's critical path.
- **Multi-adjective / `All` / comma plural universals** (`All young, cold people are green`) — the
  LARGEST remaining unrec bucket in the depth-1 probe (~13 of ~21). Extend `plural_universal_forms` to
  a leading `All` determiner + a comma/`and` adjective list (reuse the ellipsis idea).
- **Copula question, multi-word subject + bare predicate** (`is the bald eagle young`) — the Tier-3
  split limit; relational multi-word queries already work. Use `is the bald eagle a bird` / declarative
  forms, which do work. Lower yield.
- **NAF-under-CWA on a derived copula fact** (a witness with BOTH `is young` and `is rough` still
  derives `calm` from `?x is calm when ?x is young and not ?x is rough`). Pre-existing across ALL rule
  surfaces (native `when`, non-elliptical, elliptical alike — verified), a stratified-negation runtime
  limit, NOT a parsing gap. Would need the completion/decide path (or well-founded semantics) to reach
  copula NAF; a deliberate §11 call, out of the NL-front-end arc.
- **Genuinely non-stratifiable NAF cycles** (3 residual probe warnings) — the ProofWriter residual the
  stratified fragment deliberately refuses; would need well-founded/stable semantics, a deliberate
  §11 future call, NOT a casual change.
- **Indefinite existentials** (`someone is happy` as a FACT = ∃x. happy(x)) — deferred from Tier 3;
  needs an existential-witness representation. In a RULE, `someone` is already a variable (handled).

**Longer-standing arcs (not NL-front-end; pick by need):**
- **Rule ISA — a low-level machine BELOW the rules. THE CHEAP EXPERIMENT IS BUILT (2026-07-05).**
  `harneskills/isa/` (`attrgraph.py` label-less attribute substrate + `machine.py` reference interpreter),
  spec `docs/graph low level machine/isa-reference.md`, conformance `tests/test_isa_machine.py` (14
  hand-written programs, NO rules). VERDICT: the positive matching core (SEED/FOLLOW/TEST/JOIN) + monotone
  effects (EMIT/MINT) + gated control (DROP_CTRL) enumerate CLEANLY, and the §5 monotonicity invariant is now
  a PROPERTY OF THE OPCODE SET (no opcode deletes a fact edge / lowers a degree → illegal-state
  unrepresentable; existentials = just MINT). Aggregation DOESN'T FIT the per-state opcode shape (it folds
  across the whole state stream) → keep it a `<call>` calculator, not an opcode; freeze the positive-core+effects
  ISA. **LOWERING + DIFFERENTIAL TEST DONE (positive fragment):** `harneskills/isa/lowering.py` +
  `tests/test_isa_lowering.py` (5 tests) — `to_attrgraph` bridge (node name→`name="…"` valued attr, edges 1:1)
  + dumb `lower_rule` (per-`Pat`, pivot on the rel node; added machine ops `SAME` + `MINT.in_edges`) +
  `run_to_fixpoint` (fired-suppression → recursive rules terminate); the machine REPRODUCES `rewriter.run`
  EXACTLY on conjunction, transitive closure, a 4-clause SAME join, and a GRADED α-cut rule (=`graded_degree`)
  + near-miss. **GOAL-DIRECTION SHIFT (user steer 2026-07-05):** `harneskills/isa/goal.py`
  (`GoalSolver`/`solve_goal`, `tests/test_isa_goal.py`, 4 tests) — a demand-forward driver (rule-head index +
  SIP + tabling, positive core, no NAF) that materializes ONLY demanded facts; MEASURED to derive a strict
  subset vs `run_to_fixpoint` (never the irrelevant chain). `run_to_fixpoint` is now the diff-test harness +
  contrast; the DIRECTION is goal-directed (§6a). **WALKERS DONE** (`harneskills/isa/walker.py`,
  `tests/test_isa_walker.py`, 5 tests): fuel-bounded BFS demand token, "think harder"=more fuel, terminates
  through cycles, materializes a provenance SHORTCUT on arrival (repeat O(1)) — the long-range demand primitive.
  README reframed to the ratified principles (label-less + goal-directed headline, demarcated "What runs today").
  **WALKER WIRED INTO GoalSolver DONE** (`tests/test_isa_goal_walker.py`, 6 tests): `GoalSolver(…, walk_fuel=N)`
  carries a GROUND reachability goal on a transitive-closure relation with a fuel-bounded walker vs tabling the
  chain (`_transitive_closure_rels` detects `R(?a,?c):-R(?a,?b),R(?b,?c)`); derives strict subset (`{x→w}` vs
  `{x→z,x→w,y→w}`), fuel bounds reach, free-var goals still table. **GRADED GATE ON GOAL PATH DONE**
  (`tests/test_isa_goal_graded.py`, 4 tests): demanded goal gated by α-cut (`GoalSolver._graded_degree` ==
  `rewriter.graded_degree`), records `solver.degree[(rel,s,o)]`, below-cut gated out — where goal-direction meets
  the graded layer. NEXT SLICE (deferred): NAC→materialized-positive (decide line) — last reasoning piece for the
  defeasible contract scenario; then deeper walker integration (transitive subgoal inside a larger tabled query;
  linear recursion over a different base rel). Memory `finding-isa-reference-machine`.
  Design docs in `docs/graph low level machine/`: `rule-isa-design.md` (canonical writeup),
  `comparison-to-current-system.md` (what harneskills already implements vs the proposal),
  `harneskills-foundations{,-extended}.md` (prior art: RETE/WAM/Datalog/treewidth/ASP/ACT-R + a
  worked-example + glossary edition). The idea: compile every rule DOWN to a small fixed opcode set
  (`SEED`/`JOIN`/`GRADE`/`EMIT`/`EMIT-PROV`/`DROP-CTRL`/`REWIRE`/`PROPAGATE`) run by a small machine, so
  rule-stratum and machinery-stratum are debugged/tested/reasoned-about SEPARATELY. Goal = DESIGN
  TRACTABILITY, not speed, not expressiveness: explicit operational semantics, a testable machine/rule
  boundary, the §5 monotonicity invariant enforced by the OPCODE SET (illegal-states-unrepresentable,
  not a lint pass), and FORMAL reasoning about crisp-core expressiveness on the descriptive-complexity
  ladder ("which opcode does this wall need; does adding it cross PTIME→NP"). On-vision: ISA sits BELOW
  rules (not the forbidden CNL→IR seam); instructions can be in-graph nodes (more homoiconic) or a
  rebuildable bytecode cache — orthogonal fork. Matching core is PURELY POSITIVE — NO NAC/`CHECK-ABSENT`
  opcode, since negation is materialized as a positive `is_not` (the `decide`/de-pyth line); the
  gnarliest current machinery (`nac_blocks`/`_nac_groups` in `rewriter.py`, superseded residue)
  evaporates. THE CHEAP EXPERIMENT (do first, before any compiler): write the opcodes as a small-step
  spec + reference interpreter checkable against `tests/test_contract.py`; clean enumeration → you have
  the ISA; messy → the still-moving semantics (existentials/aggregation) isn't ready to freeze — learned
  on paper. Guardrails: keep the lowering DUMB (miscompilation surface); scope expressiveness claims to
  the crisp positive core (graded/budget layer is resource-relative, §14). Design-hygiene, NOT on the
  critical path — do not let it displace coverage work.
- **canonicalize retirement** — unblocked by universals→laws; the batch `load_corpus`/`load_facts`
  path is the remaining user of `forms.canonicalize` (the Session already runs un-canonicalized).
- **Generalize the decided atom `c is P` → `R(c, o)`** (`decide.completion_rule`/`DEFEAT_SEED` assume
  the unary copula) — mechanical, when a binary-relation riddle / relation-negation needs it. Now that
  stratification is object-aware, `decide.completion_rule` could also carry its natural NAC (it is
  still AGGRESSIVE+MONOTONE); a further simplification, untaken.
- **quote/eval gap** (a Pat-RHS can't mint a node named `?a`) — did NOT block universals→laws, but
  still blocks `rule_graph` property-laws.
- **Dense/hub-relation walk perf** (Tier 4a) — a walk on a cyclic relation costs O(component); fix
  must stay content-blind (bidirectional / df-gated frontier). Only when a giant-component load needs.
- **Residual grammar-unification seam** — prose and machine rules share the condition grammar but
  differ in the HEAD; full head unification ripples into frames/loose/`_rule_key` + ~4 pinned tests.

The **de-pythonization arc** (provenance-matchable → `rewire`/interposition → cascade-as-rules →
decide-as-rules → coref-as-rules) is DONE — see `docs/depythonization_design.md`,
`memory/decision_depythonization`. Its object-aware-stratification follow-up is now also done (above).

## Standing constraints (don't relitigate)

- The engine stays dumb; orchestration is token-passing serviced by the generic dispatcher — no
  hardcoded per-domain Python, and no relation name special-cased in the engine.
- Lexicon/structure is DATA (`DEFAULT | declared-from-KB`); new forms are generated like the other
  declared forms. HONEST remaining Python, all defensible (memory `decision_universals_to_laws`):
  `normalize_lexical` (`are→is`, a morphology tool like tokenizer lowercasing); `COREF_DF_CAP` (§14
  metareasoning, explicitly outside the graph); `rule_var_name`/`_merge_unique` (name-ops inside §8
  tools, past the quote/eval wall — `_merge_unique` is the `canonicalize` category).
- `Session._assert` is the one documented Python-sequence seam (parked by the user); the degree
  defaults are a 3-line bootstrap in `Session.__init__` (also parked). Leave both.
- Negation is stratified-only by design (`vision.md` §11); do not adopt well-founded / stable-model
  semantics casually.

## Parallel tracks (dedicated focused resume docs — pick one per session)

- **AttrGraph RE-HOST arc (2026-07-07, user-ratified CANONICAL) → `docs/handoff_attrgraph_rehost.md`.**
  Re-host the WHOLE system off `world_model.Graph`+`rewriter.run` onto the label-less `AttrGraph`+ISA
  machine, then delete the superseded forward machinery. The ISA arc's payoff. Strategy = NATIVE,
  red-tolerant. **IN PROGRESS, 433 tests green: substrate UNIFIED (`Graph = AttrGraph`, old class
  deleted); backward ISA engine reasons in production (`solve_all`/`ask_goal`, reproduces `run_rules`+
  `decide.solve` no fact-deletion); CWA-default+per-predicate OWA opt-in ratified+wired (`decision-cwa-default`, reversed the earlier OWA-default); `decide` retraction
  retired on the goal path; ask-user OWA gap-filler (query-boundary slice).** NEXT = the deletion-heavy
  tail: `canonicalize`->`same_as` (last fact-deletion), Session/`ask` default cutover, recognition parity,
  then delete `nac_blocks`/`graded_degree`/propagate/retraction. See the RESUME SUMMARY at the top of the
  arc doc's Current state. Memory `decision-attrgraph-rehost`, `decision-owa-cwa`.
- **Code-reasoning / real-Joern MDI arc** → `docs/handoff_joern_arc.md`.
- **SLM NL→CNL surface-coverage / retrain ledger** → `docs/handoff_slm_surface_track.md`. A
  LONG-LIVED running ledger: every session that adds authored CNL surface registers it there so a
  single off-box retrain can sweep up the accumulated debt. **Standing instruction for ALL sessions:
  when you add a new fact-shaped CNL surface, append a row to that track** (the front-end can't emit
  a surface the SLM wasn't trained on). Currently pending: the planning operator/state/goal surface.

## Pointers

- Philosophy: `docs/vision.md`. As-built: `docs/architecture.md`. History: `docs/CHANGELOG.md`.
- Design docs: `docs/depythonization_design.md`, `docs/walkers_and_locality.md`,
  `docs/planning_design.md`, `docs/consistency_design.md`, `docs/coreference_design.md`,
  `docs/coref_as_rules_design.md`. Deletion audit: `docs/nonconformance_audit.md`.
- Memory: `decision_one_substrate_vision` (full progress log) + the per-topic decision/finding files.
