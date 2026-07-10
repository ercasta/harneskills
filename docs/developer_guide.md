# Harneskills — System Developer Guide

**Audience:** engineers new to the codebase who need to understand the architecture,
extend it, or debug it. Assumes you have skimmed [`docs/onboarding.md`](onboarding.md)
(reading order + technique glossary) and the top of
[`docs/architecture.md`](architecture.md) (the model in one screen).

> This guide documents the **current one-substrate engine**. If you have read the older
> `README`-era material describing a `KnowledgeBase`, an HTN `Planner`, a `Dispatcher`,
> `DomainModel`, `corpus_reader.py`, or "1500 tests" — that is the **superseded**
> typed-predicate paradigm; those modules no longer exist. See
> [`docs/onboarding.md`](onboarding.md) §0.

---

## 1. What the system does

There is **one graph substrate**, and everything is a node in it: world facts, the rules
that derive new facts, goals, control flow, and the controlled-English source. All
computation is **graph rewriting** — rules match subgraphs and add nodes (or, in a
walled-off control layer, delete them). There is no compile step to a foreign IR, no
separate planner, and no seam where data leaves the graph for other machinery. A large
model is never in the reasoning loop; every conclusion traces, edge by edge, back to the
sentences that produced it through in-graph provenance.

The pipeline for a batch corpus:

```
CNL text ──tokenize (tool)──► token nodes ──run(FORM_RULES)──► canonical fact/rule nodes
         ──canonicalize (tool)──► merged mentions ──run(domain rules)──► derived facts
         ──ask(question)──► CNL answer + why-trace
```

Everything after `tokenize` is rules rewriting the same graph.

---

## 2. Package layout

```
harneskills/     # the engine (~8k lines)
corpus/          # behavior authored AS CNL: the planner, walker, procedures, demos
tests/           # pytest suite (273 tests, ~19s)
bench/           # scale/coverage probes (ProofWriter, WordNet, coverage audit)
scripts/         # SLM fine-tune + eval harness (off-box / Colab)
docs/            # documentation
```

### Engine modules (`harneskills/`)

Grouped by role; **bold** = read first. Everything is re-exported from the package root
(`import harneskills as h`), see `harneskills/__init__.py`.

**Core**
| Module | Responsibility |
|---|---|
| **`rewriter.py`** | The engine. `run()` — the fixpoint loop; matching (homomorphic, seed-from-ground), firing, `<call>` tool servicing. The heart of the system. |
| **`world_model.py`** | The graph substrate: `Graph`, `Node`, bare edges, the lexical name index, `name_count` (document frequency). |
| **`production_rule.py`** | `Rule` / `Pat` / `GradedCondition` — the rule data structures. |
| **`provenance.py`** | In-graph justifications (`proves` / `uses` / `unless`) and the guarded filter that keeps them out of ordinary matching. |

**Authoring (English → graph)**
| Module | Responsibility |
|---|---|
| `authoring.py` | The shared CNL body/condition grammar (`BODY_SPINE_FORMS`); `load_corpus`, `load_facts`, `load_rules`, `expand_rules`, `run_rules`, `stratify`. Largest file. |
| `forms.py` | Surface recognition: `tokenize`, `FORM_RULES`, `canonicalize`, declared verbs/relations/determiners. |
| `machine_rules.py` | The uniform triple-grammar for **control** rules (`H when B`, NAC via `not`, multi-head, `drop`, `<walker>?` tokens). |
| `universal.py` | Universally-quantified NL (`if someone is rough then they are young`) → a rule. |
| `surface.py` | `render_relation`, `narrate`, `explain` — graph back to CNL for humans. |

**Reasoning subsystems** (each maps to a design doc / memory decision)
| Module | Responsibility |
|---|---|
| `decide.py` | Defeasible / closed-world negation, decided on demand per tuple (`completion` + `defeat`, expressed as rules); `solve()`. |
| `retraction.py` | Truth-maintenance cascade as meta-rules; retraction by interposing a `<retracted>` marker. |
| `coref_walk.py` | Coreference resolution as a check-before-commit cursor. |
| `demand.py`, `walker.py` | Demand-driven matching and **walkers** (control tokens carrying fuel for long-range traversal). |
| `query.py` | Question answering (`ask`, `recognize`), existentials. |
| `planning.py`, `procedure.py` | The planner + procedures — authored entirely in `corpus/planning*.cnl`; no rule literals in Python. |
| `rule_graph.py` | Rules represented *as graph nodes* (homoiconic); relation-property + disjoint/constraint schemas → `<contradiction>`. |

