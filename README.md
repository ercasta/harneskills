# HarneSkills

**An iterative LLM harness for knowledge-intensive agent workflows.**

HarneSkills is an application layer built on top of the
[Universal Graph Machine (UGM)](https://github.com/ercasta/Universal-Graph-Machine). It pairs UGM's
symbolic graph reasoning with a fine-tuned Small Language Model (SLM) and a
Textual-based TUI, providing an interactive authoring environment and an agentic
runtime for tasks that require structured deliberation — planning, checking, choosing
— over a persistent knowledge base.

---

## What it does

HarneSkills puts an SLM at the boundary of a symbolic reasoner:

```
User / tool output
        │
        ▼
   ┌─────────┐    fuzzy intent → CNL     ┌──────────────┐
   │   SLM   │ ─────────────────────────▶│  UGM engine  │
   │ (small) │ ◀────────────── answers ──│  (symbolic)  │
   └─────────┘    reading tool output    └──────────────┘
```

The model does exactly two things — both irreducibly open-world:

1. **Fuzzy intent → CNL.** Turning "make checkout handle partial refunds better" into a
   well-formed CNL statement. A closed grammar cannot parse arbitrary human phrasing;
   that is the model's job by construction.
2. **Reading arbitrary tool output** — error messages, stack traces, API responses,
   legacy data. Unconstrained text understanding, handed to the model.

Everything else — parsing the CNL, unifying against the KB, defeasible arbitration,
provenance tracking, planning, and checking — runs on the UGM substrate. The SLM is
not asked to reason; it is asked to translate and read.

> *HarneSkills is the symbolic exoskeleton that lets a small model reason far above its
> own weight by carrying the part it cannot do.*

---

## Architecture

```
harneskills_tui/       Textual TUI — screens, widgets, modals, profiles
harneskills/
  session.py           Session: running knowledge base + recognition loop
  interaction.py       Oracle protocol, disambiguation, clarification
  driver.py            Phase driver (recognize → derive → plan → act → check)
  planning.py          Plan/act/check/replan loop (ITERATE × CHECK)
  planning_kb.py       CNL KB for planning operators and goals
  procedure.py         Named KB procedures (authored in CNL)
  deontic.py           Deontic rules (forbidden/permitted/obligatory)
  kb.py                RuleBank / KnowledgeBase containers
  lint.py              KB linting (stratification, smell detection)
  slm.py               SLM interface (inference, fine-tuning hooks)
  slm_data.py          Training data utilities
  scenarios.py         High-level scenario runner
  cpg.py               Code Property Graph adapter (reasoning over code)
  mode_calls.py        CHECK / CHOOSE mode wiring to the tool dispatcher
  repl.py              Interactive REPL
```

---

## Key concepts

### Session

A `Session` wraps a live knowledge graph, a rule bank, and the UGM engine. It
ingests CNL input line by line, recognizes facts and rules, and maintains a
continuously updated world model. The session exposes `ask`, `recognize`, and
`explain` for querying and narrating the current state.

```python
from harneskills import Session

session = Session()
session.ingest("alice wants vanilla")
session.ingest("vanilla is in_stock")
session.ingest("alice gets vanilla when alice wants vanilla and vanilla is in_stock")
answer = session.ask("alice gets vanilla")
```

### Planning

The planner expresses the plan → act → check → replan cycle as UGM's `ITERATE × CHECK`
composition. A plan is a sequence of operators authored as CNL rules; execution runs
each operator, checks the outcome, and replans on failure. The control flow is KB
content — there is no bespoke Python orchestration.

```
plan:   goal_state derived from KB goals
act:    execute the selected operator (may call external tools via <call>)
check:  CHECK the postcondition
replan: if the check fails, re-derive the plan
```

### Knowledge authoring

Domain knowledge lives entirely in `.cnl` files — plain text, no Python required:

```
# facts
alice is a customer
coffee is a product
coffee is in_stock

# rules  
alice can order coffee when alice is a customer and coffee is in_stock

# deontic
ordering two coffees is discouraged when alice is budget_conscious
```

The `lint` module validates stratification and detects smells before loading.

### TUI

The Textual-based TUI provides:
- Live knowledge graph inspection
- Session management (load/save/query)
- Rule and fact authoring
- Plan visualization
- SLM interaction panel

---

## The boundary discipline

HarneSkills enforces a strict boundary between symbolic and neural components:

- **Rules never call tools.** A rule emits a `<call>` control token; the engine's
  dispatcher routes it to the registered handler at fixpoint. The rule does not know
  the tool exists.
- **Tools never rewrite.** A tool handler reads its argument slots, emits result nodes,
  and returns. It does not touch the rule engine.
- **The SLM sees only CNL.** The SLM produces CNL statements; the engine handles
  everything else. The model is never in the rule-evaluation loop.

This is the §12.5 hard rule from the UGM design, lifted to the application level.

---

## Installation

```bash
# Install UGM first (the substrate)
pip install ugm

# Install HarneSkills
pip install harneskills

# Or in development (both repos checked out side by side)
pip install -e path/to/ugm
pip install -e path/to/harneskills
```

Requires Python ≥ 3.8.

Optional dependencies:
- `clingo` — ASP calculator for disjunction and model enumeration (`pip install "harneskills[asp]"`)

---

## Repository structure

```
harneskills/           Python package (core harness)
harneskills_tui/       Python package (Textual TUI)
corpus/                Example CNL knowledge bases
bench/                 Benchmarks (ProofWriter coverage, scaling)
testdata/              Test fixtures
docs/
  implementation_plan.md   Active development plan
  kb_authoring_guide.md    How to write knowledge bases
  planning_design.md       Plan/act/check/replan design
  vision_agentic.md        Agentic application arc
  developer_guide.md       Contributing and dev setup
```

---

## Relationship to UGM

HarneSkills depends on UGM:

```
harneskills → ugm.cnl (CNL authoring, rule loading, explanation)
           → ugm      (ISA engine, CHECK/CHOOSE/SUPPOSE, graph substrate)
```

UGM is self-contained; it has no dependency on HarneSkills. If you only need the
symbolic graph engine (without TUI, SLM, or planning), use UGM directly.

---

## Status

Active development. The ISA firmware (UGM Phases 4–5) is complete through Phase 5.4.
The plan → act → check → replan loop (Phase 5.5 slice 4) and the Phase 5 exit gate
(benchmark validation) are the current work. See `docs/implementation_plan.md`.
