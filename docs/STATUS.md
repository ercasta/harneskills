# What in `docs/` is still true

> **Written 2026-08-13, when the harness was rebuilt onto UGM's `restart` engine.**

Every other document in this folder predates that rebuild and describes one of
**two** engines that no longer exist. They are kept as a record of how the
decisions were reached; none of them is a guide to the code in this repo today.
Read `../README.md` first, and the docstrings in `harneskills/` after that —
those are the live documentation.

## The two deletions, in order

1. **~2026-07.** UGM replaced production rules + open CNL with `microfunctions`:
   backward chaining over return types, a closed 8-verb block CNL, planning and
   norms as first-class engine features. This deleted the execution model the
   original `harneskills/` package was built on.
2. **~2026-08.** UGM deleted *that* too, in the `restart` branch. The current
   engine is four primitives with a single grammar — `rule` / `fact` / `say` —
   where a rule is a relation instance like any other and adding a connective
   adds rows rather than branches. See `../../ugm/docs/rules-design.md`.

The harness was rebuilt from scratch against (2). Nothing was ported.

## Document by document

| document | status |
|---|---|
| `migration_to_microfunctions.md` | **superseded.** It plans a migration onto engine (1), which was deleted before the plan was executed. Its §3a scope ruling — *HarneSkills is a UI/UX layer over UGM, nothing else* — is the one part still in force, and the rebuild follows it. |
| `feedback_microfunctions.md`, `feedback_ugm_market_desk.md` | **closed.** Feedback filed against engine (1). |
| `ugm_surface_regressions.md` | **closed as obsolete.** Both issues concern a CNL surface that no longer exists. |
| `implementation_plan.md`, `planning_design.md`, `operator_goal_cnl.md`, `kb_authoring_guide.md`, `architecture.md`, `developer_guide.md`, `user_guide.md`, `onboarding.md` | **historical.** All describe the original production-rule engine and the harness that sat on it: planning banks, deontic arbitration, CNL authoring, the CPG stack. That code is in git history. |
| `handoff_slm_surface_track.md`, `slm_from_scratch_vs_finetune.md` | **historical, and one idea worth keeping.** The SLM track's premise — *we own the parser, so a candidate translation can be graded exactly by comparing what it parses to* — survives the engine change intact. What is gone is the grammar it graded against and the training data written in it (`testdata/`, deleted). Rebuilding it against the `.ugm` grammar is a real option; it is not built. |
| `vision_agentic.md`, `system_critique.md`, `huma_review_notes.md` | **historical.** Argument and critique, useful as reasoning, not as description. |
| `CHANGELOG.md` | **historical.** Stops before the rebuild. |
| `attic/` | already an attic. |

## What replaced them

There is no successor design document, deliberately. The engine's design is
argued at length in `../../ugm/docs/rules-design.md`; this repo is a UI over it,
and a UI whose architecture needs 4,000 words has stopped being one. What the
harness owes a reader instead:

- `../README.md` — what it is, how to run it, the one idea worth knowing
- `harneskills/view.py` — why the layers are what they are, and the one
  invariant (a projection never concludes)
- `harneskills/runner.py` — why the loader is kept, and why authoring does not
  think
- `corpus/*.ugm` — three worked examples, each commented as an argument

## Standing warning

⚠ UGM is under active redesign and its shape moves between sessions. During this
rebuild alone, grades left `Entry`, `@` left the surface, and `Loader.say` lost
an argument — with the working tree dirty throughout. When an import or an
attribute disappears, read `../../ugm/docs/HANDOFF.md` before assuming a bug
here.
