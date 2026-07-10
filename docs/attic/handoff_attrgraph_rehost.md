# Handoff — the AttrGraph re-host arc

> **Direction ratified 2026-07-07 (user): re-host the WHOLE system off the name-based
> `world_model.Graph` + `rewriter.run` onto the label-less `AttrGraph` substrate + the ISA machine
> (`harneskills/isa/`). AttrGraph is the target substrate; `world_model.Graph`, `rewriter.py`, and the
> superseded machinery (forward-rushing matcher, `nac_blocks`/`_nac_groups`, `graded_degree`,
> `propagate` handler) are deleted at the end.** This is the actual payoff of the ISA arc — it makes
> hardcoding STRUCTURALLY IMPOSSIBLE (a domain-blind machine + a dumb lowering, `decision-rule-isa` /
> `decision-labelless-substrate`) and it retires the forward-rushing direction the vision supersedes.
>
> This is a MULTI-SESSION arc. The discipline is INCREMENTAL + CONTRACT-GUARDED: `tests/test_contract.py`
> (the representation-independent swap net) plus the NL/planning/cpg benches stay green at EVERY step; no
> big-bang delete. Read `docs/vision.md` (§5 monotonicity, §6a goal-direction, label-less), the ISA
> writeup `docs/graph low level machine/isa-reference.md`, and `docs/handoff_redesign.md` (arc history)
> first. Keep this file SHORT: current phase + next step; summarize landed work in `CHANGELOG.md`.

## The feasibility verdict (3 grounded audits, 2026-07-07)

The load-bearing question was: does the label-less §5 invariant (the ISA can NEVER delete a FACT edge;
only control-layer `DROP_CTRL` edges) survive contact with the whole shipped system? **Yes — with ONE
localized, already-anticipated exception.**

- **Substrate.** `AttrGraph` is a SUPERSET representation: a node NAME is the reserved `name=` VALUED
  attr (the bridge already does this), an embedding dim is a GRADED attr, a relation reifies as a
  2-hop path. So the swap is "add methods + re-home a few values," not a rewrite. The API gap is
  breadth, not depth (biggest: `name()` ~167 calls, node `confidence` ~87, `add_relation`/
  `relations_from` ~100). Missing infra to build: `remove_node`, `copy`, `to_dict/from_dict`,
  `relations_from`, `gc_disconnected`, embeddings storage, provenance-inert handling (today
  name-string based), and a zero-copy neighbour view for matcher perf.
- **Provenance → monotone-fits.** Justifications are already MINT'd `<j:…>` nodes + `proves`/`uses`
  edges — pure addition, maps onto ISA `MINT`/`EMIT`. No deletion.
- **Retraction / TMS → SUBSUMED by demand-completion (deletion path never reached).** `retraction.py`'s
  interpose DOES cut a fact edge (the one true ISA hard-conflict primitive), BUT GoalSolver never
  reaches it: `_complete_negative` computes negation against the COMPLETE extension, so the
  aggressive-complete-then-defeat dance that motivates the cut never fires — exactly how the planner
  15-rule teardown / `DROP_CTRL` was subsumed. Negative cycles are detected + rejected, not mis-answered.
- **Coref → monotone-fits (already additive).** `coref_walk` is check-before-commit, retraction-free;
  its one NAC is barrier-gated stratified → lowers to completion; scaffolding GC is control-only.
- **CPG → monotone-fits.** Positive reasoning + one stratified NAC (`not ?loop ast_star ?decl`) that
  lowers to completion — which even DISSOLVES the manual two-phase recognition/reasoning split.
- **Recognition → fits the forward ISA path, ONE hard conflict.** Tokenization/normalization/form-
  matching is seed-scoped forward (the `run_to_fixpoint` path, not `GoalSolver`); its `drop`s touch
  ONLY the ephemeral token-chain scaffolding (`next`/`first`, control-layer → `DROP_CTRL`-legal); it has
  NO `rewire`; its one `propagate` is a monotone `set` → `EMIT`. **The ONE step that genuinely deletes
  fact nodes + rewires fact edges is name-level coreference by MERGE (`forms.canonicalize` /
  `Session._merge_unique`).** But the additive replacement ALREADY SHIPS (`wire_same_as` /
  `coref_in_context` add `same_as` edges instead of merging) and retiring `canonicalize` is already a
  planned item — so this redesign is localized, not fundamental.

**Net:** one substrate (AttrGraph), TWO engine paths that BOTH already exist in `harneskills/isa/` —
forward `run_to_fixpoint` (recognition + control) and demand-driven `GoalSolver` (reasoning/answering) —
and the §5 invariant holds everywhere once (a) `canonicalize`/`_merge_unique` are replaced by the
additive `same_as` path and (b) surface scaffolding is control-marked.

## The concrete gaps to build (work items, independent of phase order)

1. **AttrGraph substrate parity** — `remove_node`, `copy`, `to_dict/from_dict`, reified `add_relation`/
   `relations_from`, `gc_disconnected`, embeddings (graded attrs), provenance-inert via the `control`
   flag (not name strings), a designated `name`/`confidence` attr convention, zero-copy neighbour view.
2. **Lowering parity** — `lowering.py:75` currently raises `Unlowerable` on `drop`/`rewire`/`propagate`.
   Add: `DROP_CTRL` lowering for control-marked surface strips; `propagate` (`set`) → `EMIT`.
3. **Forward-driver production parity** — bring `run_to_fixpoint` to `rewriter.run` parity: provenance
   emission (MINT `<j:…>`), `seeds=`/change-frontier + semi-naive (partly present), and the tools seam.
4. **The tools/dispatch `<call>` seam (the real reasoning-side gap).** `dispatch.py`'s `<call>` is a
   REIFIED node with named argument slots serviced at fixpoint; `GoalSolver.tools` is only a
   relation-keyed `f(ag)` calculator with NO per-call args. Build the argument-bearing `<call>` on
   AttrGraph so coref's `settle`/`resolve`, clingo, rank, price etc. compose demand-driven.
5. **Replace the 3 MERGE call-sites** — `canonicalize` in `authoring.load_facts`, `Session._merge_unique`,
   and any `canonicalize` reader → the additive `same_as` path (`wire_same_as`/`coref_in_context`).
6. **Name-ops as tools** — `tokenize`, `normalize_lexical`, `expand_pronouns_text` stay as TOOLS over
   AttrGraph (opaque string → nodes; §8 name-ops past the quote/eval wall, already the accepted category).

## Migration strategy (RATIFIED 2026-07-07: NATIVE, big-batch, red-tolerant)

The user chose a decisive native rearchitecture over incremental facade-first: **do not maintain two
substrates and peel slowly; move the system onto AttrGraph in large coherent batches, tolerate a RED
period mid-flight, drive back to GREEN at the end. Git is the backstop.** So green is the arc's EXIT
gate, not a per-commit invariant.

- **No facade class.** AttrGraph ABSORBS the ergonomic API the codebase + engine need (`name(nid)`,
  `add_relation`/`relations_from`, `out`/`into` aliases, `get/set_confidence`, `get/set_embedding`,
  `remove_node`, `copy`, `within`, `gc_disconnected`, `to_dict/from_dict`, `_is_inert`). Then a
  near-mechanical `Graph -> AttrGraph` type swap across the codebase; `world_model.Graph` is DELETED,
  one substrate class survives. `name()` etc. are sugar over the reserved `name=` attr — label-less is
  preserved because IDENTITY stays opaque and we never MERGE by value.