**Calculators & external systems (the `<call>` seam)**
| Module | Responsibility |
|---|---|
| `dispatch.py` | The materialized-`<call>` mechanism: `emit_call`, `service_calls`, the `Tool` signature. |
| `external.py` | External-lookup requests as `<call>`s, with freshness/error handling. |
| `asp.py` | clingo / ASP as a scoped calculator (disjunction, exactly-one, optimization). Opt-in `asp` extra. |
| `cpg.py` | Joern Code Property Graph → `S P O` frames extractor slice. |
| `slm.py`, `slm_data.py` | The SLM harness: exact NL→CNL frame-graph reward, and the synthetic data generator. |

**Session / IO / support**
`session.py` (the lazy interactive path), `repl.py`, `interaction.py` (the user as an
oracle), `kb.py` (`RuleBank`), `lint.py` (invariant checks).

---

## 3. The substrate API (`world_model.py`)

One graph, one node population, bare edges. Key methods:

```python
import harneskills as h

g = h.Graph()
paul   = g.add_node("paul")            # returns a uuid; name is a NON-unique label
person = g.add_node("person")
p2     = g.add_node("paul")            # distinct node, same name
assert paul != p2
assert len(g.nodes_named("paul")) == 2

# A relation is an intermediate node on a 2-edge path — edges are untyped.
rid = g.add_relation(paul, "is_a", person)   # paul → [is_a] → person
assert g.name(rid) == "is_a"
assert g.has_edge(paul, rid) and g.has_edge(rid, person)

# Read relations out of a subject:
g.relations_from(paul)                 # -> [(is_a_node_id, person_id), ...]

g.name_count("is_a")                   # document frequency — how many nodes wear this name
g.set_embedding(paul, {"urgency": 0.9})
g.set_confidence(rid, 0.8)
g.gc_disconnected()                    # remove nodes connected to nothing (always safe)
```

**There are no values.** A datum like `0.2` is a node named `"0.2"`; only a *tool* ever
parses that name into a float (§6). Config, entities, literals, relation words, and control
tokens are all the same kind of thing — named node instances.

---

## 4. The rule layer (`production_rule.py`)

A `Rule` is a subgraph-matching-a-subgraph rewrite:

```python
@dataclass
class Rule:
    key: str                       # stable identifier (also used for provenance)
    lhs: list[Pat]                 # the match pattern (a subgraph)
    rhs: list[Pat]                 # nodes/relations to CREATE on fire
    nac: list[Pat] = []            # negative application condition; blocks fire if present
    drop: list[Pat] = []           # CONTROL-LAYER deletions only (linter-enforced)
    probability: float = 1.0       # prior; flows into derived confidence
    meta: bool = False             # META/TMS rule: fires provenance-silent
    # ... graded conditions, embedding propagation (see the graded layer, vision §13)
```

A `Pat(s, p, o)` is a triple-pattern. Slots follow the substrate convention:

| Slot form | Meaning |
|---|---|
| `?x` | **variable** — binds a node; same name in the rule must bind the same node |
| `is_a` (plain literal) | **reuse** a same-named node (match by name) |
| `paul?` / `<forall>?` | **bound literal** — binds the rule's own token / mints a fresh rule-scope node |
| the predicate slot may itself be `?p` | predicates are nodes too, so they can be variables |

Matching is **homomorphic** (distinct pattern keys may co-bind — needed for control tokens
and self-relations) and **unbounded**, kept cheap by **seed-from-ground**: each pattern
seeds from its most selective *ground* anchor (a literal or already-bound variable), found
O(1) via the lexical index. A pattern of only free variables yields nothing and must be
demand-driven. NAC groups sharing a free variable are independent (`not A and not B` =
¬A ∧ ¬B).

### Writing and running a rule directly

```python
import harneskills as h

g = h.Graph()
paul, person = g.add_node("paul"), g.add_node("person")
g.add_relation(paul, "is_a", person)

rule = h.Rule(
    key="mortality",
    lhs=[h.Pat("?x", "is_a", "person")],
    rhs=[h.Pat("?x", "is_a", "mortal")],
)

firings = h.run(g, [rule])             # fixpoint; every enabled match fires
# paul is now is_a mortal, with a <j:mortality> --proves--> that fact
```

`run()` signature (`rewriter.py`):

```python
def run(graph, rules, *, max_steps=200, seeds=None, provenance=True,
        activation=True, semi_naive=True, tools=None) -> list[Firing]:
```

- `provenance=True` materializes justification nodes for each firing (turn off only for
  meta/TMS rules — or set `Rule.meta`).
- `semi_naive=True` joins only against newly derived facts each round (the Datalog lesson).
- `tools=` is the `<call>` registry (§6).
- Re-firing the same `(rule, bindings)` is suppressed, so monotone rules terminate; the
  non-monotone control layer relies on `max_steps` as a real backstop.

You will rarely hand-build `Rule` objects for a domain — you author CNL and let the grammar
expand it (§5). Hand-built rules are for engine machinery and tests.

---

## 5. Authoring a domain in CNL

