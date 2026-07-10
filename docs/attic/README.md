# Attic — historical records, kept honestly

Nothing in this directory is authoritative. These files are preserved as *records* of how the
design got here (raw conversations, superseded design generations, finished-arc handoffs).
Do not implement from them; do not "fix" them. The live documentation set is indexed by
`docs/reference.md`, and the active plan is `docs/implementation_plan.md`.

Contents:

- `spec/` — the original numbered specification (superseded en bloc by `docs/vision.md`).
- `discussion/` — raw design conversations that `vision_agentic.md` later synthesized.
- `isa_origin_conversation.md` — the raw conversation that originated the graph low-level
  machine idea (synthesized into `graph low level machine/rule-isa-design.md`).
- `coreference_design.md` — first-generation coref design (impl superseded by
  `coref_as_rules_design.md`; provenance framing by `depythonization_design.md`).
- `handoff_redesign.md` — the rebuild arc's resume document (arc completed; history lives in
  `docs/CHANGELOG.md`).
- `handoff_attrgraph_rehost.md` — the re-host arc's handoff (its remaining items were absorbed
  into `docs/implementation_plan.md` Phase 0; its dated history is duplicated in the CHANGELOG).

Deleted outright (recoverable from git history, removed because they actively misled —
presented dead machinery as current): `cnl_spec.md`, `harness_arch_spec.md`,
`corpus_authoring_guide.md`, `plan_graph_reasoning_refactor.md`, `icecream_demo.md`,
`nonconformance_audit.md`, `file_index.md`, `handoff_firmware_migration.md` (absorbed into
`implementation_plan.md`).
