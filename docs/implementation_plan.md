# Implementation Plan — the vision-faithful system

> **Status: THE ACTIVE PLAN (2026-07-07, ratified with the user).** The single plan for
> implementing the system the canonical docs describe: one label-less attribute substrate, one
> ISA engine, universal system-2 firmware over reified rules, KB procedures, bounded-defeasible
> semantics. It ABSORBS and supersedes `handoff_attrgraph_rehost.md` (remaining items → Phase 0;
> now in `attic/`) and `handoff_firmware_migration.md` (phases → 1–6; deleted). **Backward
> compatibility is NOT a constraint** (user): divergences from old behavior are classified
> (ratified vs bug), never preserved for their own sake.
>
> Read first: `reference.md` (index + decisions in force) → `vision.md` (philosophy) →
> `logic_fragment.md` (WHAT is expressible) → `processing_modes.md` (HOW the machine computes)
> → `graph low level machine/isa-reference.md` (opcodes as built). Log landed work in
> `CHANGELOG.md`; keep THIS file short — current phase + next step.
>
> Standing rules: no commits by the assistant; domain logic ONLY in banks; strategies are
> DECLARED data, never engine sniffing; correctness before raw performance.
>
> **RATIFIED 2026-07-10 (user): EQUIVALENCE WITH THE PREVIOUS (rewriter / name-based) GENERATION IS NOT
> A CORRECTNESS TARGET.** The old generation was never used. `rewriter.py` + the `TEMPORARY BRIDGE`
> dual-write are a DEV CONVENIENCE (a handy oracle while building), NOT an equivalence contract — retire
> them freely when they get in the way. The goal is a **WORKING, self-consistent firmware system**, judged
> on producing sensible answers on the benches, NOT on reproducing the old exhaustive engine's outputs.
> Every "differential-gated against `rewriter`/old-exhaustive" exit condition below is DOWNGRADED to
> "firmware is sensible + self-consistent." GoalSolver stays only as a *development* oracle for the firmware
> (no old-answer-preservation constraint); demote/delete it on firmware coverage alone. See the
> "Session-handoff" section for the reclassified risk picture.

## NEXT STEP (pick this up FIRST)

**Suite fully green (2026-07-10, 535 passed, 0 failed** — `.venv` `python -m pytest -q
--ignore=tests/test_joern_corpus.py`, ~230s). Phase 5.1–5.4 + 5.5-slices-1/2/3a/3b uncommitted (committed
through Phase 4: `48148af` + the Phase-4 commit). **Phase 5.4 (declared strategies) DONE**; **Phase 5.5
slices 1–2 (CHECK+CHOOSE as `<call>` calculators), 3a (rules emit mode-calls, serviced in the loop,
verdict feeds back), 3b (no new surface — reuse the `<call>` grammar; key-aware INTERN fix retires the
interning sharp edge, relational checks now sound) DONE** — see those sections + `CHANGELOG.md`
(2026-07-10). **PICK UP NEXT: Phase 5.5 slice 4** — plan→act→check→replan expressed as ITERATE×CHECK over
`<check>` verdicts (compose the existing execution loop with mode-calls); plus **3c** SUPPOSE scope
authoring (deferred from 3b); then the Phase-5 exit gate (benches on firmware semantics — the LARGE
culmination). Companion slices from 5.1/5.2 remain open
(graded α-cut during matching; aggressive `is_not` completion; wire the planner's `chosen` as a declared
CHOOSE) — not blocking 5.5.
**RECOMMENDED FRESH-SESSION ORDER (post the no-equivalence ratification, 2026-07-10):** (1) do the
Phase-6.0 rewriter/dual-write retirement + reader-flip sweep FIRST — ✓Sonnet, mechanical, banks the big
de-risk and shrinks the code; THEN (2) slice 4 (plan→act→check→replan) — ⚠Opus. See the Session-handoff
section for the full model-routing table + reclassified risk.
The FIRMWARE arc (Phase 4, the vision's centerpiece) POSITIVE CORE is **COMPLETE THROUGH ITS GATE**, and
**Phase 5.1 CHECK + 5.2 CHOOSE + 5.3 SUPPOSE + 5.4 declared-strategies are DONE** — read the Phase 4 /
Phase 5 sections below and `CHANGELOG.md` (2026-07-09/10) for the full trail. Landed across the last
sessions, each differentially gated:
- **Phase 2.2 — control tokens as keys, BOTH halves DONE**; inert `_is_inert`→`.inert` flag migration DONE +
  guarded. 2.2's only remaining item is the Phase-6 reader flip (oracle-blocked).
- **Phase 3.1 step 1 — canonical reified rule shape**; **Phase 3.3 head index** as substrate structure.
- **Phase 4.2 APPLY v0 + Phase 4.3 CHAIN v0** — reified-rule match with a VISIBLE `<frame>`, and
  demand-driven sub-goaling with VISIBLE `<demand>` nodes.
- **Phase 4.1 gadgets ALL DONE** — the APPLY body-atom cursor is a `<current-atom>` token over a `next`-chain
  itinerary; `apply_to_fixpoint` is SEMI-NAIVE with the delta atom marked `<fresh>`; CHAIN's `<demand>` is
  promoted to the BOUND-TUPLE SIP grain (`chain_sip`, magic sets, subject/object pruning — mined from `goal.py`).
- **Phase 4.4 trace renderer DONE (the phase GATE)** — the firmware JOURNALS natively (RECORD, mode 9:
  `<j:>` proves/uses at every APPLY/CHAIN EMIT, opt-in, byte-identical to `run_bank`) and RENDERS via the
  existing `surface.explain` (journal replay); `render_demands` shows the bound magic set as CNL; and the
  EXIT GATE holds — `chain_sip` == `GoalSolver` on a randomized ProofWriter-positive slice (1000+ checks).
  `harneskills/isa/{apply,chain}.py`; `tests/test_isa_{trace,firmware_gate}.py`.
- **Phase 5.1 CHECK DONE** — `harneskills/isa/check.py`: `check(...)` returns the 4-status CWA verdict
  (POSITIVE / ENTAILED_NEG / ASSUMED_NO / UNKNOWN) over `chain_sip`, `collapse()` == `ask_goal`'s
  yes/no/unknown (differentially gated vs `GoalSolver`), `explain_check` renders "where I looked."
- **Phase 5.2 CHOOSE DONE** — `harneskills/isa/choose.py`: `choose(g, goal, alpha=…)` = graded α-cut argmax
  over candidate options (nothing-beats-it, ties→both, MONOTONE losers-retained), the LOCKED means-selection
  design (never previously built); gated on its fixtures + a 200-seed argmax differential.

**Pick up next: Phase 5.5 (KB procedures), then the Phase 5 exit gate.** 5.1 CHECK, 5.2 CHOOSE, 5.3
SUPPOSE, and 5.4 declared-strategies are all DONE (details in their sections + `CHANGELOG.md`). 5.4's
tracked residual (`same_as propagates through X` CNL surface, `CONTENT_PREDS` Python choice) is logged
against Phase 3, not lost.

**Firmware-v2 slices landed (for reference):**
1. **Phase 5.3 — SUPPOSE (`<hypothesis>` scopes) DONE (2026-07-10, 519 green, `harneskills/isa/suppose.py`,
   `tests/test_isa_suppose.py`).** The pencil/ink split, same-graph (NOT the possible-worlds/`graph.copy()`
   trap). Built as the design crux predicted — scope-aware matching, gated behavior-NEUTRAL:
   - **Scope-aware matching (the non-additive part).** `apply._fact_relnodes` / `chain._facts_matching` /
     `_fact_exists`/`_find_fact_relnode` gained a `scope=` param. A pencil fact is a CONTROL rel node tagged
     `scope=<hypothesis-id>` (`apply.SCOPE = "scope"`, a VALUED attr): invisible to ordinary matching (so it
     never touches ink), visible ONLY within its scope when `scope=` is passed. `scope=None` (the default
     everywhere but in-scope reasoning) reproduces the original fact-only behavior EXACTLY — differentially
     proven behavior-neutral (all 34 firmware-gate tests + full suite green, 511→519).
   - **`chain_sip(scope=…)`** reasons inside a scope: sees pencil + ink, EMITs its derivations back in PENCIL
     (control + scope tag), so nothing unconfirmed touches ink.
   - **`suppose(fact_g, rule_g, assumptions, predictions)`** → `SupposeResult(status, committed, contradiction,
     looked_for)`. Mints a `<hypothesis>` control scope, pencils the assumptions, CHAINs each prediction (and
     its `_neg_pred`) in-scope, then: **REFUTED** iff a prediction's NEGATION is entailed in-scope (the
     supposition entails the opposite) → `_drop_scope` (remove every scope-tagged control rel + the hypothesis;
     ink untouched, monotone); **CONFIRMED** iff every prediction holds and none contradicted → EMIT the
     assumptions to INK (optional `<j:confirmed>` provenance) then sweep the pencil; **INCONCLUSIVE** (no
     contradiction, not all predictions derivable in budget) → drop, ink untouched. `explain_suppose` renders it.
   - **v0 scope:** assumption endpoints resolve to real entity nodes (only the RELATION is pencil — a fresh
     pencil ENTITY is a later slice); `_neg_pred` negation convention (`is`->`is_not`); CONFIRM commits only the
     ASSUMPTIONS to ink (consequences re-derive from ink by ordinary forward reasoning). REFUTE criterion is
     "a prediction's negation is entailed in-scope" — sound (the hypothesis's prediction fails against what the
     KB entails), even when the negation derives from ink alone (a prediction contradicted by known facts).
   - **NOTE for whoever consumes the ink view:** `lowering.derived_triples` deliberately INCLUDES control rel
     nodes (filters only by name+endpoints), so a pencil fact shows up there mid-suppose — the differential
     gates are unaffected (no scope is live during them), but an "ink-only" reader must skip control/inert rel
     nodes (see `tests/test_isa_suppose._ink`).