The preferred path — **no Python domain logic** (a standing invariant, §9). Facts, rules,
questions, and CWA declarations all go in one corpus.

```python
from harneskills.authoring import load_corpus
from harneskills.query import ask
from harneskills import decide

g, rules = load_corpus("""
    ada is a suspect
    bo is a suspect
    cy is a suspect
    bo in library
    ada is alibied

    cleared is closed world               # drives aggressive `is_not` COMPLETION (decide.solve). NB:
                                          # under CWA-default (decision-cwa-default) closed-world is the
                                          # query default; this marker is the reasoning-side opt-in, and
                                          # `X is open world` is the OWA query opt-in.

    ?x is innocent when ?x in library     # a universal → a rule
    ?x is cleared when ?x is innocent
    ?x is cleared when ?x is alibied

    ?x is thief when ?x is a suspect and ?x is not cleared
""")

journal = decide.solve(g, rules)          # monotone deduction + decided negation to fixpoint
ask(g, "who is thief", journal=journal, rules=rules)      # -> ['cy is thief']
ask(g, "why cy is thief", journal=journal, rules=rules)   # -> a walk of the justification nodes
```

Loader entry points (all in `authoring.py`):

| Function | Use |
|---|---|
| `load_corpus(text) -> (Graph, rules)` | Full corpus: facts + rules + CWA, one call. |
| `load_facts(graph, text) -> [str]` | Just facts into an existing graph. |
| `load_rules(text) -> [Rule]` | Just rules (prose or `H when B`). |
| `run_rules(graph, rules)` | Run with graceful degradation — on a negation cycle it drops the NAF rules and reasons with the monotone subset, warning which. |
| `stratify(rules)` | Order rules into strata; raises on a non-stratifiable cycle. |

For pure **control / machinery** rules, `machine_rules.load_machine_rules(text)` parses the
uniform triple-grammar (`H when B`, bare `S P O`, `not` NAC, `drop`, `<token>?`). This is
how the planner, walker, and procedures are authored — see `corpus/*.cnl`.

### Adding a CNL form

CNL forms are **in-graph rewrite rules**, not a Python parser branch. Recognition forms
live in `forms.py` (`FORM_RULES`) and body/condition grammar in `authoring.py`
(`BODY_SPINE_FORMS`, shared by prose and machine rules). To extend the grammar you add a
form rule (LHS = a token-adjacency pattern, RHS = canonical nodes), not a compiler edit.
Declaring vocabulary is *data*: `eat is a relation`, `the is a definite`, etc. (see the
verb-catalog and definiteness handling in `forms.py`).

---

## 6. Tools — calculators on opaque nodes (`dispatch.py`)

A tool is the only way computation leaves graph-rewriting (arithmetic, an ASP solve, a
Joern export, an LLM call). A rule **emits a `<call>` node**; the engine services it at
each fixpoint through a registry and folds the result back in. Rules never read a tool's
internals; tools never rewrite via rules.

```python
Tool = Callable[[Graph, str], set[str]]   # (graph, call_id) -> set of touched/new node names
```

A tool reads its arguments off the call node, mutates the graph directly, and returns the
node names it touched (so the engine re-activates matching there). Example — the fuel
decrement tool from `walker.py`:

```python
def dec_tool(graph, call_id):
    w = call_arg(graph, call_id, TARGET)          # read the 'target' slot off the <call>
    if w is None or not graph.has(w):
        return set()
    edge = _fuel_edge(graph, w)                   # find the walker's single fuel counter
    rel, count = edge
    n = int(graph.name(count))                    # §8: parse the OPAQUE name into an int
    graph.remove_node(rel)
    touched = {w}
    if n - 1 > 0:
        f = _ensure(graph, str(n - 1))
        graph.add_relation(w, FUEL, f)
        touched.add(f)
    return touched
```

Register tools and pass them to `run`:

```python
TOOLS = {"dec": dec_tool, "refuel": refuel_tool}
h.run(g, rules, tools=TOOLS)          # engine calls service_calls at each fixpoint
```

A rule materializes a call with `emit_call(graph, tool_name, {slot: value})`. Note
`service_calls` runs queued calls **sequentially** within a fixpoint round, so K concurrent
increments apply without a race. This is the integration boundary for `asp.py`, `cpg.py`,
`external.py`, and the interactive oracle (`interaction.py`).

---

## 7. Provenance, explanation, and the two layers

**Every firing leaves a justification** (unless the rule is `meta`): a node `<j:KEY>` with
`--proves--> Conclusion` and `--uses--> Premiseᵢ` edges. This is not a side log — it *is*
the graph. `explain` / `narrate` (`surface.py`) traverse these edges to produce the English
`why` trace; `ask(g, "why …")` wraps it. The `proves`/`uses`/`unless` predicates are held
out of ordinary matching by a guarded filter (`provenance.py`), and lifted back in only for
a rule that explicitly opts in (per-rule provenance-awareness — the keystone that lets the
TMS itself be rules).

