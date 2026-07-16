# Implementation Plan — HarneSkills

> **Status: THE ACTIVE PLAN (2026-07-11, post repo-split).** This plan covers the harness layer:
> the planning CNL rule banks, SLM fine-tuning, session management, TUI, KB authoring UX, and the
> full-stack benches that validate the complete harneskills + ugm system.
>
> HarneSkills depends on `universal-graph-machine` (PyPI) / `ugm` (import). Engine work, firmware
> patterns, and CNL surface live in that repo. Work here is either: (a) authoring domain logic as
> CNL rule banks, (b) tracking and retiring SLM surface debt, or (c) building the application layer
> (session, TUI, repl, interaction) on top of the firmware the engine exposes.
>
> Standing rules: domain logic ONLY in banks (never in Python); no commits by the assistant;
> correctness before raw performance.

## NEXT STEP (pick this up FIRST)

> **STATUS 2026-07-12 (post UGM carve-out rebuild, this session).** The old "tracking posture"
> below was STALE: while it was written, UGM advanced past the split — it **retired**
> `demand.py` / `coref_walk.py` / `asp.py` / `cnl/walker.py` and **deleted** `decide.py` /
> `solve.py` / `goal.py` / `cnl/rewriter.py`, and it **shipped a Session layer** (`ugm/intake.py`
> §8: `ingest` / `converse` / `Outcome` / `Event`, plus `focus.py` / `rule_control.py`). The
> harness imported all the dead modules and **could not import at all** (0 tests collectable).

**Suite now: 24 passed, 38 failed** (`python -m pytest -q`, ~55s). Was 0-collectable before the
carve-out rebuild. The rebuild is in two layers; **layer 1 is done, layer 2 is the active work.**

> **CLEANUP 2026-07-16 (namespace de-duplication, this session).** Ran the shared `../ugm/.venv`
> (has both `ugm` and `harneskills` editable). Confirmed the harness source is genuine harness code
> that imports `ugm.*` directly — the leftover from the old embedded reasoner was a *namespace shim*,
> not duplicated logic. Done this pass (no behavioural change; suite still 24/38, no new failures):
> - **`harneskills/__init__.py` SLIMMED** — dropped `from ugm import *` and the ~40-line alias block
>   that mirrored UGM's whole namespace under `harneskills.*` (`harneskills.authoring`, `.world_model`,
>   `.query`, `.isa`, `AXIOM`, `run_rules`, the `ugm.external` re-exports, …). It now exports **only
>   the 45 harness-owned symbols**. The on-top-of-ugm boundary is explicit.
> - **Consumers repointed to `ugm.*`** — 2 TUI files, 6 tests, and 2 harness-only benches that tests
>   import (`bench/cpg_scaling.py`, `bench/joern_corpus.py`). e.g. `from harneskills.query import ask`
>   → `from ugm.cnl.query import ask`; `h.Graph` → `ugm.Graph`. Harness symbols (`h.solve`,
>   `h.seed_goal`, …) stay on `import harneskills as h`.
> - **`corpus/walker.cnl` deleted** — the only unreferenced corpus file. The other 15 (byte-identical
>   to `../ugm/corpus/` but all loaded at runtime by the harness) stay LOCAL by decision: the harness
>   owns its corpus; matching ugm today is coincidental.
> - **Bench not deduped** — the 3 diverged files (`coverage_audit`, `proofwriter_coverage`,
>   `proofwriter_nl`) left as-is; harneskills copy is canonical.
> - **Env gap noted:** `textual` is NOT installed in `../ugm/.venv`, so `harneskills_tui` can't import
>   there yet; TUI files were byte-compiled instead. Install `textual==8.2.5` before TUI work.

### Layer 1 — structural carve-out rebuild (DONE this session)
- [x] `harneskills/__init__.py` — dropped retired module imports/aliases (`decide`, `coref_walk`,
  `asp`, `demand`, `walker`, `rewriter`, `goal`, `solve`). **Superseded by the 2026-07-16 slim
  (above): it no longer re-exports UGM via `from ugm import *`; consumers import `ugm.*` directly.**