2. **Phase 5.4 — declared strategies (delete shape-sniffing) DONE (2026-07-10, 522 green).** All three
   sniffers deleted; walker base map + coref-follow are now DECLARED DATA the engine reads. See the
   Phase 5.4 section for 5.4a/5.4b + the tracked residual violation.

Companion slices still open within 5.1/5.2 (not blocking 5.3): the graded α-cut DURING matching in APPLY/CHAIN
(`_graded_degree` in the body — lifts them off positive-only on the graded axis; CHOOSE consumes its degrees),
the reasoning-side AGGRESSIVE `is_not` completion (`decide.solve`'s write-side elimination), and wiring the
planner's `chosen` pick (`solve._mint_chosen`) as a declared CHOOSE.

Also still open (NOT on the firmware v2 path): live rendering of the EPHEMERAL `<frame>`/`<current-atom>`
working state (a debug affordance — the persistent journal is the explanation); Phase 3.1 step 2 (one-graph
fold); Phase 2.3 name demotion + Phase 6 oracle retirement (oracle-blocked). `tests/test_joern_corpus.py`
live-Joern remains a legitimately-slow unrelated item.

Also still open (NOT on the firmware path): Phase 3.1 step 2 (one-graph fold — the APPLY frame-edge/
`derived_triples` hazard previews it), Phase 3.1 graded-layer reification, Phase 2.3 name demotion
(oracle-blocked + consumer-less now), Phase 6 oracle retirement (unblocks all the deferred name-drops;
keep the oracle as a safety net THROUGH the firmware build). `tests/test_joern_corpus.py` live-Joern is a
legitimately-slow (minutes) unrelated item — candidate for a `slow` marker.

(Earlier-2026-07-09 hang fixes + pinning-test resolutions that opened this session are in `CHANGELOG.md`.)

## Session-handoff: model routing + "drop-equivalence" reframe (2026-07-10)

**Do NOT start slice 4 (or any multi-step compose+gate) in a nearly-exhausted session** — the full
suite is ~4 min/run and half-work strands the repo. 5.5 3b is a clean committed boundary; start the
next slice fresh.

**Model routing** — ⚠Opus = needs vision-JUDGMENT (Sonnet has deviated here before); ✓S = Sonnet-safe
because a differential gate or precise spec catches a deviation. **Rule of thumb: Sonnet where a gate/spec
catches a wrong turn; Opus where the task IS the judgment (workaround-vs-faithful, KB-vs-engine, classify-
a-divergence, novel design).**
- Slice 4 (plan→act→check→replan as ITERATE×CHECK): **⚠Opus** — "reuse the existing execution loop, don't
  rebuild" is exactly the judgment Sonnet tends to violate (it'll write a new driver).
- Slice 3c (SUPPOSE CNL scope authoring): **⚠Opus** — surface design + variable-length scope.
- 5.5 exit gate (classify divergences ratified-vs-bug): **⚠Opus** — heavy judgment; resist "make it match" hacks.
- Companion: graded α-cut DURING matching **⚠Opus**; aggressive `is_not` completion **⚠Opus**; wire
  `chosen` as declared CHOOSE **~✓S** (gated).
- Phase 2.3 / 2.4 (name→valued attr; name-free identity tokens): **✓S** — mechanical, differentially gated.
- Phase 2.5 (COPULA/NEG_SUFFIX / solve.py preds → KB declarations): **⚠Opus** for "what's KB vs engine";
  **✓S** for the sweep once the boundary is decided.
- Dual-write bridge removal + rewriter retirement: **✓S** sweep — but the DECISION to retire is Opus/user.
- Phase 3.1 step 2 (one-graph fold): **⚠Opus** — control/fact segregation. 3.2/3.4, quote-eval wall: **⚠Opus**.
- Phase 6 demotion decisions **⚠Opus**; the architecture.md rewrite **✓S**.
- Phase 7 perf: **✓S** with benchmarks for the mechanical rungs (intern→ints, CSR, bitsets); **⚠Opus** for
  the design + AOT codegen.

**EQUIVALENCE WITH THE PREVIOUS GENERATION IS NOT REQUIRED — RATIFIED (user 2026-07-10).** The old gen
was never used; the target is a WORKING system, not a matching one. Consequences (act on these freely):
- **Retire the `rewriter` oracle + the `TEMPORARY BRIDGE` dual-write NOW.** They exist ONLY to preserve
  old-system equivalence. Dropping that constraint immediately unblocks every deferred 2.2/2.3 reader flip
  (`nodes_named("<tok>")`→`nodes_with_key`, `startswith("<")`→`is_control`) + name demotion (2.3). Delete
  `_INERT_NAMES`/`_is_inert` too. This is mostly ✓S mechanical once the oracle is gone.
- **The 5.5 exit gate COLLAPSES**: "classify every divergence ratified-vs-bug" → "is the firmware sensible
  and self-consistent on the benches." The single biggest risk-tail (the divergence classification) largely
  evaporates. Still ⚠Opus, but far less of it.
- **Keep GoalSolver** as the firmware's DEVELOPMENT oracle (gate firmware against it during a build), but
  with NO old-answer-preservation constraint — demote/delete purely on firmware coverage.
- **Net reclassification** of the remaining work under "working, not equivalent":
  - Tier-1 (was high-risk) shrinks to just **slice 4 + getting the modes to compose into a genuinely
    working plan→act→check→replan** — judged on "produces sensible answers", not "matches old". Medium → low.
  - The real long-pole for a *usable* system becomes **performance (Phase 7)**, not correctness.
  - Impossible-blocker chance drops to **<5%**; the escape hatches (§8 calculators for expressiveness gaps,
    GoalSolver-as-accelerator fallback, quote-eval wall stays parked) mean "stuck" degrades to "compromise",
    not "dead end".

## Where the system actually is (2026-07-08, 465 tests green — `rewriter` is now a TEST-ONLY oracle)

**PRODUCTION RUNTIME IS 100% THE ISA ENGINE.** No production code path calls the reference `rewriter` at
runtime: recognition, reasoning, control, planner, retraction (INTERPOSE), coref, decide, rule-source
recognition, the read-side matcher (`query`→`match_pats`), and the generic `driver` all run on `run_bank`/
`GoalSolver`. `rewriter.py` is RETAINED as the differential-test ORACLE (it caught the fired-keying bug this
session); its deletion is a Phase-6 test-oracle-retirement decision, decoupled from production. `Firing` moved
to `production_rule.py` (engine-neutral). The `run_rules` `isa=False` branch + `__init__`/`authoring` rewriter
imports survive ONLY as oracle access (`test_isa_interpose` differential + ~30 tests via `h.run`/`run_rules`).


DONE by the re-host arc: substrate unified (`world_model.Graph = AttrGraph`, one label-less
store); the backward ISA engine (`GoalSolver`/`ask_goal`) is the production answer path with
CWA-default demand-completion; recognition runs on the forward ISA `Machine` (`run_bank`),
differentially proven == `rewriter.run`; coref MERGE retired everywhere (additive `same_as`);
coref-following de-hardcoded (bank-declared, gated); recognition scaffolding control-demoted;
`skip_inert` matching fix. ALL recognizers on `run_bank` (Phase 0.2). Phase 0.3 DONE 2026-07-08:
the PLANNER's reasoning + control + teardown now run on `run_bank` (`run_rules(isa=True)` at
`plan()`/teardown) — control-stamp at MINT, `drop`→DROP_CTRL, `<call>` servicing, plus the
reasoning-parity fix (literal-endpoint INTERN + relation DEDUP) that closed the value→plan
divergence, and tool-minted control markers now stamp control so DROP_CTRL teardown works.
Phase 0.4 DONE 2026-07-08: the coref/graded reasoning passes (`_coref_propagation`, `graded_rules`
via a new dynamic-key `EMIT`) run on `run_bank` in the batch loaders AND the live Session. Phase 0.5
(cont.) 2026-07-08: **`run_bank(provenance=True)` mints J/proves/uses** at parity with `rewriter._apply`;
**cpg recognition + walker migrated**. Then **built the `INTERPOSE`/`RESTORE` opcodes** + `rewire`→INTERPOSE
lowering + per-rule provenance-awareness in `run_bank`, and **routed TMS retraction (`retraction.retract`,
`decide` phase 2) to `isa=True`**. Then **migrated `coref_walk` + `session` DEMAND_COREF** (stamped the
cursor scaffolding control in `materialize_cursor`/`settle_tool` → the `<coref>`-gated `ADVANCE` `drop`
lowers to DROP_CTRL; `same_as`/`not_same_as` heads are now control-stamped, a ratified divergence like the
walker shortcut) and **`decide` phase 1** (completion/defeat/entailed-negation, the CWA oracle) — so
`decide` is FULLY on the ISA. Every `run_rules` production caller now passes `isa=True` (the `isa=False`
fallback is dead in production). **Deleting `rewriter.py` now gated on ONE production `run` caller:**
`session.py:480` rule-source recognition — DONE 2026-07-08 (`run_bank(self.kb, forms)`). The investigation
(`finding-session480-not-phase41`) found this was **NOT Phase 4.1**: the whole-graph double-fire was a
`fired`-suppression keying bug (the `forms` list has 14 DUPLICATE rule keys; rewriter keys `fired` by
(rule.key, bindings) → duplicates share suppression, run_bank keyed PER-INDEX → each fired → duplicate NAC).
FIXED: `run_bank`'s `fired` now keyed by (rule.key, sig) like rewriter (differential-clean on a twice-listed
rule); whole-graph is correct (`normalize_surface` strips prior chains); the recognition journal isn't
surfaced in `explain`. **No forward-`run` production callers remain — deleting `rewriter.py` is now a
MECHANICAL sweep:** the `run_rules` `isa=False` fallback (`authoring.py:995`, dead in production), `rewriter.match`
(query + tests), `Firing` (surface/driver — a dataclass to relocate), `driver.py:55`. **Phase 4.1 (semi-naive)
is a real PERFORMANCE item, OFF the deletion path.** 465 tests green.