- **THE REAL WORK IS THE ENGINE, NOT THE STORE.** A pure storage swap that kept `rewriter.run` on top
  would just RENAME Graph — the §5 win comes from the EFFECT layer (only `MINT`/`EMIT`/`DROP_CTRL`
  mutate; `DROP_CTRL` refuses fact edges), and the old engine DELETES (retraction interpose, coref GC).
  So the substantive move is replacing `rewriter.run`/`run_rules` with the ISA machine (forward
  `run_to_fixpoint` extended + `GoalSolver`) and re-homing negation onto materialized-positive
  COMPLETION (no fact-edge deletion). The audits confirmed every subsystem permits this.
- **The name-index tension (decide in Phase A).** The shipped matcher seeds fast via `nodes_named`/
  `name_count` (a name->ids index); the label-less stance refuses value-indexing. Resolution: AttrGraph
  MAY keep an internal value-index over the RESERVED `name` key as a MATCHING ACCELERATOR that returns a
  CANDIDATE SET to test (never a single node, never a merge) — identity stays opaque (two "Paul"s are
  two nids both under "Paul"), so the "don't index identity by value" guarantee holds. Without it,
  forward seeding on a literal predicate degrades to O(named-nodes).

## Phases (native; GREEN is the arc EXIT gate, not per-phase)

- **Phase A — AttrGraph becomes the sole capable substrate.** Absorb the Graph API + build the missing
  methods (work item 1) + the reserved `name`/`confidence`/embedding conventions + the `name` matching-
  accelerator index. Reified `add_relation` uses the SAME named-middle-node form as `to_attrgraph`/
  `derived_triples` (so the engine walks it unchanged). §5 note: `remove_*` exist on the store but the
  ENGINE must only cut CONTROL edges — enforced at the effect layer, not by hiding `remove_*`. **← START HERE.**
- **Phase B — Engine swap.** New `run`/`run_rules` over AttrGraph = the ISA forward driver extended
  with provenance (MINT `<j:…>`), `seeds=`/semi-naive, the tools/`<call>` seam (work item 4), DROP_CTRL
  lowering + propagate->EMIT (work item 2). Reasoning/answering routes through `GoalSolver`. The old
  `rewriter.Rewriter` matcher / `nac_blocks` / `_nac_groups` / `graded_degree` / `propagate` handler go.
- **Phase C — Subsystem re-home.** Point every `world_model` import at AttrGraph; fix call-site
  differences; replace the 3 MERGE sites + retraction/decide with `same_as` / completion (work item 5);
  control-mark surface scaffolding; coref via the additive cursor; recognition on the forward driver;
  CPG as one demanded chain; planning wired to the AttrGraph store (mostly `isa/solve.py` already).
- **Phase D — Delete + drive to GREEN.** Delete `world_model.Graph`, `rewriter.py` (old machinery),
  `canonicalize`/`_merge_unique`, the retraction interpose. Re-home the internal-coupled tests
  (`test_new_core`, `test_code_frames`, … assert `_has`/node-names/lhs-tuples) to AttrGraph shapes; the
  representation-independent `test_contract.py` should pass without change. Whole suite back to green.

## Open decisions

- **Node `confidence` re-homing** (~87 calls) — a reserved GRADED key vs. dropping node-level confidence
  where a per-key degree already suffices. Decide in Phase A.
- **`within`/locality** — noted "no longer used by the matcher"; confirm it can be dropped, not ported.
- **The `name` matching-accelerator index** — adopt (recommended, above) or accept O(named-nodes) seeds.

## Current state

