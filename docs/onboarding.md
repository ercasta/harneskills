# Onboarding — Getting Oriented in Harneskills

**Audience:** a new engineer joining the project. Assumes you know Python and LLM
systems, but *not* the specific techniques the system leans on (CNL, controlled
natural language, defeasible reasoning, coreference resolution, Joern/CPG, small-model
fine-tuning, Datalog/ASP). This guide gives you a reading order, a map of the code, a
one-page mental model, and a glossary that points outward for each technique.

> **Read this first — it will save you a day.** The project was **rebuilt** partway
> through its life. There are two generations of documentation in `docs/`, and the
> older one describes a design that *no longer exists in the code*. This guide tells
> you which is which. If you start from `README.md` or `docs/developer_guide.md` you
> will look for modules (`engine.py`, `planner.py`, `dispatcher.py`,
> `corpus_reader.py`) that were deleted in the rebuild. Don't. See §0.

---

## 0. The one thing to know up front: two generations of docs

The system began as a **typed-predicate KB + planner** (an LLM-as-tool agent harness).
It was then rebuilt around a single idea called the **one-substrate vision**: *there is
one untyped graph, and everything — facts, rules, goals, control flow, even the source
English — is a node in it; all computation is graph rewriting.* The current codebase is
the rebuild.

**The doc set was consolidated on 2026-07-07: `docs/reference.md` is the single index** —
it states which documents are live, the precedence chain between them, and the active plan
(`docs/implementation_plan.md`). Historical records live in `docs/attic/` and are never
authoritative. Start at `reference.md`; anything it doesn't list as live should not be
implemented from.

Quick tell: if a doc mentions `KnowledgeBase`, `corpus_reader.py`, `planner.py`,
`dispatcher.py`, `domain_model.py`, or a RETE alpha-index, it is the old generation (attic).
The current engine core is the ISA machine in `harneskills/isa/` over the label-less
`AttrGraph` substrate; `rewriter.py` is legacy under active deletion (plan Phase 0).

---

## 1. Reading order (half a day)

Do these in order. Skim, don't study — you're building a map, not memorizing.

1. **`docs/architecture.md`** — the system as built, in one screen at the top
   ("The model in one screen"). This is the single most important page. Read the whole
   file; it's the concrete map of every module.
2. **`docs/vision.md`** — the *why* behind the substrate: untyped edges, no seams,
   graph rewriting, the two-layer (monotone facts + non-monotone control) split, tools
   as calculators. Where vision and architecture disagree, vision states intent and
   architecture states current reality.
3. **`docs/vision_agentic.md`** — the *what it's for* (CANONICAL direction, 2026-07-04):
   pointing the substrate at code reasoning, business semantics, and serving small
   language models in agentic coding. Its opening table maps each "independently
   re-derived" idea to the module that already implements it — a great index.
4. **`docs/implementation_plan.md`** — the active plan: current phase, what just landed,
   and the immediate next step. Read this to know where the frontier is *today*
   (index of all live docs: `docs/reference.md`).
5. **`docs/CHANGELOG.md`** — skim the most recent entries for chronology. Don't read it
   all; use it as a reference when you need the history of a specific subsystem.
6. **`docs/discussion/discussion.md`** — a first-principles design conversation that
   independently re-derived the substrate. Optional but illuminating; read it once you
   want the deeper "why this shape and not another."

Then come back here for the code map (§3) and the techniques glossary (§4).

---

## 2. The mental model in one page

Everything below is elaborated in `architecture.md` — this is the compression.

- **One graph, untyped.** A **node** is a uuid + a non-unique `name` label + optional
  sparse embedding + confidence. There are **no values**: the number `0.2` is just a
  node named `"0.2"`; only a tool ever parses that name. An **edge** is a bare directed
  `(from, to)` pair with **no type**. A relation `s R o` is not a typed edge — it's an
  intermediate node: `s → [R] → o` (three nodes, two bare edges).
- **Computation is graph rewriting.** A **rule** has LHS / RHS / NAC / drop, each a list
  of `Pat(s, p, o)` triple-patterns joined by shared variable bindings (i.e. a
  subgraph). Matching is *homomorphic* and *unbounded*, kept cheap by **seed-from-ground**
  (each pattern starts from its most selective already-known anchor, found O(1) via a
  lexical index). Every enabled match fires — there is no clever planner choosing among
  them (a deliberate "stupid planner" commitment).