## Phase 0 — ONE ENGINE: finish the peel, delete `rewriter` (absorbed from the re-host handoff)

0.1 **Optimize `run_bank` (the gate everything waits behind).** DONE (2026-07-07): two
    content-blind, differential-proven wins took it from ~89× slow on `planning.cnl` (9.6s) to
    2.6× (273ms), 1.0–5.1× across all ten banks, every output IDENTICAL. (a) **name-index SEED**
    — a `name = X` seed hits the O(1) `nodes_named` accelerator instead of scanning every named
    node (88.8×→33.1×); (b) **bound-endpoint join driving** — a literal-predicate pattern whose
    endpoint an earlier pattern bound reaches its rel node by FOLLOWing from that bound node + a
    name TEST, not a fresh whole-predicate SEED + SAME (kills the `next`-chain cross-product;
    33.1×→2.6×; `_match_step` 3.86M→243k calls). Remaining factor is pure cross-round re-matching
    — the semi-naive/`<fresh>` change-frontier (the `processing_modes.md` SATURATE discipline) +
    NAC-from-bound-endpoint are NOT yet needed (absolute times ≤240ms; the intra-match pathology
    is gone). Revisit if a much larger bank regresses.
0.2 **Move the remaining recognizers onto `run_bank`** (`load_rules`/`load_universal_rules`/
    `load_loose_rules`/`load_machine_rules`). DONE (2026-07-08): all four rule loaders now
    recognize via `run_bank` (the ISA forward Machine) instead of `rewriter.run`; the
    `rewriter` import dropped from `machine_rules.py`. Unblocked by 0.1's perf work; 449 tests
    green, suite 99s→82s. `load_facts`/`load_corpus` were already on `run_bank`. The only
    remaining `rewriter.run` callers are the reasoning passes (`_coref_propagation`, `graded_rules`)
    = Phase 0.4, and the planner teardown `drop`s = Phase 0.3.