> **RESUME SUMMARY (2026-07-07, 443 tests green; latest work committed except this turn's `absorb` +
> this handoff edit).** Substrate re-host DONE; backward reasoning engine is the production answer path;
> loaders no longer delete fact edges; **DIRECTION RATIFIED (user): ONE engine, DELETE `rewriter`
> ENTIRELY** — no keep-rewriter compromise. Two recent enablers landed; recognition-on-ISA is now in flight.
> DONE (foundation — details in the dated entries below):
> - **Substrate unified** (`AttrGraph` = the one label-less substrate; `world_model.Graph = AttrGraph`).
> - **Backward ISA engine reasons in production** (`solve_all` forward driver + `query.ask_goal` backward);
>   Session yes/no + who answer via `ask_goal`; CWA-default; closed-world by demand-completion (no retraction).
> - **Coref MERGE retired** across all 3 loader sites → additive `same_as` (no loader fact-deletion left).
> - **Coref-following DE-HARDCODED (GATED, data-driven)** — `_follow_coref` in `isa/goal.py`: a bank that
>   carries the `same_as` propagation rules DECLARES coref (engine follows the class via the union-find, fast);
>   a bank WITHOUT them (recognition/graded) is coref-BLIND (structural). Fixes the graded cross-product at the
>   root. [[feedback-no-hardcoded-engine-policy]]. (Perf: union-find stays as the fast on-path evaluator — a
>   TEMPORARY optimization; a purely rule-driven + optimized propagation is a SEPARATE later effort.)
> - **Recognition-NAC completions demoted to CONTROL** (`control_completions` flag) — recognition scaffolding
>   invisible to fact matching.
>
> **DONE — production recognition is OFF `rewriter`, on the FORWARD ISA Machine (`run_bank`); 449 green.**
> `load_facts`/`load_corpus` recognize via `_recognize` -> `isa.lowering.run_bank` (reference `Machine` +
> dumb lowering, whole-batch, differential-proven == `rewriter.run` on `_ALL_FORMS`). Fixed the item-1 perf
> regression (suite 336→116s; recognition 28× over `solve_all`) AND retired rewriter's recognition role. NAC =
> a positive sub-program the driver runs as a match-time filter (opcode set stays positive). See the dated
> entry below. Earlier micro-opt also kept: `Pat` classification precompute (~32% engine-wide on GoalSolver).
>
> **NEXT — the run_bank PERF work is now the PREREQUISITE gate; the other peels wait behind it:**
> 0. **OPTIMIZE `run_bank` (now the critical path).** Naive today: re-match EVERY rule each round, NAC via
>    full SEED-by-name scan, no change-frontier / semi-naive / rarest-anchor seeding. MEASURED cost:
>    `load_machine_rules(planning.cnl)` 160ms→**18s** (115×); moving the light rule loaders regressed the
>    suite +80s. So the "move the other recognizers" items below are PROVEN-CORRECT but BLOCKED on this.
>    Wins: seed each rule from its rarest ground anchor (df), a change-frontier so a saturated rule isn't
>    re-matched, cheaper NAC (seed from a bound endpoint, not a full SEED scan). Differential-test against
>    `rewriter.run` each step (harness proven this session). Do NOT trade correctness/data-drivenness.
> 1. **Move the OTHER recognizers off `rewriter` onto `run_bank`** (`load_rules`/`load_universal_rules`/
>    `load_loose_rules`/`load_machine_rules`). DIFFERENTIALLY PROVEN == `rewriter` this session (all four,
>    facts+rules identical) AND the provenance fix they need is DONE (`skip_inert`, below). PURELY perf-blocked
>    on item 0 — swap is otherwise near-mechanical (revert-ready diff in git history / this handoff).
> 2. **Planner DROP_CTRL** — the planner's `TEARDOWN_RULES` are 16/16 forward `drop`s via `run_rules`
>    (rewriter's control role). Add `DROP_CTRL` lowering (the opcode exists, refuses fact edges) to
>    `_lower_bank_rule`/`run_bank`, then route the planner through it. On the critical path for deleting rewriter.
> 3. **The loaders' REASONING passes** (`run(graph, _coref_propagation(graph))`, `run(graph, graded_rules
>    (graph))`) + `run_rules` — still rewriter. `_coref_propagation` is plain positive rules (swap to
>    `run_bank` after item 0), but `graded_rules` needs `propagate→EMIT` lowering (item 4) first.
> 4. **Graded `propagate→EMIT` lowering** — `graded_rules`' one `propagate` (embedding write) -> the `EMIT`
>    opcode, so the graded layer also runs on the ISA. (`run_bank` currently rejects `propagate`.)
> 5. **Then DELETE `rewriter`** once recognition (done) + other recognizers (1) + planner-control (2) +
>    reasoning passes (3/4) are all off it. `test_contract.py` should stay green.
>
> DONE this session (kept): `skip_inert` — the ISA matcher (`Machine`) now skips provenance-inert nodes
> (`<j:…>`/`uses`/`proves`) exactly like `rewriter._match`, so `run_bank` is correct over a graph that already
> carries provenance (the loader-swap case — `normalize_surface` mints it). Auto-enabled by `run_bank` ONLY
> when the graph has provenance (one-time scan), and short-circuited + per-nid-cached so the common no-prov
> recognition path pays nothing (~70ms, unchanged). Unit-tested (`test_isa_machine`).
>
> NOTE (user, standing): raw PERFORMANCE optimization is a SEPARATE effort AFTER correctness — don't trade
> correctness/data-drivenness for speed pre-emptively.
> Full history below (dated entries); decisions in memory `decision-attrgraph-rehost`, `feedback-no-hardcoded-engine-policy`.

**2026-07-07 — item 1 PROBED (other recognizers -> run_bank): PROVEN CORRECT but PERF-BLOCKED; `skip_inert` kept; 449 green.**
Attempted moving `load_rules`/`load_universal_rules`/`load_loose_rules`/`load_machine_rules` off `rewriter`
onto `run_bank`. Differentially PROVEN identical to `rewriter.run` on all four (facts+rules; harness in
scratchpad). Surfaced + FIXED a real `run_bank` bug on the way, then REVERTED the swaps for PERF:
- **BUG FOUND + FIXED (`skip_inert`, KEPT):** the reference `Machine` matched THROUGH provenance-inert nodes,
  which `rewriter._match`/`GoalSolver` skip. On a graph carrying `<j:…>`/`uses` (from `normalize_surface`),
  `run_bank` bound `?s` in `?s first if?` to the `uses` node that justified the `first` relation, TRIPLING
  `load_universal_rules`' recognized rules. Fix: `Machine(skip_inert=…)` (opt-in) filters inert candidates in
  SEED/FOLLOW/JOIN; `run_bank` auto-enables it ONLY when the graph has provenance (one-time scan) and it is
  short-circuited + per-nid-cached, so the shipped no-prov `load_facts`/`load_corpus` path is unchanged (~70ms).
  Unit-tested. This is genuine, ready infra for when the loaders DO move.
- **REVERTED (perf):** naive `run_bank` is 115× slower on `load_machine_rules(planning.cnl)` (160ms→18s) and
  regressed the suite +80s even for the light rule loaders (bulk-called in `test_universals`/coverage). Dev
  speed wins — the swaps wait behind `run_bank` optimization (NEXT item 0). So `load_*rules` stay on `rewriter`.
- NET this session: `skip_inert` correctness fix + its test; the perf blocker precisely QUANTIFIED; the swap
  proven correct and revert-ready. `load_facts`/`load_corpus` recognition unchanged (still on fast run_bank).

**2026-07-07 — RECOGNITION ON THE FORWARD ISA MACHINE (`run_bank`); solve_all regression recovered; 449 green.**
Built the genuine FORWARD ISA driver and routed production recognition through it — recognition is now on
the reference opcode `Machine` + a dumb `Rule`->program lowering, NOT `rewriter` and NOT the slow backward
`solve_all`. This is the real fix for the item-1 perf ceiling AND retires `rewriter`'s recognition role.
- **`isa/lowering.py`:** (a) `lower_rhs` now does VALUE INVENTION — a non-LHS-bound RHS endpoint (skolem
  `<cond>?`/`<rule>?`, tag literal) MINTs one fresh node per firing, SHARED across the firing's RHS clauses
  (reproduces `rewriter.apply_rule`'s `fresh` dict); (b) `lower_lhs` refactored to `lower_conj(pats, prebound,
  tag)` so a NAC group lowers to a positive sub-program SEEDED with the firing's LHS bindings; (c) `_nac_groups`
  + `lower_nac_programs` (independent-group split, faithful to `rewriter._nac_groups`); (d) **`run_bank(ag,
  rules)`** — the BANK-level forward driver: each round MATCH every rule on the start-of-round graph, suppress
  already-fired bindings (keyed over LHS binders), apply the match-time NAC filter, then COLLECT-THEN-APPLY the
  survivors (snapshot per round — a guard tag `a is_kw yes` and the clause it gates can't race). `Machine.match`
  gained an `init=` seed for the NAC sub-programs.
- **DESIGN — NAC stays out of the opcode set** (decision-rule-isa: matching core PURELY POSITIVE). A NAC is a
  positive sub-program the DRIVER runs as a match-time FILTER (block if any group has a witness), never a
  CHECK-ABSENT opcode; §5 untouched. Reasoning-negation stays NAC-as-completion in `GoalSolver` — recognition
  NACs are stratified surface guards, correctly handled forward. Value invention is the only new lowering.
- **Differentially PROVEN == `rewriter.run`** on a diverse corpus (facts, relation, gradable, disjoint,
  if/then + plural universals, bare/graded/NAC-body rules, lexicon frame + loose imperative, closed-world):
  real FACTS identical AND recognized RULES identical, both WHOLE-BATCH and per-sentence. So `authoring.
  _recognize` DROPPED the per-sentence isolation/`absorb` (a `solve_all` workaround) — it now just tokenizes
  whole-batch + `run_bank` + strips bare-`yes` scaffold (run_bank MINTs a fresh `yes` per firing — label-less
  — which `wire_same_as` would else mislink). Tests: `tests/test_isa_runbank.py` (5, incl. the NAC-race pin +
  end-to-end contract), `isa/__init__` exports `run_bank`.
- **PERF:** rule-sentence recognition 1806ms (`solve_all`) → 64ms (`run_bank`), ~28×; vs `rewriter` 7ms it is
  ~9× (run_bank is NAIVE — no semi-naive/frontier, NAC via SEED-by-name scan — a later opt). Suite 336→116s
  (original rewriter-recognition baseline was 71s; the ~1.6× residual is run_bank's naïveté). `load_corpus(ICE)`
  9.2→2.3s. **rewriter's RECOGNITION role is now retired** (production loaders + the diff test prove parity).
  STILL on rewriter (NOT yet deletable): `load_rules`/`load_universal_rules`/`load_loose_rules` (private
  rule-only graphs — probe whole-batch `run_bank`, no isolation needed), the loaders' `_coref_propagation` /
  `graded_rules` reasoning passes, `run_rules`, and the planner's `TEARDOWN_RULES` drops (need DROP_CTRL).

**2026-07-07 — PERF: `Pat` classification precompute (safe, engine-wide ~32% on the GoalSolver path); 443 green.**
Profiling `_recognize` (per-sentence `solve_all`) pinned the cost NOT in construction/lowering but the join
loop: `is_var`/`binder`/`is_bound_literal`/`literal_name`/`str.startswith` re-derived the SAME fixed `Pat`
slot strings tens of millions of times (`_pat_goal`/`_resolve`/`_extend`/`_unify_head`; `is_var` alone 43.5M
calls/25s). Fix: `Pat.__post_init__` precomputes each slot's `(kind, bind, name)` as non-field cached attrs
(absent from __init__/__eq__/__hash__ — semantics-identical to the four classifier fns), and the GoalSolver
hot methods read them instead of re-parsing. NO engine algorithm / data-drivenness change. Result: rule
sentence 2.63→1.81s, `load_corpus(ICE)` 13.5→9.2s, suite 362→336s; ISA subset + full suite green.
DEAD-ENDS measured + rejected (don't re-try): memoizing the classifier fns (dict+call overhead > `startswith`),
and seeding all heads into one fixpoint (bigger per-round scan). The residual 4.7× is intrinsic to running
recognition BACKWARD via `solve_all` — the forward Machine driver is the real fix (NEXT item 5).

**2026-07-07 — item 1 DONE: production loaders' RECOGNITION routed off `rewriter` onto `solve_all`; 443 green.**
`load_facts` and `load_corpus` no longer recognize via forward `rewriter.run` — the "one engine" move for
production recognition. New `authoring._recognize(graph, sentences, forms)`: per sentence, a FRESH graph →
`tokenize` → `solve_all(forms, control_completions=True)` → strip bare-`yes` scaffold → `graph.absorb(gs)`
(fresh-id merge), returning the absorbed sentence-anchor ids. Both loaders call it; the downstream
`wire_same_as` / `_coref_propagation` / `graded_rules` / `propagate_embeddings` passes are UNCHANGED (still
`run`/rewriter for now — they're reasoning/graded, not recognition).
- **Per-sentence isolation is load-bearing** (the (iii) divergence): over ONE shared graph the demand-all-
  heads engine re-derives globally and a rule-source form fires spuriously on a plain fact (`alice is a
  customer` → stray `is(alice, a)`). A fresh graph per sentence is an EXTERNAL scope that prevents it —
  proven earlier in scratchpad, now the production path. Differentially checked vs the old `load_corpus` on
  the real ICE_CREAM + THIEF corpora: recognized `Rule`s IDENTICAL, real domain FACTS identical, `ask()`
  answers identical.
- **The bare-`yes` strip.** Recognition tags (`is_kw`/`kw_not`/`is_bnd`/`copula`/`det_np`/… `yes`) are
  ephemeral NAC-guard scaffolding consumed DURING recognition; every REAL yes-fact uses the inert `<yes>`,
  so bare `yes` is ALWAYS scaffold (grep-verified across forms.py/authoring.py/machine_rules.py). Minted
  fresh per isolated sentence they would DUPLICATE and be spuriously coref-linked by `wire_same_as`
  (`yes same_as yes`), so `_recognize` removes them + `gc_disconnected` before absorb. (Dangling `is_kw`
  relation nodes survive gc but are name-filtered/inert — harmless; a fuller scaffold-gc is a cleanup.)
- **PERF REGRESSION (accepted, standing note):** a fresh `GoalSolver` per sentence over the whole `_ALL_
  FORMS` bank took the suite 71s → 362s (5×). Correctness-first; seed-scoping / lowered-bank caching are the
  deferred wins. **rewriter is NOT yet deletable** — `load_rules`/`load_universal_rules`/`load_loose_rules`
  recognition and the loaders' graded/coref-propagation passes still use it (NEXT items 1/2).

**2026-07-07 — recognition-on-ISA: PATH A chosen + PROVEN; `AttrGraph.absorb` built; 443 green.** Starting
"one engine" for recognition (route recognition off `rewriter` onto `solve_all`). The remaining (iii)
divergence (spurious `is(alice, a)`) is **cross-sentence only** — a single sentence recognizes byte-identical
under `solve_all` and `rewriter`; the leak needs multiple sentences sharing one graph (the demand-all-heads
engine re-derives GLOBALLY and a NAC's emptiness check binds to a prior sentence's leftover recognition
scaffolding). So recognition must be **per-sentence ISOLATED**.
- **PROOF (scratchpad, no grammar change):** isolated per-sentence recognition (fresh graph → tokenize →
  `solve_all(control_completions=True)` → strip surface → `kb.absorb`) reproduces forward `rewriter` whole-
  batch EXACTLY on a real mixed corpus (facts + relations + gradable + universal rule + NAC rule + disjoint +
  closed-world): **recognized RULES byte-identical AND real domain FACTS identical.** In-place accumulation
  (even with strip-between) leaks `bob is a`; fresh isolation does not.
- **`AttrGraph.absorb(other)` BUILT** (`isa/attrgraph.py`, tested `test_isa_machine.py`): merges a graph into
  the accumulator under FRESH ids, preserving attrs+control+edges, NEVER merging by name (label-less — two
  "Paul"s stay two; coref is the additive `same_as` step). This commits an isolated recognition into the KB.
- **DESIGN NOTE — PATH A is a pragmatic stand-in; the PURE form is a SCOPE NODE (user, 2026-07-07).** The
  fresh recognition graph is an EXTERNAL (Python-object) scope. The pure, engine-neutral form puts the scope
  IN THE GRAPH: a `<scope>`/`<sentence>` node the sentence's tokens hang off, and recognition rules that only
  match WITHIN one scope — then isolation is DATA+RULES that ANY engine (rewriter/solve_all/Machine) respects
  identically (max reversibility). The `<sentence>` anchor `tokenize` already mints (forms root at it,
  `?s first ?x`) is the LATENT scope node; the leak is `solve_all` ignoring it and deriving globally. So the
  pure form = recognition SEEDED/SCOPED to one `<sentence>` anchor. Path A ships first (faster, reversible,
  its `absorb` doesn't block the scope-node); the scope-node is the purity follow-up. See [[feedback-no-hardcoded-engine-policy]].
- **NEXT:** rewire `load_facts`/`load_corpus` to the isolated per-sentence + `absorb` flow through `solve_all`,
  then drive the whole suite green; then the planner's DROP_CTRL (16/16 `TEARDOWN_RULES` are drops) before
  `rewriter` fully deletes.

**2026-07-07 — DIRECTION SET + coref-following DE-HARDCODED (GATED, data-driven); 442 green.** User ruled the
only acceptable direction is **ONE engine, delete `rewriter` entirely** (not the keep-rewriter compromise) —
and, reviewing the (ii)/(iii) findings, caught the real blocker underneath: **who decided GoalSolver ALWAYS
follows `same_as`? That was a HARDCODED engine policy** (a Python union-find privileging the string
`"same_as"`), introduced by node-level identity (Option B) which had MOVED coref composition OUT of banks
(`same_as_rules`, DATA) and INTO the engine. Fixed (`isa/goal.py`), correctness-first:
- **Coref-following is now GATED on the bank (`_follow_coref`)** — DATA, not engine policy. A bank that
  carries the `same_as` propagation rules (`universal.same_as_rules`) DECLARES coref → the engine follows
  the class (the union-find is those rules' fast evaluation) and drops them as subsumed. A bank WITHOUT them
  (RECOGNITION / the graded surface-chain pass) is coref-BLIND: `_token`'s class-rep is the NODE, not the
  `same_as` class, so non-unique surface tokens (`is`/`very`) match STRUCTURALLY. Recognition-vs-reasoning
  now differ by WHICH BANK RUNS, not a Python branch. Nested solvers inherit `_follow_coref`.
- **This is the enabler for "one engine"**: it dissolves the recognition fork's coref half — the graded
  cross-product is FIXED at the root (verified: coref-blind body-join yields the correct `(alice,urgent)/
  (carol,fast)` pairing, not the 4-way cross-product; the wrong cross-pairings are gone, dups are idempotent).
- **Blast radius = ONE test** (`test_goalsolver_composes_across_same_as_linked_mentions`): its premise
  ("node-level identity composes WITHOUT prop rules") is exactly what changed — re-homed to DECLARE coref via
  `same_as_rules`, plus a new `test_goalsolver_is_coref_blind_without_the_propagation_rules` pinning the gate.
  The Session `ask_goal` path did NOT break: the forward `_derive` (`_reason_bank` carries the prop rules)
  composes across links BEFORE `ask_goal` reads, so coref-blind answering is correct there. Comments updated
  (`goal.py` module doc / `_is_same_as_prop` / the node-level block; `session.py` ask_goal).
- **PERF NOTE (user, accepted as TEMPORARY):** the union-find stays as the ON-path evaluator (fast). A full
  data-driven propagation (measured ~4.5× slower on the ISA subset when the rules run un-optimized: 19.9s→
  88.5s) is a SEPARATE later effort — correctness first, optimize once everything is correct.

**2026-07-07 — item #3 sub-item (i) DONE: recognition-NAC completions demoted to CONTROL-layer; 441 green.**
The flagged "smaller follow-up" for #3 (recognition off `rewriter`). When the FORM rules run through the
`GoalSolver` forward driver (`solve_all`), their guard NACs lower to demand-completions whose NEGATIVES
(`is_kw_not`/`is_bnd_not`/`kw_not_not`) are pure surface scaffolding — the forward `rewriter` NEVER
materializes them (its NAC is a match-time check, not a materialized positive). So the ISA forward driver
over-produced visible facts the forward path doesn't. Fix (domain-blind, one boolean — NO predicate list):
- **`GoalSolver(..., control_completions=False)` / `solve_all(..., control_completions=False)`** — a
  RECOGNITION solve passes `True`; a REASONING solve leaves `False` (there `is_not P`/`overridden_not …`
  are REAL facts consumers match positively — the `decide` line — and must stay visible). `_complete_negative`
  marks the materialized negative `control=True` under the flag; nested solvers inherit it (`isa/goal.py`).
- **`_facts_matching` now skips CONTROL relation nodes** (all 3 branches) — so a demoted completion is
  invisible to fact matching, structurally (not just by naming). Safe for recognition itself: a NAC negative
  is answered by `_complete_negative` (cached/direct), never re-read via `_facts_matching`. Full suite green,
  so no existing reasoning path relied on a control node being matchable.
- **`AttrGraph.set_control(nid, flag=True)`** added (was read-only `is_control`). Recognized `Rule`s stay
  BYTE-IDENTICAL to `rewriter` (the completions are NAC scaffolding, never read by `expand_rules`); the
  positive guard fact `kw_not` correctly stays visible (rewriter emits it too). Test:
  `test_recognition_nac_completions_are_control_and_invisible` (`tests/test_isa_forward.py`) — pins that the
  flag (not the predicate) demotes, and that a reasoning enumeration of a control completion returns nothing.
- **REMAINING for #3:** (ii) `propagate→EMIT` (graded layer); (iii) route production `load_facts`/
  `load_corpus` recognition through `solve_all(control_completions=True)` + drive the whole suite; (iv)
  `INTERPOSE` opcode.
  - **(ii) FINDING (2026-07-07, explored + BACKED OUT — NOT a bounded brick):** building `propagate→EMIT`
    on the GoalSolver is easy (an `_apply_propagations` pass that joins a propagate-only rule's LHS to envs
    and writes `?x.embedding[name(?dim)] = value` — the mechanism is sound and single-mention-correct). The
    BLOCKER is the graded rule's LHS: it matches the RAW SURFACE CHAIN `?x next is? and is? next <adv>? and
    <adv>? next ?adj`, where `is`/`very`/… are NON-UNIQUE surface-keyword nodes. In production `load_facts`
    runs `wire_same_as` BEFORE the graded pass, which links same-named `is`/`very` mentions into `same_as`
    CLASSES. GoalSolver's `_facts_matching` FOLLOWS the `same_as` class (correct for REASONING — entities
    compose across coref links), so alice's `very`-node and carol's `very`-node are ONE identity → the chain
    join can't separate the two sentences → a CROSS-PRODUCT (alice gets carol's `fast`, both get both dims).
    The forward `rewriter` is immune: it matches the `next` chain STRUCTURALLY (physical edges), coref-blind.
    So (ii) needs a **coref-blind / structural matching mode** for surface-chain rules (or run graded BEFORE
    `wire_same_as` AND stop the join from following classes) — a real design decision about GoalSolver's
    identity semantics, not a quick add. Recording so the next session starts from the constraint, not the
    rediscovery. NOTE: (ii) is NOT a prerequisite for (iii) — `_ALL_FORMS` has ZERO propagate rules (graded
    is a SEPARATE `run(graph, graded_rules(graph))` pass).
  - **(iii) FINDING (2026-07-07, probed — NOT a clean swap either):** single-sentence fact recognition via
    `solve_all(_ALL_FORMS)` is content-identical to forward `run` (12/12 diverse shapes). BUT a MULTI-
    SENTENCE corpus DIVERGES: `solve_all` OVER-recognizes. Root cause = the RULE-SOURCE forms
    (`rule.cond.is_a`/`rule.kw.a`/`body.*`, in `_ALL_FORMS` but NOT in `FORM_RULES+FACT_FORMS`) fire
    SPURIOUSLY on a PLAIN fact — `alice is a customer` yields a stray `is(alice, a)` under `solve_all` that
    forward `run` never creates. The `load_corpus` fact/rule-source COEXISTENCE relies on forward-recognition
    guards (docstring: "rule fragments are built with bound-literals so recognition never grabs a fact node")
    that the demand-all-heads + NAC-as-completion engine does NOT reproduce. (`_ALL_FORMS` has ZERO `drop`
    rules → it is NOT a DROP_CTRL gap; it is a guard/NAC-firing-semantics gap.) So routing production
    recognition through `solve_all` needs the recognition-guard semantics debugged under NAC-as-completion
    (or sentence-scoped seeding, or a different forward driver) — not a swap.
  - **ARC FORK — RESOLVED 2026-07-07 (user): direction B, ONE engine, delete `rewriter` entirely.** The two
    recognition divergences are being retired, not worked around:
    - **coref-blind (the (ii) graded half) — DONE** via the gated `_follow_coref` (see the top dated entry).
      Recognition/graded banks carry no `same_as` propagation rules → coref-blind structural matching. The
      graded cross-product is fixed at the root.
    - **guard-ordered firing (the (iii) fact/rule-source-isolation half) — STILL OPEN.** The spurious
      `is(alice, a)` under `solve_all` remains: rule-source forms fire on plain facts because the demand-all-
      heads engine doesn't reproduce forward recognition's guard ordering. NEXT for "one engine": either
      sentence-scoped seeding for recognition (so a fact sentence's chain doesn't feed rule-source forms), or
      the SEPARATE forward ISA driver (`run_to_fixpoint` = reference `Machine` + `lowering` with DROP_CTRL/
      EMIT) as the recognition path — then `rewriter` deletes. NOTE (user): raw performance is a SEPARATE
      later effort; get recognition CORRECT on the ISA first.

**2026-07-07 — Phase C item #1 FINISHED: `canonicalize` retired from BOTH loaders; 438 green.** The LAST
loader fact-deletion is gone — `load_facts` and `load_corpus` no longer MERGE same-named mentions. Both
now: `wire_same_as` (additive link) → `run(_coref_propagation(g))` → `graded_rules` → `propagate_embeddings`.
- **`forms.propagate_embeddings`** (NEW §8 tool): unions graded/embedding attrs across each `same_as`
  equivalence class (union-find over the links) — the GRADED-layer counterpart of `same_as_rules`, since
  the path language can't join on embedding attrs. Reads links via `relations_from` (skips provenance-inert
  predecessors — a `same_as` relation node also carries `proves`/`uses` edges INTO it, so raw `into(link)`
  picks a justification node; this bug made it NONDETERMINISTIC until fixed). Needed because a graded
  degree lands on ONE surface mention (`alice is very urgent`); this spreads it to the coref siblings.
- **`_coref_propagation(g)`** = `same_as_rules(_COREF_PREDS | declared_relations | declared_prepositions)`,
  run before `graded_rules` so `urgent is gradable` reaches the surface `urgent` token of its use. Added
  `closes` to `_COREF_PREDS` so a closed-world marker reaches a rule's `is not P` `k_obj` before
  `expand_rules`/`_is_cw_negation` reads it (the merge used to co-locate them on one node).
- **`load_corpus` APPENDS `prop` to the returned `rules`** so forward `run_rules(kb, rules)` consumers
  (contract/cards/riddles) compose DERIVED facts across the links live (the merge gave that permanently;
  additivity needs it in the reasoning fixpoint — a NAC like `?c is not urgent` else sees a mention the
  derivation missed and misfires).
- **`GoalSolver` drops `same_as` propagation rules at intake** (`goal.py:_is_same_as_prop`): node-level
  identity follows the class natively in `_facts_matching`, so the copy rules are redundant — and they had
  ~2×'d the ISA `solve_all`/`ask_goal` tests (they saturate/complete every head). Suite 46s→91s→53s.
- **Re-homes:** `test_new_core` `outcome`/`served`/`placed`/`custs` helpers dedupe with a set (additive
  coref replicates a derived fact across an entity's mentions); two raw-`run_rules` tests bundle
  `same_as_rules` as the Session's `_reason_bank` does; the corpus `keys` assertion filters the appended
  propagation. `canonicalize` UNCALLED in production now (test-only). Full details in CHANGELOG 2026-07-07.

**2026-07-07 — Phase A (substrate) DONE; 423 tests still green.** `AttrGraph` now ABSORBS the production
`world_model.Graph` surface as conventions over the label-less core (`harneskills/isa/attrgraph.py`):
- Reserved attrs `NAME`/`CONF`; every other GRADED attr is an embedding dim. `AttrNode` gained
  `name`/`embedding`/`confidence`/`id` properties so `graph.node(nid).name` call-sites survive the swap.
- Overloaded `add_node`: a NAME string + `embedding`/`confidence` (production) OR an `{key: Attr}` dict
  (the ISA/bridge form) — both isa/ callers and former Graph callers work unchanged.
- Lexical MATCHING-ACCELERATOR `_by_name` (name-value -> {nid}), maintained in `set_attr`/`remove_node`:
  returns a CANDIDATE SET, never a merge — two "Paul"s stay two nids (label-less identity preserved).
- Full Graph API: `name`/`nodes_named`/`name_count`/`remove_node`/`out`/`into`/`add_relation`/
  `relations_from`/`set,get_embedding`/`set,get_confidence`/`within`/`gc_disconnected`/`copy`/
  `to_dict`/`from_dict`, plus `_is_inert` (name-based, ported verbatim for parity).
- VALIDATED: 100 isa tests green (existing AttrGraph behavior intact) + a smoke test (name lookup,
  two-Pauls-distinct, relation read, copy, serialize round-trip, remove_node index-sync). Full suite 423.

**2026-07-07 — Phase B step 1 (SUBSTRATE UNIFICATION) DONE; 423 tests still GREEN (not even red).**
The whole system now runs on ONE substrate, the label-less `AttrGraph`:
- `world_model.py` is now a thin RE-EXPORT — `Graph = AttrGraph`, `Node = AttrNode`, `WorldModel =
  AttrGraph`, `_is_inert`/`_INERT_NAMES` from `isa.attrgraph`. The old name-based `Graph`/`Node` class
  bodies are DELETED. Every `from .world_model import Graph` transparently gets `AttrGraph`.
- Import cycle broken: `isa/lowering.py` now takes `_is_inert` from `.attrgraph` (not `..world_model`),
  so `world_model -> isa.attrgraph` is a clean one-way edge.
- Why it was green, not red: Phase A made `AttrGraph` API-compatible, and the audit found NO external
  `Node()` construction, NO graph-internal access, NO node-field writes, only `.node(nid).name` (a
  property) — so the entire engine (`rewriter.Rewriter`) + all subsystems run on `AttrGraph` unchanged.
  Perf non-issue (suite 37s -> 40s; the `succ`/`pred` copy-vs-live-view cost is negligible).
- VERIFIED: `h.Graph is AttrGraph`; full suite 423 green; no CRLF.

**2026-07-07 — Phase B step 2 BEACHHEAD landed (the ISA machine reasons in production); 426 tests green.**
`isa.solve_all(ag, rules)` (`harneskills/isa/goal.py`) forward-materializes a whole bank by DEMANDING
every head predicate (free/free) through one `GoalSolver` — the goal-directed ISA machine used as a
FORWARD driver, reusing its positive core + NAC-as-COMPLETION + graded gate + tools. Proven
(`tests/test_isa_forward.py`, 3):
- It reproduces the shipped stratified `run_rules` EXACTLY at the answer level on the real contract
  scenario-1 bank (graded urgency + NAC-gated defeasible defeat) — WITHOUT `nac_blocks`/`graded_degree`.
- It subsumes contract scenario-2's closed-world elimination (cy uniquely the thief) via demand-
  completion, WITHOUT any retraction/deletion — and a §5 test pins that the closure only ever GROWS.
- KEY FINDING (refines the plan): a `closed world` declaration currently makes `load_corpus` PRE-COMPILE
  negation into `decide`'s AGGRESSIVE-completion rule (`?x is_not P when …`, over-asserting) + defeat-by-
  RETRACTION (which DELETES). `solve_all` correctly refuses to reproduce that (it would need the
  retraction); given the SAME reasoning as a plain NAC it gets it right. So **retiring `decide` (Phase C)
  = keeping the NAC on the GoalSolver path instead of compiling the aggressive+retract form** — the
  deletion machinery is subsumed, exactly as the audit predicted, not ported.

**2026-07-07 — GOAL-DIRECTED answering + OWA/CWA ratified; 429 tests green.** Two design decisions
ratified (memory `decision-owa-cwa`) and the engine's BACKWARD face wired into production. **[SUPERSEDED
same-day: the OWA-default below was REVERSED to CWA-default — see the item-#2 entry above / `decision-cwa-
default`. The `ask_goal` backward-face wiring and the four-status model still hold; only the DEFAULT flipped.]**
- **OWA-DEFAULT + per-predicate CWA** (user-ratified). Absence != false; unprovable = UNKNOWN unless the
  predicate is `closed`. Completion (CWA) is sound IFF the extension is KB-determined; open predicates
  never complete (never "not tainted" from failure). A NAC is a local closure assertion, so defeasible
  rules are unchanged; the OWA distinction surfaces at the QUERY answer. **ASK-USER** noted as the OWA
  companion (fills unknowns on open predicates; monotone; needs the arg-bearing `<call>` seam;
  goal-direction makes it efficient) — a standing design consideration.
- **`query.ask_goal`** (`harneskills/query.py`): answers a question by DEMANDING just its goal through
  `GoalSolver` (reasoning on demand), the backward face — vs forward `ask` which reads a pre-materialized
  graph. Recognition stays forward; only ANSWERING goes backward. `tests/test_isa_ask.py` (3): parity
  with `run_rules`+`ask` on the defeasible graded bank; GOAL-DIRECTION (one question materializes
  strictly less than the full `solve_all` closure — the DIRECTION-PRESERVATION invariant, which
  saturating would violate); OWA `unknown` vs CWA `no`.

Note (goal-direction, per user): `solve_all` (demand every head) is FORWARD saturation and degrades the
goal-direction win — it stays only for genuine full-closure needs; the production reasoning path is
`ask_goal` (backward), not `run_rules -> solve_all`.

**2026-07-07 — Phase C step 1: closed-world reasoning RETIRED off `decide`, goal-directed; 431 green.**
Closed-world elimination (contract scenario 2, WITH `cleared is closed world`) now runs on the BACKWARD
ISA machine with NO retraction/deletion, reproducing `decide.solve` exactly:
- **`expand_rules(rule_graph, *, decided_negation=False)`** (`authoring.py`): the goal/ISA path — a
  closed-world `is not P` STAYS a plain NAC (no positive-`is_not` upgrade, no aggressive
  `decide.complete.*` completion rule). `GoalSolver._lower_nac` then turns it into demand-driven
  completion — sound, no over-assertion, no retraction. (`decided_negation=True` default unchanged.)
- **`decide.closed_predicates(graph)`** — the per-predicate CWA set (names with `closes <closed_world>`,
  provenance-inert excluded); `ask_goal` reads it for the OWA/CWA query answer (concept-keyed: closedness
  is on a copula query's OBJECT concept).
- **GoalSolver now skips PROVENANCE-INERT nodes** (`_facts_matching`, like `rewriter._match`/
  `relations_from`) — else a derived `x is T` leaked `proves is T` into a free-var enumeration.
- `tests/test_isa_ask.py` (+2): the CW thief matches `decide.solve` (`yes/no/no/cy`) via the backward
  path with no retraction; `closed_predicates` == {`cleared`}; the goal-form rule keeps its NAC.

**2026-07-07 — ASK-USER seam (the OWA gap-filler), first slice; 433 green.** `ask_goal(..., ask_user=fn)`
(`harneskills/query.py`): when a yes/no goal on an OPEN predicate would be `unknown`, the engine ASKS
`ask_user(subj, rel, obj) -> bool | None` (the human-in-the-loop external source, §8) — `True`
MATERIALIZES the fact (monotone, persists for later reasoning) -> `yes`; `False` -> `no`; `None` ->
stays `unknown`. It asks ONLY the open thing the goal needs and NEVER a closed predicate (the KB is
authoritative). `tests/test_isa_ask.py` (+2): fills an OWA gap + the acquired fact persists so a
downstream rule derives; a closed predicate is answered `no` and ask-user is never consulted. This is
the query-boundary slice; SUBGOAL-level asking (mid-reasoning, on an unknown open subgoal) is the deeper
follow-up, and the arg-bearing reified `<call>` seam it wants is still to build. `decision-owa-cwa`.

**2026-07-07 — Phase C item #2: Session ANSWER PATH cut over to the backward ISA engine + CWA-default; 438 green.**
The Session's yes/no + who answers now route through `ask_goal` (`GoalSolver`, demand-driven) instead of
forward `ask` over a materialized graph — the backward reasoning engine is the production answer path (n-ary
/ why still fall back to forward `ask`). Enabled by the node-level identity below (coref) + a design reversal:
- **CWA-DEFAULT ratified, REVERSING the OWA-default `decision-owa-cwa`** (new memory `decision-cwa-default`).
  For an AGENTIC system the default is closed-world: an underivable goal is a DEFEASIBLE `no` ("best of
  current knowledge", computed demand-driven so §5-safe — no eager `is_not`/retraction), not `unknown`. OWA
  is a per-predicate opt-in (`X is open world`, surface TODO) for unsafe cases (mice/bugs) → `unknown` +
  gather evidence. `ask_goal` param is now `open_preds=frozenset()` (was `closed=`/`owa=`); the ask-user
  evidence-gatherer fires only for OPEN predicates. The dangerous-assumed-no → gather escalation is a
  METAREASONING policy triggered by DEONTICS over the epistemic act of concluding-no (the CAPSTONE, unbuilt).
- **ENTAILED NEGATION built** (`universal.entailed_negation_rules(graph)`): reads `disjoint_from` and emits
  PER-PAIR LITERAL `?z is A => ?z is_not B` (+ is_a variant, both dirs) — a HARD `no` (`A disjoint_from B`,
  `x is A` |= `x is_not B`), distinct from the defeasible assumed-no, which makes CWA-default safer. Literal
  (not variable `?a` join) so it survives concept-mention duplication under additive coref. Surfaced + fixed
  a semi-naïve bug: `GoalSolver._delta_matching` used exact `==`; now `_endpoint_matches` (literal-vs-token),
  so a delta token-pair matches a literal subgoal. Single-hop composes; multi-hop via is_a transitivity is
  limited by the pre-existing concept-coref gap (NOT a regression — `is rex a dog` is `no` on committed too).
- Also: `_lower_nac` now DROPS a NAC clause identical to the head (a forward idempotency guard like
  is_a.transitive's `not ?a is_a ?c`) — redundant under tabling, and lowering it to completion made the head
  depend negatively on itself (spurious `NonStratifiable`). Matches `rewriter.run` (which derives the head).
- Tests: `test_isa_ask.py` reframed to CWA-default (`open_preds` opt-in, ask-user gathers for OPEN); added
  entailed-negation tests; `test_isa_goal_nac.py` cycle test split (genuine cross-predicate negative cycle
  still raises; head-identical self-NAC now derives). Memory index compacted; `decision-owa-cwa` superseded.

**2026-07-07 — Phase B: GoalSolver made NODE-LEVEL (selective coref on the ISA backward engine); 435 green.**
The load-bearing gate for retiring `rewriter` on the REASONING path. A differential COREF PROBE (rewriter
vs GoalSolver on two `paul` mentions, `respected :- teacher, mortal`, one fact per mention) found the ISA
backward engine reasoned at the NAME level and could NOT carry the Session's node-level selective coref:
`_facts_matching` resolved a bound subject NAME to ONE node, so a ground fact on a sibling coref mention was
invisible (even `paul is_a mortal` failed when the fact sat on `paul#2`). USER RATIFIED **Option B
(node-level identity)** over the ~10-line Option A (read-all-same-named — free coref but breaks selective
coref + contradicts label-less). BUILT (`harneskills/isa/goal.py`):
- Identity currency = a TOKEN. `_token(nid)` = the name if UNIQUE-noded (so every name-canonicalized /
  distinct-entity KB — every existing test + `load_corpus` bank — is byte-for-byte unchanged, token ==
  name), else `name\x00classrep` per `same_as` equivalence class (union-find over `same_as` edges).