- [x] **`harneskills/session.py` REBUILT on the UGM Session layer** — `Session` is now a THIN
  stateful wrapper over `ugm.ingest`: it holds the KB + accumulated rules + oracle and translates
  an `Outcome` → `LineResult`. The ~350 lines of hand-rolled lazy-coref / contradiction detection
  (on the retired `demand`/`coref_walk`) are GONE. Coref is UGM's declared `same_name_coref_rules`;
  the human ask is UGM's mid-chain `ask_user` bridged to the `Oracle`. The reasoning bank the
  wrapper passes to `ingest` mirrors `load_corpus`'s bundle (`expand_rules + expand_loose +
  same_name_coref_rules + _coref_propagation`), recomputed per turn.
- [x] **Name-demotion reader fix** — a reified relation now carries NO name (`graph.name(r) == ''`);
  its predicate is `graph.predicate(r)`. Fixed `session._content_relations` and added
  `cpg._relation_exists` (predicate-aware) to replace the retired `rewriter._relation_exists`;
  repointed the CPG tests/benches off `rewriter`.
- [x] **`run_rules(..., isa=True)` API drift** — the `isa=` flag is gone (everything is ISA now);
  removed from `planning.py` / `cpg.py` / `driver.py`.

### Layer 2 — domain-bank rebuild (ACTIVE — the remaining ~38 failures)
The harness's DOMAIN Python + CNL banks predate two UGM changes and must catch up:

1. **Planning stack is non-functional (H-3, biggest).** `load_planning_kb(cards_kb.cnl)` produces an
   **empty graph** — the operator/state/goal CNL surface (`planning_kb.py`) no longer matches UGM's
   current grammar, so `solve` runs on nothing and returns a **spurious "done"** (goal vacuously
   satisfied). This sinks `test_scenarios` / `test_deontic` / `test_cards_*` (~23 tests). Rebuild the
   planning-KB CNL forms against the current surface FIRST; the read helpers are the second half.
2. **Name-demotion broke predicate reads pervasively (H-3).** Every `graph.name(r) == "<pred>"` in the
   harness Python (`planning.py`, `scenarios.py`, `procedure.py`, `deontic.py`, `harneskills_tui/`,
   `examples/`, `bench/`) now reads `''` and must become `graph.predicate(r) == "<pred>"`. Mechanical
   but pervasive (~30 sites). Do AFTER the loader is fixed (else you can't tell a read bug from a
   loader bug). Entity reads (`graph.name(o)` for the object) stay.
3. **SLM surface debt (H-1).** UGM's intake path DROPPED determiner / multiword-NP surface
   normalization (`the eagle is a bird` → no fact) and `every X is a Y` no longer derives (returns
   `no`). The SLM `CONSTRUCTS` (`multiword_def`, `universal`) train on surface UGM no longer parses.
   Record in `handoff_slm_surface_track.md`; decide with the user whether to (a) update the SLM
   constructs to the current surface, or (b) restore the normalization in UGM. ~9 tests.
4. **CPG recognizer + live-joern (H-6).** `test_cpg_scaling`/`_graphson` recognizer drift + the
   live-Joern test (mark it `slow`). ~6 tests.

**These are CLASSIFY-not-force per the 2026-07-10 ratification** (bench answers need not match the old
generation; a *nonsensical* answer is a bug, a *different-but-sensible* one is ratified). Several are
UGM-SURFACE questions (determiners, universals) — decide with the user whether the fix lands here or in
`ugm`.

---

## H-0 — Repo split cleanup (2026-07-11) + carve-out rebuild (2026-07-12)

- [x] All harness modules live in `harneskills/` (planning, session, interaction, kb, lint,
  slm, slm_data, procedure, deontic, repl, scenarios, cpg, mode_calls, planning_kb)
- [x] TUI in `harneskills_tui/`; tests in `tests/`; `pyproject.toml` depends on `universal-graph-machine`
- [x] `harneskills/__init__.py` — REBUILT (dead modules removed) then SLIMMED 2026-07-16 to export
  only harness-owned symbols; UGM namespace mirroring removed, consumers repointed to `ugm.*`
- [x] `rewriter.py` is fully RETIRED in UGM; no harness code imports it (replaced `_relation_exists`
  with `cpg._relation_exists`)
- [ ] **Verify benches** (`bench/cpg_scaling.py`, `bench/joern_corpus.py`) — import-fixed off `rewriter`;
  recognizer behavior still drifts (Layer-2 item 4)
- [ ] **Examples verified** — `examples/` still contain the pre-name-demotion `graph.name(r) == pred`
  read pattern (Layer-2 item 2); confirm they run after the sweep

---

## H-1 — SLM surface debt

The SLM is fine-tuned on the CNL grammar. Every time UGM changes the CNL surface (new forms,
renamed predicates, new control tokens) the SLM accumulates retrain debt.

**Debt ledger: `docs/handoff_slm_surface_track.md`** (create if absent; one entry per grammar change).

Known open debt (from UGM Phases 2–5, 2026-07-09/10):
- Relational mode-call forms (`<call>? SLOT VALUE and ...`) — new in 5.5 slices 3a/3b
- SUPPOSE scope authoring forms (5.5 slice 3c, not yet landed in UGM)
- Key-aware INTERN behavior change (5.5 slice 3b) — surface-transparent but changes which
  literals the engine interns; verify SLM-generated CNL still parses cleanly

**Gate:** before any SLM retrain, confirm the grammar change is stable in UGM (no pending
rework). Batch retrains, never per-change.

---

## H-2 — Phase 5 exit gate (full-stack benches)

This is the LARGE validation milestone: once UGM Phase 5.5 slice 4 lands, run the planning
benches here to confirm the full harness + UGM firmware stack produces sensible answers.

**Benches to run:**
- `bench/` — card-trader planning scenarios, coref resolution, riddles
- `tests/test_isa_solve.py`, `tests/test_isa_solve_cards.py` — solve-layer tests that use
  `harneskills.planning` rule banks

**Exit criterion (DOWNGRADED per 2026-07-10 ratification):** firmware is sensible and
self-consistent on the benches. NOT "matches old exhaustive rewriter outputs" — old-gen
equivalence is not a target. Note any behavior that is *internally wrong or nonsensical*;
classify as ratified or bug; never silently accept a nonsensical answer.

Companion: wire `solve._mint_chosen` (in `ugm/solve.py`) as a declared CHOOSE, driven by the
planning rule banks here. ~✓Sonnet once the UGM interface is stable.

---

## H-3 — Planning rule bank evolution

The planning vocabulary (`PLANNING_RULES`, `EXECUTION_RULES`, `TEARDOWN_RULES`, `SOLVE_RULES`,
`DETECT_DIVERGENCE`, `REQUEST_RULES`) lives in `harneskills/planning.py` as CNL banks.

As UGM firmware advances these banks should evolve:

- **`chosen` as a declared CHOOSE** — `solve.py` currently picks `chosen` via Python
  (`_mint_chosen`). Once UGM exposes CHOOSE as a `<call>` tool, this should be a declared bank
  rule, not a Python picker. (Companion to UGM 5.2.)

- **plan->act->check->replan loop** — once UGM slice 4 lands (ITERATE*CHECK), the execution loop
  in `solve.py` should compose with mode-calls rather than calling Python helpers. Track the
  interface here; the bank may need new `<call>` forms.

- **Procedures** (`harneskills/procedure.py`) — named compositions of modes, authored in CNL.
  The `to NAME: step then step` surface is the intended authoring form once UGM 5.5 is complete.

**Rule:** all planning strategy choices stay in the banks. No new Python logic for domain
decisions. If a strategy requires a calculator (tie-break, cost comparison, coref resolution),
it is a `<call>` to a registered tool, not a Python conditional.

---

## H-4 — Session & interaction layer

`harneskills/session.py`, `harneskills/interaction.py`, `harneskills/repl.py`.

- **REBUILT 2026-07-12 on the UGM Session layer (§8).** `Session` is now a thin wrapper over
  `ugm.ingest` / `converse`; it no longer owns reasoning. The bespoke lazy-coref / detection is gone
  (retired `demand`/`coref_walk`). `submit` → `ingest` → `Outcome` → `LineResult`; `contradictions()`
  runs the relation-property constraint rules then reads `<contradiction>` markers; `explain()` reads
  UGM's in-graph support. The `Oracle` now bridges to UGM's mid-chain `ask_user(subj, rel, obj)` (an
  open-premise yes/no/unknown), NOT coref disambiguation (which is UGM declared rules now).
  `interaction.py` still provides the oracles + `ask_user_handler` (`CLARIFY_DEFAULT_KIND` survives).
  NEXT: consider exposing `converse` (non-blocking generator) for the TUI's live event stream.

- **Model routing** (from 2026-07-10 session-handoff): the harness routes between Sonnet and
  Opus based on the judgment requirements of the current task. This policy lives here, not in UGM.
  Document the routing table in `docs/model_routing.md`.

- **`CONTENT_PREDS` (tracked violation)** — `session.py:CONTENT_PREDS` is a Python choice about
  which predicates propagate coref. The vision-faithful fix (`same_as propagates through X` bank
  declaration) is tracked in UGM Phase 3 (needs coref rules reified). Until then this is a KNOWN,
  LOGGED deviation. Do not paper over it with more Python logic.

- **`session.py` rule-source recognition** — runs on `run_bank` (no rewriter); confirmed clean
  post-split.

---

## H-5 — KB authoring UX (REPL, TUI, lint)

`harneskills/kb.py`, `harneskills/lint.py`, `harneskills/repl.py`, `harneskills_tui/`.

- **Lint** (`Smell`, `lint_rules`, `lint_graph`) — stratification check at bank load is in UGM
  (`authoring.lint_stratifiable`). Harness lint focuses on domain-level smells (deprecated
  predicates, orphaned rules, violated KB conventions).

- **TUI** — verify it starts correctly against the split packages before first commit to new repo.

- **REPL** — `python -m harneskills.repl examples/sample_kb.cnl` should work unchanged.
  Verify after split.

---

## H-6 — CPG / code intelligence layer

`harneskills/cpg.py`, `bench/cpg_scaling.py`, `bench/joern_corpus.py`.

- `test_joern_corpus.py` requires a live Joern server; exclude from default CI run. Tag it
  `@pytest.mark.slow` and add a `--slow` flag to pytest configuration.

- `bench/cpg_scaling.py` and `bench/joern_corpus.py` are harness-only (moved from monorepo
  during the split).

---

## H-7 — GitHub setup

1. Rename `ercasta/harneskills` -> `ercasta/harneskills_old`, make private
2. Create `ercasta/universal-graph-machine` repo; push `ugm/` as first commit
3. Create `ercasta/harneskills` repo; push `harneskills_new/` as first commit
4. Pin `universal-graph-machine` version in `harneskills/pyproject.toml` once UGM has a
   stable release tag

---

## Risks

- **SLM retrain timing** — grammar is still moving (UGM 5.5 not complete). Retrain too early
  and incur debt again immediately. Batch at the H-2 exit gate.
- **`CONTENT_PREDS` drift** — as the KB grows, the Python list of coref-propagating predicates
  will diverge from intent. The fix is UGM Phase 3; until then, audit at every major KB session.
- **Harness bench divergence** — the 2026-07-10 ratification means bench answers may differ from
  the old exhaustive rewriter. Classify any new divergence explicitly (ratified vs bug) when
  running H-2.
- **Joern corpus test fragility** — `test_joern_corpus.py` requires a live Joern server; it will
  always be environment-dependent. Keep it behind a `slow` marker; never let it block CI.