0.3 **Planner control onto the ISA**: `DROP_CTRL` lowering + control-stamp-at-MINT.
    DONE (2026-07-08): `plan()` reasoning/control AND the teardown now run on `run_bank`
    (`run_rules(isa=True)`); the reasoning-parity gate is closed.
    - **Control-stamp at MINT** (`lowering.lower_rhs`): a relation minted by a rule that references
      a `<…>` control token is flagged `control` — the content-blind, PRODUCER-side criterion
      (drop-independent, so DROP_CTRL's fact-refusal keeps teeth). Design ratified with the user
      against `vision.md` §5/§1-amendment ("no python logic": control-ness = reserved `<…>` syntax
      + structural propagation, never a domain-predicate list).
    - **`drop` → DROP_CTRL** (`lowering.lower_drop`/`_lower_bank_rule`): a control rule's `drop`
      deletes a reified control relation via DROP_CTRL over both bare edges; run_bank gc's the
      orphaned control rel node. Refuses a fact drop.
    - **`<call>` tool servicing in `run_bank`** (parity with `rewriter.run`'s tool loop).
    - **REASONING-PARITY FIX (the gate that was blocking):** recognition compared graphs as SETS of
      triples, which hid two NODE-IDENTITY properties reasoning needs. (a) **INTERN** — a head
      endpoint that is a PLAIN LITERAL now canonicalizes to its graph-wide node (`MINT(intern=)`,
      `rewriter.resolve_so`), so a downstream rule joins two head-derived literals by identity
      (the `test_cards_frontier` value→plan divergence was a split `have_valuable`, NOT a
      control-stamp bug). (b) **DEDUP** — a reified relation reuses an existing `s -[rel]-> o`
      (`MINT(dedup=)`, `rewriter._relation_exists`), so a rule re-fired across outer control cycles
      stops accreting duplicate rel nodes and the graph's EDGE set (hence `_fingerprint`) reaches a
      fixpoint. The "perf regression" was mostly this accretion. `test_isa_reasoning_parity.py`.
    - **Tool-minted control markers** (`planning._control_relation`): `done`/`ranked`/`price_known`
      are written by §8 TOOLS via `add_relation` (fact rel nodes), which `DROP_CTRL` would refuse.
      The tool now stamps the rel node control when it targets a `<…>` token — content-blind, the
      same reserved-syntax criterion; a fact a tool writes (`cheaper_than`, a price) stays a fact.
    - Differential-clean: `run_bank` == `rewriter.run` on the cards-frontier value→plan scenario
      (derived triples, chosen operators, cycle count all identical); 456 tests green.
0.4 **Graded/coref reasoning passes onto the ISA**: DONE (2026-07-08). `_coref_propagation` (plain
    `same_as` rules) and `graded_rules` (`propagate` → `EMIT`) now run on `run_bank` in BOTH batch
    loaders (`load_facts`/`load_corpus`) AND the live `Session` graded pass. New capability:
    `EMIT(key_reg=, raise_degree=False)` — a DYNAMIC-key graded SET (the embedding dim is the NAME
    of a bound register, e.g. `?adj`→"urgent"), lowered by `lowering.lower_propagate` (the ISA face
    of `rewriter._propagate_ops`; SET semantics, matching `set_embedding`'s overwrite). Differential-
    clean vs `rewriter.run` (`test_isa_reasoning_parity.py`: dynamic-key, literal-dim, and the
    end-to-end graded pass). 459 tests green; the batch loaders no longer touch `rewriter` for the
    reasoning passes. **NOTE for 0.5:** the plan's "only remaining `rewriter.run` callers" was
    optimistic — beyond these, `rewriter.run` is still called by the module-level recognition/tool
    passes (`deontic`/`forms`/`query`/`procedure`/`planning_kb`/`session._surface`, `walker`,
    `coref_walk`, `session` DEMAND_COREF) and the `run_rules` `isa=False` fallback (`authoring.py`
    line 995) + the degree-graph recognition (line 175). 0.5 must migrate ALL of them.
0.5 **Retire `rewriter.py` from production** (delete deferred to Phase 6 as a test-oracle decision).
    DONE (2026-07-08, 465 green). The blockers below were real and are resolved in the order the
    findings predicted:
    - Clean additive migrations (`deontic`, `procedure`, `planning_kb`, `query`, degree-graph
      recognition) landed first, `run(tmp, …)` → `run_bank(tmp, …)`.
    - **Phase 2.2 scaffolding slice** (control-flagging `next`/`first`/scaffold predicates) unblocked
      `normalize_surface` onto `run_bank`, as predicted.
    - **`INTERPOSE`/`RESTORE` opcodes built** (`decision-interpose-opcode`) unblocked every remaining
      `drop`-a-fact-edge caller: `coref_walk`, `session` DEMAND_COREF (cursor scaffolding
      control-stamped), `decide` phase 1 (CWA oracle) and phase 2, `retraction.retract`.
    - **`session.py:480` rule-source recognition** — the last forward-`run` production caller — was
      NOT actually gated on semi-naive SEED (Phase 4.1) as this plan once assumed; investigation
      (`finding-session480-not-phase41`) found a `fired`-suppression keying bug (duplicate rule keys
      in `forms`, keyed per-index instead of by `(rule.key, sig)`). Fixed directly; Phase 4.1 stays a
      pure PERFORMANCE item, off the deletion path.
    - Mechanical remnants swept: `Firing` → `production_rule.py` (engine-neutral); `query.ask`'s
      matcher → `lowering.match_pats`; `driver.drive` → `run_rules(isa=True)`/`run_bank`.
    - **Result: no production runtime path calls `rewriter`.** Every `run_rules` caller in production
      passes `isa=True`; the `isa=False` branch, the `__init__`/`authoring` `rewriter` imports, and
      `rewriter.py` itself are RETAINED deliberately as the differential-test ORACLE (user's call —
      it caught the fired-keying bug this session). Deleting the file outright is a Phase-6 decision,
      decoupled from production correctness. See `finding-surface-rewriting-blocks-rewriter-deletion`.

## Phase 1 — STABILIZE the oracle (before firmware builds on it)

1.1 **DONE (2026-07-08, 465 green).** Fixed known `GoalSolver` staleness (`harneskills/isa/goal.py`):
    `_sa_union` now invalidates the losing class-rep's cached tokens (`_invalidate_class`) so members
    re-file under the merged rep; `_token`/`_ensure_node` keep `_token_class` live as a side effect
    of computing/minting a token (not just at `__init__`); `_materialize` unions `same_as` endpoints
    whenever ANY rule head derives `same_as` (not just the `universal.same_as_rules` propagation set,
    which is filtered out of `self.rules` entirely). **Widened beyond the plan's original scope:**
    `_name_ids`/`_sa_parent`/`_tok_cache`/`_token_class` are now threaded through nested-solver
    construction (`_group_satisfiable`, `_complete_negative`) exactly like `_materialized`/
    `_justified`/`_skolem` already were — a nested completion deriving `same_as` was invisible to the
    outer solver's identity caches until the nested frame returned and its private copy was discarded.
1.2 **DONE (2026-07-08, 465 green).** Cached `_group_satisfiable` (`harneskills/isa/goal.py`): keyed
    by `(id(group), env restricted to the group's own vars)`, valid only while `len(self._materialized)`
    — a monotonic, already-shared-across-nested-solvers epoch — hasn't grown since caching, so a later
    derivation anywhere can never leave a stale UNSATISFIABLE verdict cached. Still constructs a fresh
    nested `GoalSolver` on a miss (that construction cost is untouched); the win is repeat checks of
    the same group under the same relevant bindings.
1.3 **DONE (2026-07-08, 465 green).** Stratification LINT at bank load (`authoring.lint_stratifiable`,
    reusing the existing `stratify`/`lint.py` negation-cycle check): wired eagerly into `load_rules`
    (the CNL rule-parsing choke point) and `load_corpus` (the whole-corpus loader most tests/benches
    use), raising immediately with the offending source named. `run_rules`'s runtime graceful
    degradation (`_strata_or_degrade`, `strict=False` warns-and-drops) is UNCHANGED — this only adds
    an earlier, louder checkpoint at load, it does not touch execution semantics. Not wired into the
    live `Session._reason_bank` (rebuilt every reasoning step from domain rules + universals +
    same_as propagation) — that path intentionally combines sources incrementally and already has a
    documented no-false-cycle rationale; adding a hard raise there risks turning today's graceful
    per-step degradation into a live-session crash, out of scope for this pass.
1.4 **DONE (2026-07-08, 470 green).** Adversarial tests (`tests/test_isa_goal_adversarial.py`):
    goal-visitation-order independence (one `GoalSolver` answering several independent goals gets
    the same per-goal verdict in either order — no cross-goal bleed through `.solve()`'s shared
    tables/semi-naive state); derived-`same_as` (a rule-derived union is visible immediately, both
    from a top-level `_materialize` and from a NESTED solver's); `_group_satisfiable`'s cache never
    serves a stale verdict past a new derivation; a genuine cross-goal negation cycle raises
    `NonStratifiable` regardless of which side is asked first. **Writing test 1 surfaced a real gap
    beyond 1.1's original fix**, caught by the adversarial discipline itself: `_token_class` was
    populated incrementally (one node at a time, whichever node happened to have `_token()` called
    on it), so a class token could be cached PRESENT-BUT-INCOMPLETE — `_nodes_of_token` would then
    short-circuit on the stale partial list forever. Fixed by making `_token_class` a pure CACHE:
    `_token()` no longer writes to it; `_nodes_of_token` fully (re)scans same-named nodes on a miss,
    filtered through `_token()` itself (not a raw `_sa_find` comparison — that regressed coref-BLIND
    mode, briefly re-merging `same_as`-linked-but-undeclared mentions, caught by the existing
    `test_goalsolver_is_coref_blind_without_the_propagation_rules`); `_sa_union` invalidates BOTH
    the losing and winning rep's cached bucket (the winning side's enumeration is stale too, not
    just wrong). These gate every later phase — the interim engine is the differential oracle for
    firmware, so it must be trustworthy.

**Phase 1 exit gate reached (2026-07-08, 470 green):** `GoalSolver` staleness fixed and widened to
nested solvers, `_group_satisfiable` memoized safely, stratification checked at load, adversarial
coverage in place. Next: Phase 2 (attribute-native conventions).

## Phase 2 — ATTRIBUTE-NATIVE conventions (namelessness for real)

2.1 **Predicates become graded KEYS** (`{chase: 1.0}` on the event node), not node names;
    `add_relation` becomes sugar; seeding moves to the blessed `nodes_with_key`/`key_count`
    df index. Closed key vocabulary = the KB's verb/attribute catalog.
    DONE (2026-07-08, 470 green). `add_relation` (attrgraph.py) now mints the rel node's
    predicate as a GRADED key (`rel_name: 1.0`) — the canonical representation — and the core
    ISA reference machine (`lowering.py`'s `lower_conj`/`lower_drop`/`lower_rhs`, `goal.py`'s
    `_facts_matching`/`_materialize`, `solve.py`'s predicate checks) seeds/tests predicate
    identity via `nodes_with_key`/`has_key`, not `name` equality. **Dual-write bridge (user's
    call, TEMPORARY, grep "TEMPORARY BRIDGE" to find every site):** `add_relation` and the
    `to_attrgraph`/`lower_rhs` mint paths ALSO still write the legacy VALUED `name` attr, so
    `rewriter.py` (kept as the differential-test oracle; reads relations via `graph.name`/
    `nodes_named` uniformly for entities and predicates) keeps working unchanged — drop the
    `name` write at Phase 6 alongside rewriter's retirement. One real bug surfaced and fixed by
    the differential suite: several production sites (`solve.py`'s `_mint_marker`/`_mint_chosen`,
    `walker.py`'s `_materialize_shortcut`) hand-minted rel nodes with `add_node`+`add_edge`
    instead of `add_relation`, bypassing the dual-write; routed through `add_relation` now.
    `to_attrgraph` (the name-`Graph`->`AttrGraph` bridge) needed its own post-pass to predicate-
    key copied relation nodes. **Reserved-key collision found and guarded:** a domain predicate
    literally named `name` (e.g. a CPG `name` property) IS the reserved NAME key — writing a
    GRADED `name` too would clobber the just-written VALUED `name`; `add_relation` and the two
    other mint sites skip the graded write in this one degenerate case (pinned by
    `test_add_relation_name_predicate_does_not_clobber_the_reserved_key`). Also fixed:
    `AttrNode.embedding` now returns `{}` for a provenance-inert node — a `proves`/`uses` rel
    node's predicate key was otherwise leaking into the "embedding" view (`test_isa_reasoning_
    parity.py` caught this). Out of scope (deliberately, per the plan): the ~140 `add_relation`
    call sites in domain files (planning.py, provenance.py, deontic.py, etc.) and their paired
    `graph.name(rel) == "pred"` reads — unaffected by the bridge, swept in Phase 6.
2.2 Keyword/control tokens (`<goal>`, `<current>`, `<frame>`, `<disabled>`) become keys on
    control-flagged nodes; provenance inertness = the `control` flag (kills `_INERT_NAMES`
    and `<j:` prefix sniffing, incl. the `skip_inert` name-check — becomes a flag check).
    SLICE DONE (2026-07-08, out of order — it gates Phase 0.5): the **surface recognition
    SCAFFOLDING is now control-typed.** `tokenize` marks the `<sentence>` anchor + `next`/`first`
    chain control; `run_bank(control_preds=)` + a PER-ATOM rule in `lower_rhs` mark a head whose
    PREDICATE is a scaffolding predicate (`forms.SCAFFOLD_PREDS = {next, first, *SURFACE_TAGS}`)
    control regardless of the rule — so a form reads the chain and mints CONTENT (fact) while its
    `next`/`first` bridge stays control. This let `normalize_surface` (determiner strip + NP
    decompose, whose `drop`s of `next`/`first` were `DROP_CTRL`-refused as fact edges) move onto
    `run_bank`. Two obsolete GoalSolver-recognition tests retired (recognition is `run_bank`'s job;
    the reasoning engine correctly can't see control scaffolding).
    **`_is_inert` → flag, SLICE 2 DONE (2026-07-09, 469 green):** the WORLD_MODEL SUBJECT-FINDER
    family — the 8 identical `next((n for n in g.into(r) if not _is_inert(g.name(n))), None)` readers
    across `authoring`/`deontic`/`forms`×3/`planning_kb`/`session`×2, plus the equivalent
    `decide.py`'s closed-world-predicate collector — now read the `.inert` FLAG (`g.is_inert(n)`),
    and the dead `_is_inert` imports were dropped from all 6 files. PRECONDITION first: the two
    remaining UNFLAGGED provenance mint sites (`provenance.ensure_axiom`'s `<axiom>` node,
    `axiomatize`'s `<axiom>--proves-->rel`) now pass `inert=True`, so every `<j:>`/`<axiom>`/`proves`/
    `uses` node an `into(r)` subject-scan can encounter carries the flag (all other mints — goal.py,
    lowering.py, rewriter.py — were already flagged). `universal.py`'s `entailed_negation_rules`
    node-loop also flipped (its `_is_inert(name)` → `graph.is_inert(n)`; the sibling
    `name.startswith("<")` control-token filter is untouched — that's the separate "control TOKENS as
    keys" sub-item). Differentially clean against the still-name-based `rewriter` oracle (469 green).
    **The `_is_inert`→flag NODE-INSTANCE migration is now COMPLETE** — every remaining `_is_inert` call
    is in a category that STAYS name-based BY DESIGN, not a deferred flip:
    - PATTERN/LITERAL-side guards over rule/goal tokens (a literal is a STRING, not a materialized node,
      so there is nothing to flag-check): `goal.py:727/743` (guards the GOAL ATOM's rendered subj/obj
      literal — its actual node-instance obj/subj checks at `:736/:752` ALREADY use the flag),
      `lowering.py:400/573`, `rewriter.py:78`.
    - The `rewriter` ORACLE itself (`rewriter.py:59`) — reads entities and predicates UNIFORMLY by name
      by design; must stay name-based until it is retired (Phase 6).
    - `lowering.py:86` (`to_attrgraph`, the name-`Graph`→`AttrGraph` BRIDGE) — accepts arbitrary (incl.
      test-built) source graphs where the flag guarantee is weaker than the name convention, and it is
      slated for deletion at Phase 6; name-based is the safer guard for bridge code with a Phase-6 expiry.
    NON-BLOCKER RESOLVED: the `<retracted>` marker is NEVER `inert`-flagged (so `_is_inert` name-fn is a
    strict SUPERSET of the flag). A retracted fact is hidden because the interposed marker's NAME doesn't
    match the goal's object (`goal.py:736` sees `<retracted>` as a NON-inert successor whose name simply
    fails `_endpoint_matches`), NOT because it is inert-skipped; the retraction suite + the new guard test
    confirm this. Its `control` state is PATH-DEPENDENT (control via the ISA INTERPOSE mint `machine.py:476`,
    UNflagged via the rewriter-oracle rewrite path — surfaced by the guard test), and irrelevant to the
    subject-finder flip. No inert-vs-control change to `<retracted>` is needed.
    GUARD TESTS added (`tests/test_meta_provenance.py`, 2026-07-09): the migration's soundness rests on
    "every provenance node an `into(r)` scan can meet is `inert`-flagged" — pinned now on BOTH mint paths
    (`test_inert_flag_covers_every_provenance_mint_{oracle,isa}_path` assert
    `is_inert(n) ⟺ name∈{proves,uses,<j:…>,<axiom>}` after a prov-on run + `axiomatize`), so a future
    unflagged mint FAILS LOUDLY instead of silently leaking (the 2026-07-09 exponential-hang class);
    `test_retracted_marker_is_not_inert_flagged` pins the `<retracted>` superset divergence.
    STILL TODO in 2.2 — but NOT the mechanical flip this plan once implied: control TOKENS as keys.
    **KEY FINDING (2026-07-09): `startswith("<")` is NOT the debt `_INERT_NAMES` was, and must NOT be
    flipped to `is_control`.** `_INERT_NAMES = {proves, uses}` was a hardcoded CONTENT list (rightly
    replaced by the flag). `startswith("<")` is the RATIFIED, content-blind RESERVED-SYNTAX criterion
    (`decision-control-ness-criterion`; `lowering._is_control_token`, `lint.is_control_token`,
    `planning.py:229/235`) — the canonical test for "is this a reserved token." Flipping the node-instance
    `startswith("<")` readers (`forms.py:473/507/548` canonicalize/wire_same_as, `universal.py:90`) to
    `is_control(n)` would REGRESS: `<axiom>` is `inert`-flagged NOT control, and many `<…>` tokens
    (`<demand>`/`<call>`/`<query>`/`<wh>`/`<contradiction>`/…, minted across ~a dozen files) are not
    uniformly control-flagged — so `is_control` would misclassify them as coreferable ENTITIES. The
    syntactic test is correct and STAYS. So "control tokens as keys" is genuine REPRESENTATIONAL work
    (make the token an attribute KEY on a control-flagged node + flag every mint site), NOT a reader
    sweep — a deliberate design slice.
    **CONTROL-TOKENS-AS-KEYS, HALF 1 DONE (2026-07-09, ADDITIVE, oracle-safe):** the name->key dual-write.
    A reserved control token (`<…>` syntax) minted as a NODE (`AttrGraph.add_node("<goal>")`) now ALSO
    carries its token as a GRADED key `{<goal>: 1.0}` — the same dual-write `add_relation` already does
    for control PREDICATES — so `nodes_with_key`/`has_key` can eventually replace the name-based
    `nodes_named("<token>")` reads (the Phase-6 reader flip). Reserved to `<…>` names (an ordinary entity
    like `Paul` gets NO graded key — pinned). `AttrNode.embedding` filters `<…>` keys back out (like an
    inert node reports none), so the fuzzy/similarity/`propagate` view stays token-free. **T-norm is
    unaffected** (a token key is always degree 1.0 = identity for T_MIN/T_PROD, and degrees only compose
    into `score` via explicit GRADE/FUZZY α-cut ops that crisp token matching never invokes — so the
    regular graded namespace is safe; the `<…>` syntax gives the view-level distinction for free, no
    reserved namespace needed). Additive: the legacy VALUED name stays (oracle bridge), so NO current
    reader changes; differentially clean (472+3 tests). Repr choice ratified with the user: graded key in
    the regular namespace + embedding `<…>` filter. Tests: `test_control_token_node_dual_writes_*`,
    `test_ordinary_named_node_gets_no_token_key`, `test_token_key_is_excluded_from_the_embedding_view`.
    **HALF 2 DONE (2026-07-09, differentially proven behavior-neutral):** control-ness at the mint
    chokepoint. `AttrGraph.add_node` now applies the ratified criterion — reserved `<…>` syntax + NOT inert
    ⟹ `control=True` — so every control token is flag-queryable (`is_control`) for the Phase-6 reader flip;
    inert provenance (`<j:…>`/`<axiom>`, minted `inert=True`) is EXCLUDED (inert, not control); a caller's
    explicit `control=` only promotes, never demotes. This was the behaviorally-consequential half (the flag
    is READ in production: `goal.py` control-rel skip, `DROP_CTRL`, `_fingerprint`'s control-edge exclusion),
    so it was run as a HYPOTHESIS gated by the full differential suite rather than assumed additive. RESULT:
    behavior-neutral across all 475 tests except ONE — `test_isa_drop.py::test_drop_of_a_fact_is_refused`,
    a RATIFIED divergence: a bare edge-less `<go>` token is now control, so `run_bank`'s orphan-control GC
    sweeps it (correct — orphan control scaffolding is ephemeral; real control tokens always carry edges).
    Test re-establishes the token before use. So the "family-by-family" caution proved empirically
    unnecessary — the single content-blind rule at the chokepoint is safe and is the clean realization.
    Pinned: `test_reserved_token_mint_is_control_but_inert_provenance_is_not`.
    **2.2 REMAINING = the Phase-6 reader flip only** (blocked on the oracle): `nodes_named("<token>")` →
    `nodes_with_key("<token>")`, and the node-instance `startswith("<")` checks (`forms.py:473/507/548`,
    `universal.py:90`) → `is_control(n)` — now SAFE because every token is flagged, but deferred with the
    dual-write name drop until the oracle retires. Then name demotion (2.3), and delete `_INERT_NAMES`/
    `_is_inert` at Phase 6 alongside the oracle + bridge retirement (the only readers left).
2.3 `name` demoted to an ordinary VALUED attr; value-accelerator indexes exist ONLY for
    KB-DECLARED discriminating keys (`name is a discriminating key`).
2.4 Identity tokens name-free (coref-class representative nid, not `name\x00rep`); rendering
    back to surface happens at the output boundary only.
2.5 `COPULA`/`NEG_SUFFIX` and `solve.py`'s predicate list → KB declarations.
    Exit gate: engine code grep-clean for predicate/key strings; benches green.

## Phase 3 — RULES AS DATA (homoiconicity)

> **SCOPING DECISION (2026-07-09, chosen with the user): Phase 3 is being done AS THE PREREQUISITE FOR
> PHASE 4's firmware, and the firmware needs the reified rule SHAPE (walkable in-graph structure), NOT
> the "built by FORM rules" authoring.** APPLY (4.2) walks body atoms as graph structure; CHAIN (4.3)
> reads the in-graph head index (3.3) — neither cares whether the structure was authored by Python
> `write_rule` or by FORM rules. So the **meta-circular FORM-rule authoring (the quote/eval wall the
> codebase deliberately parks — `rule_graph.py`'s note: a FORM rule building a rule must create a node
> literally NAMED `?a`, but the engine reads `?a` as a variable) is DEFERRED** as a homoiconicity-purity
> milestone off Phase 4's critical path. 3.1 here = MODERNIZE the reified shape (2.1/2.2-aligned) so
> APPLY/CHAIN can walk it, keeping the Python builder for now.

3.1 Canonical rule shape in-graph: rule node + head/body-atom pattern nodes + shared var
    nodes. (Original scope also said "built by FORM rules (no Python parser)" — DEFERRED per the
    scoping decision above; that is the parked quote/eval wall, not on Phase 4's path.)
    **STEP 1 DONE (2026-07-09, 476→478 green):** `rule_graph.write_rule` modernized to the 2.1/2.2-aligned
    canonical shape. (a) Every rule-structure node — the rule node, shared var/literal nodes, per-Pat
    predicate nodes, and role relations — is now `control`-flagged, so a folded ONE-graph can segregate
    pattern-space from fact-space by the control flag (the `goal.py` control-rel skip) instead of the
    current separate rule-graph — the meta-circular one-graph milestone, unblocked by 2.2. (b) Each pattern
    atom is built in FACT SHAPE via `add_relation` (predicate carried as a graded KEY `{is_a: 1.0}`, not a
    bare name), so a reified rule is literally in the shape of the facts it rewrites and the firmware's
    APPLY can seed a pattern predicate through `nodes_with_key`/`has_key` exactly as it seeds a fact.
    Round-trip (`rules_in_graph`) unchanged and exact (name-based read still works via the dual-write
    bridge); differentially clean (full suite). Pinned:
    `test_reified_rule_is_control_layer_and_pattern_predicates_are_keyed`.
    **STEP 2 NEXT:** demonstrate/prove pattern nodes stay fact-INVISIBLE when the rule fragment is folded
    into a live fact graph (the control flag is the segregation) — the one-graph fold. **STEP 3:** 3.3's
    head index as graph structure. **DEFERRED:** the graded/control layer (`probability`/`graded`/
    `propagate`/`priority`/`rewire`/`meta`) is not yet reified (b1 limitation) — encode when the firmware
    needs it (mostly Phase 5); and the FORM-rule authoring (quote/eval wall).
    **TRACKED (from Phase 5.4b, 2026-07-10): the `same_as propagates through X` CNL surface lands
    HERE.** Coref-follow is now a declared `coref_prop` tag on the rule (5.4b), which kills the engine
    sniffing but leaves TWO Python-policy residuals: `session.py:CONTENT_PREDS` chooses which predicates
    propagate coref, and `universal.same_as_rules` generates the propagation rules in Python. The
    vision-faithful fix — a bank-authored `same_as propagates through X` declaration that reifies/authors
    the coref rules AND signals following — is a homoiconicity item that belongs with this phase's
    reified-rule authoring (it can't be done whole until the coref rules reify). When built, the
    `coref_prop` Python flag becomes a graph attribute on the reified rule node (same `GoalSolver` read
    site). Until then it is a KNOWN, logged `no-python-for-banks` deviation, not a silent one.
3.2 Runtime rule edits by user CNL: add = same path as facts; disable = additive `<disabled>`
    marker; re-enable = control-layer op. No rule deletion (§5 holds for rules).
3.3 Head index as graph structure (catalog-key → rule nodes, wired at load).
    **DONE (2026-07-09, `apply.build_head_index`/`rules_producing`, 487 green):** a `<head-index>` hub with,
    per rule, a relation `hub -[headPred]-> rule_node` for each head (rhs) predicate — the catalog-key→rule
    map as SUBSTRATE structure (queried through `relations_from`, no Python dict), built to CHAIN's now-known
    query ("which rules produce this goal predicate"). Idempotent. Pinned in `tests/test_isa_chain.py`.
3.4 **Collections as first-class KB structure**: member `next`-chains + list-authoring CNL
    forms (the ITERATE substrate — `processing_modes.md` §1).
    Exit gate: every bank rule round-trips CNL → rule subgraph → rendered CNL.

## Phase 4 — FIRMWARE v1: APPLY + CHAIN (the positive core)

4.1 Token conventions as control gadgets: `<frame>` (bindings), `<demand>` (magic-sets made
    literal), `<fresh>` (semi-naive delta), `<current-atom>` cursor. GoalSolver's hidden dicts
    become visible graph structure.
    **APPLY-SIDE DONE (2026-07-09, 490 green, `harneskills/isa/apply.py`):** `<frame>` (bindings) was
    already done in 4.2. Added this session:
    - **`<current-atom>` cursor** — `_build_itinerary` materializes the df-sorted body as a VISIBLE
      `next`-chain of `<atom>` step nodes (each carrying `(subj,pred,obj)` as VALUED attrs) with a
      `<current-atom>` cursor at the head; `_apply_pass` reads the current atom FROM the cursor and
      ADVANCES it along `next`, killing the Python loop index. The itinerary is FRESH control nodes only
      (never touches the reified rule's patoms — an edge into a patom corrupts `_read_atoms`) and is GC'd
      with the frames. Pinned: `test_body_atom_cursor_is_a_visible_itinerary_that_advances`.
    - **`<fresh>` semi-naive delta** — `apply_to_fixpoint` full-joins once (seed) then re-derives only from
      the previous round's DELTA (delta-substitution: each body position in turn draws from `fresh`, others
      full — mirrors `GoalSolver._delta_join`); the delta atom is marked `<fresh>` on the itinerary. SUBTLETY
      caught in design: `_apply_pass` re-sorts by df each call, so the fixpoint FREEZES one df order per round
      and threads it to every position's pass — else `delta_pos` could name different atoms across a round and
      an atom might never take its delta turn (a silent incompleteness). Differentially identical to the naive
      fixpoint (`run_bank`). Pinned: `test_fresh_delta_atom_is_marked_visible_on_the_itinerary`,
      `test_semi_naive_fixpoint_derives_the_full_transitive_closure_over_many_rounds`.
    **CHAIN SIDE DONE (2026-07-09, 493 green, `harneskills/isa/chain.py`):** `chain_sip(fact_g, rule_g,
    (pred, subj|None, obj|None))` promotes `<demand>` from the PREDICATE grain (4.3, restricts which RULES
    run) to the BOUND-TUPLE grain (restricts which TUPLES). A demand is a bound tuple on a `<demand>` node
    (`for=/subj=/obj=`); evaluation INTERLEAVES demand-raising with per-env body evaluation (a body atom's
    sub-demand is raised under the env bound so far, so an earlier atom's answer grounds the next atom's
    demand) to a fixpoint. Prunes by SUBJECT/OBJECT: goal `is_a(socrates,?)` never demands a second
    philosopher `plato` (`run_bank`'s closure has `plato is_a mortal`; `chain_sip` doesn't, while COMPLETE for
    the socrates tuples). BUG caught by the differential gate: df-selectivity seeding (APPLY's heuristic) is
    UNSOUND for SIP — it can front-load an atom whose join var is unbound, raising `(pred, None, None)` that
    floods off-goal tuples; fixed with `_sideways_order` (binding order, not selectivity). v1 scope: positive
    rules, plain-literal preds, unique-noded names; the per-env bindings stay a Python env (the visible gadget
    is the bound `<demand>`; a `<frame>` env is a later unification). Pinned:
    `test_chain_sip_is_complete_for_the_goal_tuple_and_prunes_by_subject`,
    `test_chain_sip_demands_are_bound_tuples_visible_as_nodes`, and a two-chain transitive goal.
    **PHASE 4.1 IS NOW COMPLETE** (all four gadgets: `<frame>`, `<current-atom>`, `<fresh>`, bound `<demand>`).
4.2 APPLY: serial body-atom cursor, df-seeded candidates one at a time into the frame,
    comparator TESTs on attributes, head EMIT with check-before-derive (materialized facts =
    the memo table). Fuel-bounded.
    **v0 DONE (2026-07-09, `harneskills/isa/apply.py`, 482 green): the firmware thesis proven on the
    positive core.** `apply_rule`/`apply_to_fixpoint` match a REIFIED rule (Phase 3.1's in-graph shape,
    read straight from `rule_node` — "APPLY over reified rules") against the facts and EMIT the head, with
    the binding environment held as VISIBLE graph structure: a partial match is a `<frame>` control node
    and each binding is a reified relation `<frame> -[?var]-> node` (the "GoalSolver's hidden dicts become
    visible graph structure" win of 4.1, realized for the bindings dict). df seed-from-rarest (the only
    heuristic); EMIT is monotone with CHECK-BEFORE-DERIVE (an existing head fact is the memo → skipped →
    a recursive rule terminates under the `apply_to_fixpoint` SATURATE wrapper); FUEL-bounded. DIFFERENTIALLY
    GATED against `run_bank` (`tests/test_isa_apply.py`): single-atom body, 3-way join, TRANSITIVE recursion,
    near-miss — APPLY over the reified form derives EXACTLY what `run_bank` derives over the Python `Rule`.
    One real bug caught+fixed by the differential gate: an in-graph frame binding adds an INCOMING edge to
    the bound fact node, which makes an entity look like a rel node to `derived_triples` (a fact reader that
    doesn't filter control) — so the ephemeral working frames (nodes AND binding rel edges) are GC'd cleanly
    after each pass; this previews the one-graph-fold hazard (Phase 3.1 step 2). **v0 SCOPE:** positive
    rules only (NAC/graded = Phase 5 CHECK/CHOOSE); plain-literal predicates; head slots resolve to a bound
    var or literal (fresh-RHS-node MINT deferred); the driver is Python (ratified reference style) with the
    BINDINGS as visible graph structure. **UPDATE (2026-07-09, Phase 4.1):** the body-atom cursor is no longer
    the driver's loop position — it is now a VISIBLE `<current-atom>` token over a `next`-chain itinerary, and
    `apply_to_fixpoint` is SEMI-NAIVE with the delta atom marked `<fresh>` (see Phase 4.1). Remaining firmware
    pieces: 4.1's CHAIN-side bound-tuple SIP `<demand>`, then 4.4 the trace renderer.
4.3 CHAIN: sub-`<demand>` via the in-graph head index; to quiescence or fuel exhaustion.
    **v0 DONE (2026-07-09, `harneskills/isa/chain.py`, 487 green).** `chain(fact_g, rule_g, goal_pred)`
    demand-drives: `demand_closure` closes the demand set BACKWARD from the goal predicate through the head
    index (a demanded pred pulls in the body predicates of every rule producing it, transitively), minting a
    VISIBLE `<demand>` control node per predicate (the magic set, inspectable — not a hidden agenda); then
    APPLY runs ONLY the relevant rules (those producing a demanded pred) to quiescence. DIFFERENTIALLY GATED
    vs `run_bank` over the FULL bank (`tests/test_isa_chain.py`): CHAIN derives EXACTLY the goal-predicate
    facts the full forward closure derives (complete for the goal), while NEVER applying an irrelevant rule —
    pinned by a bank where the `likes` rule is provably skipped for an `is_a` goal (`alice likes bob` derived
    by `run_bank`, absent under CHAIN), and a transitive goal reproduces `run_bank` exactly. **v0 SCOPE /
    NEXT:** demand is at the PREDICATE grain (restricts WHICH RULES run, not yet which tuples — bound-arg SIP
    is the v1 refinement the GoalSolver already does at tuple grain); positive rules only (inherited from
    APPLY v0); relevant rules run forward to fixpoint. Next: 4.1's `<demand>`/`<fresh>` gadgets (promote the
    predicate-grain demand to the bound-tuple grain + semi-naive delta) and the 4.4 trace renderer.
4.4 **Trace renderer** (gate, not nice-to-have): frames, cursors, demand — all nine modes
    renderable; explanation = journal replay (RECORD).
    Exit gate: firmware == GoalSolver differentially on the ProofWriter positive slice.
    **DONE (2026-07-10, 498 green, `tests/test_isa_{trace,firmware_gate}.py`):**
    - **RECORD (mode 9)** — `apply._record` mints a `<j:rulekey>` justification per firing (`proves -> head`,
      `uses -> each body fact node`) at every APPLY/`chain_sip` EMIT, in the SAME inert substrate shape
      `GoalSolver._justify`/`rewriter` write. Opt-in `provenance=True` (default OFF — keeps the derivation-set
      differentials clean; provenance is INERT, invisible to matching). `uses` recorded in AUTHORED rule order
      so the journal is byte-identical to `run_bank`.
    - **RENDER = journal replay** — since the journal is the standard `proves`/`uses` support and
      `world_model.Graph = AttrGraph`, a firmware derivation explains through the EXISTING `surface.explain`,
      no firmware-specific renderer. Pinned: a `chain_sip` proof tree, and an APPLY derivation explaining
      BYTE-IDENTICALLY to `run_bank(provenance=True)`.
    - **`render_demands`** — the bound magic set (visible `<demand>` nodes) as CNL "what I looked for" lines.
    - **EXIT GATE MET** — `chain_sip` == `GoalSolver` on a randomized ProofWriter-positive slice (transitivity
      + inheritance join + linear + conjunctive rule; 20 graphs × every goal binding pattern, 1000+ checks).
    DEFERRED (not gate-blocking): live rendering of the EPHEMERAL `<frame>`/`<current-atom>` working state (a
    debug affordance); the not-yet-built modes' traces (CHECK "where I looked", SUPPOSE scopes) land with their
    Phase-5 modes. **Phase 4 positive core is COMPLETE through its gate.**

## Phase 5 — FIRMWARE v2: the psychology leaves Python

5.1 CHECK: bounded completion → defeasible `assumed-no` (CWA), per-predicate OWA opt-in;
    "where I looked" journaled and renderable.
    **DONE (2026-07-10, `harneskills/isa/check.py`, `tests/test_isa_check.py`):** `check(fact_g, rule_g,
    goal, open_preds=…)` runs CHAIN (`chain_sip`) and returns ONE of FOUR statuses — POSITIVE / ENTAILED_NEG
    (the negative `pred_not` derivable, a HARD no) / ASSUMED_NO (CWA default, defeasible, §5-safe — nothing
    materialized for it) / UNKNOWN (open concept, gather). `collapse()` = `query.ask_goal`'s yes/no/unknown
    verdict (which COLLAPSES the negative KINDs; CHECK keeps them distinct for metareasoning). `explain_check`
    renders the verdict + "where I looked" from the visible `<demand>` magic set (`render_demands`).
    DIFFERENTIALLY GATED: `collapse(check(...))` == the `GoalSolver`-based verdict over 12 random positive
    banks × every bound goal (500+, mixed closed/open concepts). v1: negative pred = `pred+"_not"`;
    ENTAILED_NEG needs negative-producing rules. The AGGRESSIVE `is_not` completion (`decide.solve`'s
    write-side elimination) is a DISTINCT mechanism, composed in with 5.2/elimination — not this query verdict.
5.2 CHOOSE (PREFER/SELECT): graded α-cut comparison over frames; the planner's `chosen` pick
    becomes a declared deterministic rule.
    **DONE (2026-07-10, `harneskills/isa/choose.py`, `tests/test_isa_choose.py`):** `choose(g, goal,
    alpha=…)` realizes the LOCKED means-selection design (`graded_means_selection_design.md`, mechanism 1b
    RETAINED/RANKED, MONOTONE — which was never actually built). Candidates = option nodes with a graded
    `fit`; α-cut prunes below `alpha`; the winner is the argmax = the candidate NOTHING beats (`beaten` iff an
    eligible one has strictly greater fit — the `satisfied_by … and not … beaten` argmax, driver-computed, no
    `<compare>` tool since fit is a float). MONOTONE (losers retained + marked `beaten`, auditable; winners
    `satisfied_by`); TIES → all win; α-cut and selection compose (α-pruned ≠ beaten). Gated on the design's
    exact fixtures + a 200-seed randomized argmax differential. v0: fit is an INPUT — computing it from a
    rule's graded condition during matching (`_graded_degree` α-cut in the APPLY/CHAIN body) is the companion
    slice; wiring the planner's `chosen` operator pick (`solve._mint_chosen`) as a declared CHOOSE is the
    follow-on.
5.3 SUPPOSE: `<hypothesis>` scopes — pencil writes, CHAIN inside the scope, CHECK predicted
    consequences, confirm→EMIT-to-ink with provenance / refute→DROP_CTRL. No retraction, ever.
    **DONE (2026-07-10, `harneskills/isa/suppose.py`, `tests/test_isa_suppose.py`, 519 green).** The
    pencil/ink split, SAME-GRAPH (not the possible-worlds/`graph.copy()` trap). The non-additive part —
    SCOPE-AWARE matching — landed as a `scope=` param on `apply._fact_relnodes`/`chain._facts_matching`/
    `_fact_exists`, gated behavior-NEUTRAL at `scope=None` (differentially proven, 511→519, all firmware
    gates green). A pencil fact = a CONTROL rel node tagged `apply.SCOPE`, visible only within its scope;
    `chain_sip(scope=…)` reasons in-scope and EMITs in pencil; `suppose(...)` → `SupposeResult`
    (CONFIRMED→ink+`_drop_scope`, REFUTED[contradiction]→drop, INCONCLUSIVE→drop), ink monotone throughout.
    See the "Pick up next" trail above for v0 scope + the `derived_triples`-includes-control caveat.
5.4 Declared strategies replace shape-sniffing: `R is transitive` (walker), `same_as
    propagates through X` (coref-follow). DELETE `_is_same_as_prop`,
    `_is_transitive_closure_rule`, `_linear_recursion_base`.
    **DONE (2026-07-10, 519→522 green, all three sniffers deleted; CHANGELOG has the full trail).**
    - **5.4a walker/transitive (test-only in production → answers-identical).** `goal.py`'s
      `_is_transitive_closure_rule`/`_linear_recursion_base`/`_closure_bases` (rule-shape matchers)
      replaced by `_closure_declarations(ag)`, reading the base map from the SUBSTRATE: `R is
      transitive` → the CANONICAL `R -[rel_property]-> transitive` fact (the same declaration that
      GENERATES the transitivity rule — now double duty), `D -[transitive_closure_of]-> B` for linear
      recursion. `GoalSolver` gains `closures=` (defaults to reading `self.ag`). KEY FINDING:
      `walk_fuel` is NEVER set in production → the walker + these sniffers were test-only, so this is
      pure de-sniffing with zero production change. End-to-end CNL chain pinned in `test_isa_goal_walker.py`.
    - **5.4b coref-follow (production-semantic → behavior-preserving, differentially gated).**
      `_is_same_as_prop` (sniffed `r.key.startswith("same_as.subj.")`) deleted. `Rule` gains a declared
      `coref_prop` role; `universal.same_as_rules` sets it; `GoalSolver` reads `r.coref_prop` (not the
      key) for `_follow_coref` + the subsumed-rule drop. Repairs a lossy path (the declaration
      `same_as_rules(preds)` already made was discarded then re-sniffed). Answer-identical across the
      full suite; pinned `test_coref_following_is_driven_by_the_declared_flag_not_the_rule_key`.
    - **TRACKED RESIDUAL VIOLATION (ratified w/ user 2026-07-10 — option A "tag now"; recorded, not
      papered over).** 5.4b closes the ENGINE-sniffing violation but NOT the deeper `no-python-for-banks`
      one: which predicates propagate coref is still a Python choice (`session.py:CONTENT_PREDS`) and the
      propagation rules are still Python-generated. The bank-authored `same_as propagates through X` CNL
      surface is DEFERRED to Phase 3 (see the Phase 3 tracked note) — it needs the coref rules reified
      first (the parked quote/eval wall), so doing it now would bolt a new authored surface onto
      still-Python machinery with migration + SLM-surface risk. `coref_prop` is forward-compatible: when
      rules reify it becomes a graph attribute, same read site.
5.5 **KB procedures** (`to NAME: step then step` beyond planner ops): named compositions of
    modes, authored in CNL, run as control-token programs. Plan→act→check→replan re-reads as
    ITERATE×CHECK over expected effects (the loop already exists — reuse, don't rebuild).
    New CNL forms → `handoff_slm_surface_track.md` (retrain debt ledger).
    **SLICES 1–2 DONE (2026-07-10, 522→531 green, `harneskills/mode_calls.py`, `tests/test_isa_mode_calls.py`):
    the ENABLING PRIMITIVE — a firmware MODE invoked as a §8 `<call>` calculator.** A reasoning mode is
    a calculator the substrate invokes, exactly like a tool (`decision-agentic-direction` / `decision-
    materialized-tool-calls`): a rule/procedure MATERIALIZES a `<call> --tool--> MODE` node with slots;
    the dumb dispatcher (`dispatch.service_calls`) runs it and folds the result back, consuming the call.
    WHICH mode / WHEN = the calls present (DATA), never the dispatcher (content-blind). Reuses the
    existing `<call>` loop — NOT a new driver ("the loop already exists — reuse"). Lives at `harneskills/`
    level (a bridge like `procedure.py`; inside `isa/` it would close an import cycle through `world_model`).
    - **Slice 1 CHECK** (goal → `<check>` verdict, control token carrying goal + 4-status); 6 differential
      tests vs. direct `check(...)`.
    - **Slice 2 CHOOSE** (goal node + optional α → firmware `choose` over pre-registered candidates,
      marks `satisfied_by`/`beaten`; `choice_results` reads winners); 3 tests incl. a heterogeneous
      CHECK+CHOOSE program. SUPPOSE is NOT a single call (its assumptions/predictions are variable-length
      lists — a scope the CNL surface lays down; forcing fixed slots = a workaround), so it lands in slice 3.
    - **Slice 3a DONE (2026-07-10, 531→534 green): rules emit mode-calls, the EXISTING loop services them,
      the effect FEEDS BACK — no new driver, no authored surface, zero SLM debt.** Ratified framing (user):
      the primitive is rules-emit-mode-calls (loop-inversion / machine-rule-CNL faithful), NOT a Python
      procedure DSL; `to NAME` is later sugar. `run_bank(..., tools=mode_registry(rule_g))` already services
      `<call>`s at fixpoint, so integration = pass the mode registry as tools. The CHECK verdict now also
      emits CONTROL relations (`<check> -[status]-> S`, `-[of]-> subj`) so a forward RULE matches + reacts.
      3 integration tests (positive-materialization feedback; react to a CWA `assumed-no` verdict; CHOOSE
      winner drives a downstream rule). SHARP EDGE found + tracked (`finding-interning-aliases-predicate-
      literals`): a rule carrying a goal PREDICATE as an object literal (`<call> -[pred]-> is`) runs away
      because INTERN aliases the `is` literal to the `is` predicate rel node; fixed by defaulting `pred` to
      the copula (copula checks carry only safe entity literals). Relational-predicate calls + a key-aware
      INTERN fix are deferred to 3b / a Phase-2 engine item.
    - **Slice 3b DONE (2026-07-10, 534→535 green): no new surface + key-aware INTERN fix.** Ratified
      (user): reuse the EXISTING `<call>? SLOT VALUE and … when …` machine-rule grammar (zero new forms,
      zero SLM debt); fix INTERN now; SUPPOSE deferred. `machine.py`'s MINT-intern is now KEY-AWARE — it
      skips a reified DOMAIN-RELATION candidate (graded key == its own name, non-`<…>`), so a value-literal
      `is`/`eats` never aliases the predicate rel node (retires `finding-interning-aliases-predicate-
      literals`). RELATIONAL mode-calls are now sound; the copula-only 3a limitation is retired. Gated hard
      (INTERN is core: reasoning parity, planner, recognition — all green). Test: a CNL-authored rule emits
      a relational `eats` check whose derived fact drives a downstream rule.
    **REMAINING 5.5 SLICES:** (4) plan→act→check→replan expressed as ITERATE×CHECK over `<check>` verdicts
    (compose the existing execution loop with mode-calls, don't rebuild); (3c) SUPPOSE scope authoring in
    CNL (deferred from 3b — variable-length assumptions/predictions).
    Exit gate (DOWNGRADED per the ratified no-equivalence principle — 2026-07-10): engine grep-clean (no
    strategy selection in Python); card-trader + planning + coref + riddles benches produce SENSIBLE,
    SELF-CONSISTENT answers on firmware semantics. **No longer** "every divergence from old exhaustive
    results classified ratified-vs-bug" — old-gen equivalence is not a target; only note firmware behavior
    that is internally wrong or nonsensical. This collapses the phase's biggest risk-tail.

## Phase 6 — DEMOTE the Python solver; docs converge

6.0 **NOW-UNBLOCKED by the no-equivalence ratification (2026-07-10) — pull FORWARD, mostly ✓Sonnet.**
    Retire `rewriter.py` + the `TEMPORARY BRIDGE` dual-write `name` write (grep "TEMPORARY BRIDGE"): they
    only preserved old-gen equivalence. Then sweep the reader flips they blocked — 2.2's
    `nodes_named("<tok>")`→`nodes_with_key`, node-instance `startswith("<")`→`is_control`
    (`forms.py:473/507/548`, `universal.py:90`); 2.3 name demotion; delete `_INERT_NAMES`/`_is_inert`. All
    differentially gate-able against a KEPT GoalSolver (dev oracle) or just "still sensible". Do this BEFORE
    the judgment-heavy firmware work — it shrinks the codebase and removes the equivalence machinery.
6.1 GoalSolver (or its remains) = ACCELERATOR only where profiling justifies; deleted where the firmware
    subsumes it (coverage alone — NOT old-answer equivalence, which is no longer a target).
6.2 Rewrite `architecture.md` as the as-built description of THIS system; `reference.md`
    doc-map refreshed; this plan's finished phases summarized into `CHANGELOG.md`.

## Phase 7 — PERFORMANCE track (separate effort, after correctness — user standing rule)

In leverage order: (a) intern keys/values to ints, CSR adjacency, bitset candidate sets;
(b) Rust (PyO3) inner loop for Machine + store, Python stays the shell; (c) per-rule AOT
codegen = partial evaluation of APPLY (Soufflé-style), differentially gated; (d) two-tier
execution for runtime-edited rules — fresh rules interpret, stable-hot rules compile in
background, version-stamp invalidation on edit. JIT (Cranelift/copy-and-patch before LLVM)
only if profiling demands it.

## Risks

- **Phase 0.1 is a real optimization problem** — do not trade data-drivenness for speed
  (user standing note); the differential harness is proven, use it every step.
- **Semantic divergences** (bounded-defeasible vs old exhaustive) WILL appear from Phase 5 —
  classify every one; no silent deltas.
- **Meta-debugging** — the Phase 4 trace renderer is the mitigation; it gates the phase.
- **SLM surface debt** accumulates from Phases 2/3/5 CNL forms — batch retrains via the ledger.