- `_facts_matching` FOLLOWS the `same_as` class of a bound endpoint — LINKED mentions compose, UNLINKED
  same-named nodes stay distinct (selective coref, the label-less distinct-witness model). `same_as_rules`
  propagation is thus unnecessary on the goal path (composition = link traversal, not copy).
- Literal-vs-token split (`_endpoint_matches`/`_extend`/`_unify_head` compare literals by `_render`): a
  rule LITERAL is a concept by NAME (any class), a bound VARIABLE is identity by token. Names live only at
  the boundary: `_entry_tokens` (a top goal on a DUPLICATED name fans out over its classes) + `_render`
  (public `solve` maps tokens→names; nested completion/∃-NAC solvers use token-returning `_solve_tokens`).
- Differential-tested (`test_isa_ask.py` +2): linked → `respected` composes (agrees with forward rewriter);
  unlinked → distinct, not composed. Dead `_node_id`/`_all_triples` removed; both-free `_facts_matching`
  now enumerates reified relation-instance nodes (no `derived_triples` scan — a free perf win). Fixed a
  latent test-helper bug (`ids.setdefault(n, g.add_node(n))` eagerly minted orphan duplicate nodes).
- **This UNBLOCKS item #2** (Session answer path → `ask_goal` default): the ISA backward engine now carries
  the Session's selective coreference. `rewriter`'s reasoning path can start retiring for real.