- **Two layers, one graph.** A **monotone fact layer** (reasoning never deletes; "truth
  changes" only by adding marker nodes read through a guarded filter) and a
  **non-monotone control layer** (tokens, plan scaffolding — freely created and deleted).
  A linter flags any rule that deletes outside the control layer.
- **Tools are calculators on opaque nodes.** A rule emits a `<call>` node; the engine
  services it at each fixpoint through a registry and folds the result back in. Rules
  never call into a tool's internals; tools never rewrite. They couple only through
  nodes. This is how clingo (ASP), Joern (CPG), tokenizers, and an LLM all plug in
  without reopening a seam.
- **Provenance lives in the graph.** Each firing materializes a justification node
  `<j:KEY> --proves--> C`, `--uses--> Pi`. `explain` just walks these edges — there's no
  separate log. This is also the basis of the truth-maintenance / retraction machinery.
- **CNL is surface, not the reasoner.** English sentences are compiled to graph
  structure and reasoning happens on the graph; CNL is rendered back only for humans.
  Nobody runs inference over an English string.

If you internalize those six bullets, the code will read cleanly.

---

## 3. Code map (`harneskills/`)

The engine is ~8k lines of Python. Grouped by role — start with the ones in **bold**.

**Core engine (read these first)**
- **`rewriter.py`** (806 lines) — the heart. Pattern matching, firing, the fixpoint
  `run()` loop, tool servicing. If you understand this file you understand the engine.
- **`world_model.py`** (320) — the graph substrate: nodes, bare edges, the lexical index
  that makes seed-from-ground O(1), `Graph.name_count` (document-frequency).
- **`production_rule.py`** (175) — the `Rule` / `Pat` data structures (LHS/RHS/NAC/drop,
  `rewire`, per-rule `meta` provenance suppression).
- **`provenance.py`** (144) — in-graph justifications; the `proves` / `uses` / `unless`
  predicates and the guarded filter that keeps them out of ordinary matching.

**Authoring: English → graph**
- `authoring.py` (1113) — the shared CNL body/condition grammar (`BODY_SPINE_FORMS`);
  the largest single file, and where most grammar lives.
- `forms.py` (857) — surface forms; tokenization-to-graph recognition rules.
- `machine_rules.py` (134) — the uniform triple-grammar for *control* / machinery rules
  (`H when B`, NAC via `not`, multi-triple heads, `drop`, `<walker>?` control tokens).
- `universal.py` (68) — universally-quantified NL (`if someone is rough then they are
  young`) compiled to a rule.
- `surface.py` (117) — rendering graph back to CNL for humans.

**Reasoning subsystems (each maps to a decision doc)**
- `decide.py` (184) — defeasible / closed-world negation "decided on demand" per tuple
  (completion + defeat, now expressed as rules).
- `retraction.py` (124) — truth-maintenance cascade as meta-rules; retraction by
  "interposition" (splicing a `<retracted>` marker into a fact's path).
- `coref_walk.py` (365) — coreference resolution as a check-before-commit cursor (see §4).
- `demand.py` (87) / `walker.py` (305) — demand-driven matching and **walkers**
  (control tokens that carry fuel to do long-range graph traversal; "think harder" =
  more fuel). See `docs/walkers_and_locality.md`.
- `query.py` (249) — question answering, existentials (`is anyone happy`).
- `planning.py` (569) + `procedure.py` (164) — the planner, now authored entirely in
  CNL (`corpus/planning*.cnl`); `planning.py` holds no rule literals.

**Calculators & external systems (the `<call>` seam)**
- `dispatch.py` (113) / `external.py` (192) — the materialized-`<call>` mechanism and
  the tool registry.
- `asp.py` (118) — **clingo / Answer Set Programming** as a scoped calculator for
  disjunction / exactly-one / optimization (opt-in `asp` extra: `pip install clingo`).
- `cpg.py` (129) — **Joern Code Property Graph** → frames extractor slice (converts a
  CPG into `S P O` facts; no live JVM required for the slice).
- `slm.py` (83) / `slm_data.py` (175) — the small-language-model harness: exact
  frame-graph **reward** for NL→CNL, and the synthetic data generator.

**Session / IO**
- `session.py` (483) — the interactive, *lazy* path (coreference and contradiction are
  pulled by read paths, not run eagerly). `repl.py` (124), `interaction.py` (111),
  `driver.py`, `kb.py`, `lint.py`, `rule_graph.py`.

**Corpora (`corpus/*.cnl`)** — the planner, walker, and demo behavior authored *as
English*, not Python. `icecream.cnl` is the toy domain; `planning*.cnl` is the planner.

**Tests / benches** — `tests/test_*.py` (run: `.venv/Scripts/python.exe -m pytest tests/ -q`,
~19s, ~273 tests). Each `test_*.py` roughly corresponds to one subsystem above and is the
fastest way to see a subsystem's intended behavior by example. `bench/` holds the
coverage/scaling probes (ProofWriter, WordNet, the coverage/composition audit).

---

## 4. Techniques glossary — what to learn and where

Each entry: what it is, why we use it, and a concrete pointer. `docs/learning_resources.md`
already curates a Datalog/ASP/evaluation study path — start there for the logic-programming
family; the entries below add the rest.

### CNL — Controlled Natural Language
A restricted subset of English with a well-defined grammar that maps deterministically to
a formal representation. We author *all* domain behavior in CNL and compile it to graph
structure; the goal is authorable-in-English, auditable, no procedural code.
- **In this repo:** `docs/kb_authoring_guide.md`, `docs/logic_fragment.md` (the accepted
  fragment), any `corpus/*.cnl` file; the recognizer is `authoring.py` + `forms.py`.
- **Outside:** Attempto Controlled English (ACE) and its RACE reasoner —
  attempto.ifi.uzh.ch — is the closest published relative and is discussed directly in
  `vision_agentic.md`. Read the ACE "in a nutshell" primer.

### Frames / reified role-triples
A "frame" is an opaque concept id with **named role edges** (e.g. an `eat` event with
roles `agent`, `patient`). We represent them as ordinary `S P O` triples with a
predicate-name plus an `is_a` type — reified role-triples without a separate type system.
- **In this repo:** `tests/test_code_frames.py`, `docs/vision_agentic.md` §5.
- **Outside:** Minsky's "frames," and FrameNet (framenet.icsi.berkeley.edu) for the
  linguistic version.

### Defeasibility / non-monotonic reasoning / closed-world negation
Classical logic is *monotone*: adding facts never retracts a conclusion. Real reasoning
is **defeasible** — "birds fly" but not penguins; a later fact can defeat an earlier
conclusion. We implement negation-as-failure "decided on demand" per tuple, with a
justification-based truth maintenance system (JTMS) that cascades retractions when a
defeating fact arrives.
- **In this repo:** `docs/consistency_design.md`, `decide.py`, `retraction.py`,
  `tests/test_decide.py`, `tests/test_retract_rules.py`; the decision writeups
  `decision_forcing_a_decision` / `decision_depythonization` in the memory index.
- **Outside:** the classic *Truth Maintenance Systems* literature (Doyle 1979; de Kleer's
  ATMS). For defeasible logic proper, Nute's "Defeasible Logic." For the closed-world /
  negation-as-failure and stratification background, the Datalog references in
  `docs/learning_resources.md`.

### ASP — Answer Set Programming (clingo)
A logic-programming paradigm for problems needing disjunction, "exactly one," and
optimization — things a bottom-up forward-chainer can't do directly. We use **clingo** as
a *scoped calculator* invoked through the `<call>` seam, never as the main engine.
- **In this repo:** `asp.py`, `tests/test_asp_calc.py`; install with the `asp` extra.
- **Outside:** the Potassco guide (potassco.org) and "Answer Set Solving in Practice"
  (Gebser et al.). `docs/learning_resources.md` §on ASP.

### Coreference resolution
Deciding when two mentions ("the dog," "it," "Rex") refer to the same entity. In an
untyped substrate this is load-bearing: merge too eagerly and you fuse distinct things;
too little and you can't reason across sentences. Our approach is *check-before-commit*
(link only if it doesn't create a sort clash) and demand-driven, not eager.
- **In this repo:** `docs/coref_as_rules_design.md` (history: `docs/attic/coreference_design.md`),
  `coref_walk.py`, `tests/test_coref_walk.py`. Note the quantification-vs-coreference
  decision: a bare repeat is a *distinct witness*, not a contradiction.
- **Outside:** Jurafsky & Martin, *Speech and Language Processing* (3rd ed., free online),
  the "Coreference Resolution" chapter — the standard on-ramp.

### Joern / CPG — Code Property Graph
Joern (joern.io) parses source code into a **Code Property Graph** unifying AST, control
flow, and data flow into one queryable graph — the standard substrate for static security
analysis. We fold a CPG into our own `S P O` facts so the same engine can reason over code.
- **In this repo:** `cpg.py`, `tests/test_cpg_adapter.py`, `bench/coverage_audit.py`,
  `docs/vision_agentic.md` §4.
- **Outside:** the original CPG paper — Yamaguchi et al., "Modeling and Discovering
  Vulnerabilities with Code Property Graphs" (IEEE S&P 2014) — and the Joern docs.

### Small-language-model fine-tuning (QLoRA)
We fine-tune a ~0.5B model for the *one narrow job* of turning intent into CNL (the only
place a model sits in the loop — at the boundary, never in the reasoning). QLoRA =
low-rank adapters on a 4-bit-quantized base, cheap enough to train on a single Colab GPU.
The novel part here is the **exact reward**: `slm.grade` scores a generated CNL by
comparing its *frame graph* to the target, catching "confidently wrong" outputs a string
match would pass.
- **In this repo:** `slm.py` (reward), `slm_data.py` (synthetic data gen, disjoint eval
  vocab to test copy-through), `scripts/finetune_nl2cnl.py` (the Colab QLoRA script),
  `scripts/eval_nl2cnl.py`.
- **Outside:** the LoRA paper (Hu et al. 2021) and QLoRA paper (Dettmers et al. 2023);
  the Hugging Face PEFT docs for the hands-on version.

### Datalog / Horn clauses / forward chaining
The theoretical backbone: our monotone fact layer is essentially a Datalog-style
bottom-up (forward-chaining) fixpoint over Horn rules, with stratified negation. Knowing
this vocabulary makes `rewriter.py`'s `run()` loop obvious.
- **In this repo:** `docs/spec/05-active-semantic-inference*.md`.
- **Outside:** `docs/learning_resources.md` is a curated study path — the "fast path"
  trio (Møller & Schwartzbach's *Static Program Analysis* notes, the Soufflé tutorial,
  and the Green et al. survey) gets you operational in a weekend.

### Walkers & locality / demand-driven matching
Our answer to "how do you do long-range reasoning without matching the whole graph every
step." Matching seeds from ground anchors; rules with no anchor are pulled on demand; and
genuinely long-range traversal is done by **walkers** — control tokens carrying a fuel
budget. More fuel = "think harder."
- **In this repo:** `docs/walkers_and_locality.md`, `walker.py`, `demand.py`,
  `tests/test_walkers.py`.
- **Outside:** this one is homegrown; the nearest relatives are magic-sets / demand
  transformation in Datalog (covered in the learning_resources survey) and agenda-based
  forward chaining.

---

## 5. Get hands-on (an afternoon)

1. Set up the venv and run the suite:
   `.venv/Scripts/python.exe -m pytest tests/ -q` (system Python has no pytest). Some
   tests need the `asp` extra: `pip install clingo` (already in the venv).
2. Open `tests/test_new_core.py` and `tests/test_machine_rules.py` and read them as
   *worked examples* of the engine's contract.
3. Load a corpus and ask it something — start from `corpus/icecream.cnl` and the
   interactive `session.py` / `repl.py` path.
4. Pick one subsystem you'll likely touch, read its decision doc + its `test_*.py`, then
   read the module. The test file is always the fastest spec.
5. Read `docs/implementation_plan.md` again — now it will make sense — to see the current
   frontier and pick a first task.

> **Windows note:** the `Edit` tool has occasionally written files as CRLF. Before
> finishing a change, verify touched files are LF-only
> (`tr -cd '\r' < file | wc -c` should print `0`). The user commits manually — never run
> `git commit`.

---

## 6. Where the project is pointed (so you know *why*)

The canonical direction (2026-07-04, `docs/vision_agentic.md`) is to aim the substrate at
**reasoning over code and business semantics, in service of small language models doing
agentic coding**. The bet: a deterministic, auditable reasoning substrate lets a small
model punch far above its weight — the model only translates intent to CNL at the
boundary; all reasoning is graph rewriting that can be explained edge-by-edge. The recent
**coverage/composition audit** (`bench/coverage_audit.py`) measured the central risk
(does a small set of general rules compose to catch novel cases, or must you enumerate
patterns forever?) and found composition works: 100% recall on encoded mechanisms
including novel manifestations, with the residual misses being *absent-premise* classes
(taint, concurrency, arithmetic) rather than a pattern-enumeration treadmill.

That's the story you're joining. Welcome aboard.
