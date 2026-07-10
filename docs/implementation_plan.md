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

**Suite: 59 passed, 0 failed** (post repo-split, 2026-07-11, `python -m pytest -q`).

The harness is currently in a **tracking** posture relative to UGM:

1. **Wait for UGM Phase 5.5 slice 4** (plan→act→check→replan as ITERATE×CHECK) to land in `ugm`.
   That is the next UGM milestone that changes harness-visible behavior. Once it lands, the
   planning benches here become the **Phase 5 exit gate** (H-2 below).

2. **While waiting — SLM surface debt sweep (H-1):** the CNL grammar has changed across UGM
   Phases 2/3/5 (key-aware INTERN fix, relational mode-call forms, scope authoring). Record
   those form changes in `handoff_slm_surface_track.md` and schedule the batch retrain.

3. **Phase 6.0 in UGM (rewriter retirement) unblocks** the name-demotion sweep; some CNL
   authoring forms may need updating once `nodes_named` reads flip to `nodes_with_key`. Track
   any surface regressions here.

---

## H-0 — Repo split cleanup (2026-07-11)

- [x] All harness modules live in `harneskills/` (planning, session, interaction, kb, lint,
  slm, slm_data, procedure, deontic, repl, scenarios, cpg, mode_calls, planning_kb)
- [x] TUI in `harneskills_tui/`
- [x] Tests that depend on harness modules in `tests/`
- [x] `harneskills/__init__.py` re-exports from `ugm` for backward compat + harness symbols
- [x] `pyproject.toml` depends on `universal-graph-machine`
- [ ] **Verify benches pass** (`bench/cpg_scaling.py`, `bench/joern_corpus.py`) after split
- [ ] **Examples verified** — `examples/` use `import harneskills as h`; confirm they run on
  the split packages
- [ ] `rewriter.py` in `ugm/ugm/cnl/` is a dev oracle only — tracked for Phase-6 retirement
  in UGM; no harness code should import it directly

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