**2026-07-07 — Phase C, item-#1 SLICE 1: `Session._merge_unique` fact-deletion RETIRED; 433 green.**
The Session's single-identity coreference no longer MERGES nodes (a fact-edge deletion). `_merge_unique`
(hand-written `add_edge`/`remove_node` graph surgery collapsing every `is_unique` mention to one node)
is replaced by `_force_coref_unique`, which delegates to the EXISTING demand/dispatcher handshake
`_resolve_coref(force_names=...)`: seed a `<demand>` -> the `DEMAND_COREF` rule turns it into a coref
`<call>` -> the engine services it in FORCE mode (additive `same_as`, commit every pair unconditionally,
no clash-check, no retraction). The coref DECISION is now a rule firing on a token, not a Python call.
- Facts compose across the link via `same_as` propagation (already present in `_reason_bank`); the two
  call sites (`_assert`, `_check`) both moved. Single-identity contradiction detection is preserved —
  it was ALREADY additive for the cross-name `same_as` case (`test_session_cross_name_identity_catches_
  contradiction`), so the same-name case now works the same way (two `ice` mentions linked, `is_a` both
  solid+liquid via propagation, disjoint schema fires).
- Two internal-coupled `test_verb_catalog` tests re-homed from the merge representation
  (`nodes_named==1`) to the additive one (`same_as`-linked mentions + facts compose). This is the
  Phase-D "re-home internal-coupled tests to AttrGraph shapes" work, done incrementally.