**Two layers, one graph** (the *one* deliberate seam):

- **Monotone fact layer** — reasoning never deletes. "Truth changes" by adding marker nodes
  (e.g. a `<retracted>` interposed into a fact's path) read through a guarded filter.
- **Non-monotone control layer** — control tokens (`<current>`, `<goal>`, `<walker>`, …)
  and plan scaffolding: freely created and deleted, but **only control edges, only gated by
  a control token**.

Crossing into the control layer is crossing into Turing-completeness; `max_steps` is the
real backstop, used deliberately.

---

## 8. The linter (`lint.py`)

Static checks against the standing invariants — run it on any rule bank you author:

```python
import harneskills as h

bad = h.Rule(key="bad",
             lhs=[h.Pat("?x", "is_a", "person")],
             rhs=[],
             drop=[h.Pat("?x", "is_a", "person")])   # deletes a FACT edge, ungated

[str(s) for s in h.lint_rules([bad])]
# -> ['[ungated-delete] bad: deletes an edge but no <control> token gates the LHS']
```

Findings (`Smell(rule_key, kind, detail)`):

| kind | Meaning |
|---|---|
| `ungated-delete` | a `drop` whose LHS has no `<control>` token — deletion must be control-gated (vision §5) |
| `unbound-drop` | a `drop` references a node the LHS never bound |
| `no-op` | a rule with no RHS, drop, or propagate — it can never change anything |
| `negation-cycle` | the bank is not stratifiable (NAC through a cycle); reuses `stratify` |
| `dead-predicate?` | (opt-in) an LHS predicate no rule produces and not in `base_predicates` |

`lint_graph(graph)` lints rules that live in the substrate as rule-nodes
(`rule_graph.rules_in_graph`).

---

## 9. Design invariants (load-bearing)

These are the standing guardrails from `vision.md` §12. Violating one breaks the property
it protects.

| Invariant | Why | Enforced by |
|---|---|---|
| **Edges stay untyped.** No edge labels, no `Ref` type — a relation is a node. | Uniform substrate: rules and data are the same stuff. | Review; `world_model.py` has no edge-type field |
| **Reasoning rules never delete; only control rules delete, only control edges, only token-gated.** | Confluence / termination / "every fact has a derivation" are all-or-nothing. | `lint.py` `ungated-delete` |
| **Domain logic lives in CNL banks, never in Python engine code.** | The engine is domain-agnostic by construction; every behavior traces to a sentence. | Review; the memory records this as a hard rule |
| **The scheduler stays dumb.** No scoring-as-control, no beam search, no HTN. | Determinism comes from token-passing in the graph, not a clever engine. | Review; creeping intelligence belongs in the graph as rules |
| **Tools never read opaque content with rules; rules never call tool internals.** | The opaque/expanded boundary is absolute — the only seam-free integration point. | Review; `dispatch.py` `Tool` signature |
| **Metareasoning is content-blind.** Effort dials read structural stats (df, fuel, fire counts) + exogenous budget, never *meaning*. | A content-scoring effort dial is the rejected smart planner sneaking back. | Review; `vision.md` §14 |

---

## 10. Testing

```bash
.venv/Scripts/python.exe -m pytest tests/ -q          # 273 tests, ~19s
.venv/Scripts/python.exe -m pytest tests/test_riddles.py -v
```

Some tests need the `asp` extra (`pip install clingo`, already in the venv). Each
`tests/test_*.py` roughly corresponds to one subsystem in §2 and is the **fastest spec** for
that subsystem's intended behavior — read the test before the module. `tests/test_new_core.py`
is the substrate/rule/engine contract; `tests/test_riddles.py` is the best end-to-end
integration example.

`bench/` holds the scale and coverage probes (ProofWriter grammar coverage, WordNet
scaling, the coverage/composition audit) — these validate the substrate at scale rather
than unit behavior.

> **Windows note:** the `Edit` tool has occasionally written files as CRLF. Before
> finishing a change, verify touched files are LF-only (`tr -cd '\r' < file | wc -c` prints
> `0`). The user commits manually — never run `git commit`.

---

## 11. Where to go next

- **The frontier:** [`docs/implementation_plan.md`](implementation_plan.md) — the active
  plan, current phase, and next step (index: [`docs/reference.md`](reference.md)).
- **The direction:** [`docs/vision_agentic.md`](vision_agentic.md) — code reasoning,
  business semantics, SLMs; where `asp.py`, `cpg.py`, and `slm.py` are headed.
- **The philosophy in full:** [`docs/vision.md`](vision.md).
- **Subsystem deep dives:** `docs/walkers_and_locality.md`,
  `docs/depythonization_design.md`, `docs/coref_as_rules_design.md`.