- Motivated by a user question ("why is Python managing coref/derive — shouldn't they compile to the
  ISA?"). Honest state: inference CONTENT is already rules/banks (coref = `coref_walk` cursor rules,
  propagation/detection = rules); what remains Python is (a) the ENGINE those rules run on — still
  `rewriter.run`, not the ISA `run_to_fixpoint`/`GoalSolver` (only the ANSWER path `ask_goal` is on the
  ISA today — Phase B) and (b) ORCHESTRATION (`_assert` sequence, `_derive` phase plan — the flagged
  "KNOWN REMAINING SEAM", targeted at control-tokens/subgoals, `decision-agentic-loop-inversion`). This
  slice moved one real piece from "Python doing graph surgery" to "rule doing coref."

**#1 COMPLETE (2026-07-07, 438 green).** All three production merge sites (`Session._merge_unique`,
`authoring.canonicalize` in `load_facts` AND `load_corpus`) are retired to additive `same_as`. Details in
the two SLICE entries under the RESUME SUMMARY item #1 above and the CHANGELOG. `canonicalize` is now
test-only (a Phase-D delete). See the 2026-07-07 dated entry for the mechanics (`propagate_embeddings`,
the `closes`-in-propagation trick for closed-world, and `GoalSolver._is_same_as_prop`).

**§5 REFRAMED (user, 2026-07-07) — the "delete retraction + blanket guard" plan is RETIRED.** Retraction
by INTERPOSITION (`retraction.py`: cut `?rel→?o`, relink through the inert `<retracted>` marker) is
REVERSIBLE and marker-recorded — the fact node persists, the edge is reconstructible — so it is NOT the
fact-LOSS §5 forbids. The invariant is "the monotone reasoning FIXPOINT never loses a derived fact," which
the backward `GoalSolver` satisfies by construction; `h.retract` is a sanctioned reversible belief-revision
TOOL. So: the blanket "`remove_*` refuses fact edges" guard is the WRONG shape (it would forbid the
legitimate rewire) and is DROPPED; `retraction.py` + `decide` + their tests STAY. The re-host retires the
FORWARD reasoning machinery for the OTHER arc reasons (domain-blind engine, goal-direction, one substrate)
by moving reasoning onto the backward ISA engine — NOT because retraction breaks §5. Future: a rule-based
`<reconsider>` (un-splice on new evidence, `<retracted>` as KB vocabulary) = belief revision as pure banks.

**LANDED 2026-07-07 (439 green): backward-engine PROVENANCE + contract/riddles reasoning on the backward
engine.** `GoalSolver` now MINTs in-graph `proves`/`uses` (+ a premise-less `complete.REL` J for a
closed-world negative) when `provenance=True`, so `why`/`explain` reads its derivations (`isa/goal.py`;
`_justify`/`_justify_completion`/`_find_fact_node`, `_materialize` returns the rel node). `load_corpus(...,
decided_negation=False)` gives the plain-NAC form. `test_contract` + `test_riddles` now run on
`solve_all(..., provenance=True)` — same public contract, no aggressive over-assertion, no retraction. This
proves the backward engine is the reasoning engine for the closed-world path incl. explanation.

**NEXT — finish Phase C + the swap, pick ONE:**
(1) **Move the remaining forward reasoning consumers onto the backward engine** (the arc's "ISA is the
reasoning engine" goal — NO LONGER a §5 deletion errand). `decide.solve` is still the forward aggressive-
completion+retract driver, now superseded by `solve_all`/`ask_goal` for reasoning; its remaining callers
are `test_decide.py` (decide's own unit test — leave until decide itself is retired) and any Session/
`run_rules` closed-world path (audit: does `expand_rules` default `decided_negation=True` still matter for
the Session, or is it vestigial now that answering is `ask_goal`?). Once no reasoning path needs the forward
aggressive completion, `decide.solve`/`DEFEAT_SEED` become deletable (retraction.py STAYS as the TMS tool).
(2) **Recognition ISA-forward parity** (item #3) — SUBSTANTIALLY LANDED 2026-07-07 (440 green). Framing
(user): `FORM_RULES` may stay Python (declarative data), but the reasoning MECHANISMS — NAC,
`propagate→EMIT`, interpose — must live ONLY in the ISA, not `rewriter`; moving all three deletes
`rewriter`. Empirically, recognition runs on `solve_all` (GoalSolver forward driver): NAC handling is
ALREADY the ISA's (NAC-as-completion == `rewriter.nac_blocks` on recognition guards). Two demand-engine
gaps found + FIXED (`isa/goal.py`, differential test `test_solve_all_recognizes_rule_source_identically…`):
(a) **Skolem/value-invention** for `<...>?` heads (`_head_endpoint`/`_skolem`), (b) **bound-literal pinning**
(`is?`/`a?` pinned to one node across body clauses, `_extend`/`_resolve`). Rule-source recognition now
compiles byte-for-byte identical `Rule`s via `solve_all`; full suite green (no reasoning regression).
   - **REMAINING for #3:** ~~(i) mark the materialized recognition-NAC completions CONTROL-layer~~
     **DONE 2026-07-07 (441 green)** — see the dated entry at the top of this file; (ii) `propagate→EMIT` for the graded layer
     (`graded_rules`' `propagate` — the ONE propagate) so graded also runs on the ISA; (iii) route the
     production `load_facts`/`load_corpus` recognition through `solve_all` + drive the whole suite;
     (iv) build the `INTERPOSE` opcode ([[decision-interpose-opcode]], designed). Then `rewriter` has only
     positive matching left (subsumed by the ISA) → DELETE it + `nac_blocks`/`graded_degree`.
