# HarneSkills — KB Authoring Guide

**Audience:** Domain authors who write CNL corpora. No Python required.

---

## 1. The Authoring Model

Everything in HarneSkills is authored in a **Controlled Natural Language (CNL)**. You write short English sentences; the system compiles them into a knowledge base (KB) that drives planning, execution, and narration.

**Core principle:** one sentence = one KB rule. There is no hidden inference. Every behaviour the planner exhibits traces back to exactly one sentence you wrote.

A CNL file (`.cnl`) contains two kinds of content:

- **KB sentences** — general knowledge, authored once, loaded for every session.
- **Problem sentences** (Form 7) — instance-specific initial state, embedded in a problem file or seeded via the TUI.

The file extension is `.cnl` for both. Comments start with `#`.

---

## 2. Sentence Forms

### Form 1 — Relation triple (hard fact)

```
subject  relation  object [, object …] [and object] [.]
```

This is the workhorse. One sentence produces one production rule. The relation is the connective tissue that the planner traverses.

**Available relations:**

| Phrase in corpus | Canonical name | Planner role |
|---|---|---|
| `requires` | `requires` | Hard precondition — action blocked until this slot is True |
| `causes` | `causes` | Postcondition — written True when the action succeeds |
| `has part` / `has parts` | `has_part` | HTN decomposition / structural composition |
| `precedes` | `precedes` | Ordering constraint between steps |
| `is a` / `is an` | `is_a` | Type membership / variant selection |
| `produces` | `produces` | Skill → artifact link (triggers recursive expansion) |
| `uses tool` | `uses_tool` | Binds a step to a registered tool id |
| `resolves` | `resolves` | This action resolves a named residual |
| `calls` | `calls` | Call-graph dependency |
| `depends on` | `depends_on` | Soft dependency |
| `annotates` | `annotates` | Metadata |

Multi-object lists are a single AND-decomposition (all objects required together):

```
cook_turkey has parts thaw, preheat, season, roast, rest
```

**Example:**

```
tool.take_order requires order_needed
tool.take_order causes preparation_needed
```

---

### Form 2 — Qualitative fact (embedding dimension)

```
subject is [not] [very | somewhat | slightly] <adjective>
```

Writes a preference signal onto a concept. The planner uses these signals when scoring alternative actions at an OR-node.

**Available adjectives:** `risky`, `safe`, `reversible`, `invasive`, `localized`, `conservative`, `complex`, `simple`, `detailed`, `fast`, `slow`, `expensive`, `cheap`, `urgent`.

```
roast_turkey is risky
patch is not reversible
serve_express is fast
write_footer is simple
html_generator is not risky
```

Modifiers scale the signal:

| Modifier | Weight |
|---|---|
| `very` | 1.0 |
| (none) | 0.7 |
| `somewhat` | 0.4 |
| `slightly` | 0.2 |
| `not` | −0.7 |

---

### Form 3 — Variables and opaque data

**Variables (`?x`)** create parametric rules that hold for any entity:

```
tool.take_order requires order_needed for ?cust
```

The `?cust` variable is grounded to a concrete entity scope when the planner dispatches. See §3 (Entity Scopes) for the full pattern.

**Opaque literals** (`"..."`) are values passed to a tool without inspection:

```
run_tests requires "pytest -q"
connect_db requires "postgresql://localhost/prod"
```

Opaque literals are never expanded as concepts and never matched as preconditions by the planner. They are carried in `template_params["data_literals"]` for the tool.

---

### Form 4 — Negative application condition (NAC)

```
subject applies unless condition present [.]
```

Blocks the rule when `condition` is present (True) in the domain model. NACs prevent redundant re-execution.

```
preheat_oven applies unless oven_at_temperature present
write_header applies unless header_written present
tool.serve_customer applies unless is_a.rush_customer present
```

The last example shows how to NAC on an entity IS-A fact — the condition uses the `is_a.TYPE` notation to match the derived type fact in the domain model.

NACs are **monotone** — they add a blocking condition; they never remove an existing rule.

---

### Form 5 — Hedged relation (soft default)

```
subject [hedge] relation object [.]
```

Like Form 1 but attaches a probability weight `< 1.0`. The planner treats optional parts (weight < 1) as candidates rather than requirements.

```
web_page usually has nav_bar
web_page sometimes has sidebar
section rarely has analytics
```

**Hedge → weight table:**

| Hedge | Weight |
|---|---|
| `always` | 1.0 (same as Form 1) |
| `usually` / `typically` | 0.80 |
| `often` | 0.65 |
| `sometimes` | 0.40 |
| `rarely` | 0.20 |
| `never` | 0.0 |

---

## 3. Entity Scopes and Multi-Entity Domains

For domains where multiple entities (customers, documents, tasks) are processed concurrently, CNL provides entity-scoped forms.

### Form 12 — Entity-scoped precondition

Append `for ?var` to a `requires` clause:

```
tool.take_order requires order_needed for ?cust
tool.check_stock requires preparation_needed for ?cust
tool.serve_customer requires serving_needed for ?cust
```

This tells the planner: *fire this action for the entity `?cust` that currently satisfies the precondition*. The planner grounds `?cust` to the entity scope with the highest urgency score.

### Form 11 — Derive rule

```
?var is a TYPE derives when ?var is a OTHER_TYPE and ?var is [very] ADJECTIVE
```

Derive rules create new IS-A facts at runtime when the stated conditions hold:

```
?cust is a rush_customer derives when ?cust is a customer and ?cust is very urgent
```

When an entity's urgency embedding reaches `very` (≥ 0.8), the engine derives `is_a.rush_customer` for that scope. Derive rules fire via `_system1_expand` after each step.

### Form 15 — Universal quantification

```
all TYPE must have SLOT
```

Asserts that every entity of TYPE must eventually have SLOT set to True. This feeds the `all_complete` protocol:

```
all customer must have payment_received
```

The engine aggregates these per-entity checks into a single `all_complete` fact that the goal condition can test.

### Form 14 — Suppose (entity declaration)

Used via the TUI `/suppose` command or programmatically:

```
/suppose ?cust is_a customer with order_needed True
```

This seeds a new entity scope with initial slot values before the run starts.

### `precondition_value` — entity type gate

A special annotation on tool rules that gates dispatch on the entity's current IS-A state:

```
tool.serve_customer precondition_value is_a.scoop_prepared
tool.serve_express precondition_value is_a.rush_customer
tool.serve_express precondition_value is_a.scoop_prepared
```

Multiple `precondition_value` lines are AND'd — all must hold. This allows fine-grained action selection without writing Python.

---

## 4. Goal and Objective Forms

### Form 20 — Goal declaration

```
goal requires SLOT to be true
```

Declares what the engine is trying to achieve. Typically used once per corpus:

```
goal requires all_complete to be true
```

### Form 21 — Objective weight

```
DIMENSION scoring weight N.N
```

Sets the weight of a soft dimension in the objective function. Higher weight → more influence on action selection:

```
urgency scoring weight 2.0
```

### Form 19 — Scoring rule

```
?var is a TYPE scores DIMENSION VALUE
```

Contributes a numeric score to an entity's soft dimension based on its IS-A type:

```
?cust is a waiting_customer scores urgency 1.0
?cust is a ordering_customer scores urgency 0.5
?cust is a scoop_prepared    scores urgency 0.3
```

The planner picks the entity scope with the highest aggregate `urgency` score as the next target. This is how priority emerges from CNL rules, with no code.

### Domain dynamics

Two special slots control per-tick urgency growth (tunable per domain):

```
urgency.per_tick is 0.2
urgency.max is 1.0
```

---

## 5. Documentation Forms

These forms do not affect planning; they enrich explanation and narration output.

### Form 25 — Step explanation and slot reason

```
explains TOOL_ID as "Human-readable description of what this tool does."
reason SLOT as "Human-readable explanation of why this slot is needed."
```

```
explains take_order as "Takes the customer's order and queues them for preparation."
reason order_needed as "The customer has not placed an order yet."
```

`/explain` in the TUI surfaces these strings when describing why the last step was selected.

### Form 27 — Narration template

```
narrate.TOOL_ID is "Template string with {slot} placeholders."
```

```
narrate.take_order is "Taking order from {entity}."
narrate.prepare_scoop is "Preparing {order_flavor} for {entity}."
```

Templates are rendered by `run_narrated` after each step. Placeholders are filled from the dispatcher's outbound slot bindings. This is how the engine produces human-readable step summaries with zero hardcoded print statements.

---

## 6. Naming Conventions

These are not enforced by the parser but are load-bearing for readability and convention:

| Concept type | Convention | Example |
|---|---|---|
| Tools / actions | `tool.` prefix | `tool.take_order`, `tool.prepare_scoop` |
| Abstract steps | `step.` prefix | `step.locate`, `step.patch` |
| State slots (boolean) | `noun_verb` or `noun_adjective` | `order_needed`, `payment_received`, `stock_checked` |
| Entity types (IS-A) | plain noun | `customer`, `rush_customer`, `waiting_customer` |
| Goal concepts | plain noun describing the terminal state | `all_complete` |
| Variables | `?` prefix, lowercase | `?cust`, `?x`, `?doc` |

Shared names across sentences are the connective tissue. The concept `preparation_needed` in `tool.take_order causes preparation_needed` and in `tool.check_stock requires preparation_needed for ?cust` is the same node in the concept graph — that's what links the two tools in sequence.

---

## 7. Complete Example — Ice Cream Shop

The full corpus for the ice cream demo (`corpus/icecream.cnl`) illustrates every feature:

```cnl
# Narration templates (Form 27)
narrate.take_order is "Taking order from {entity}."
narrate.check_stock is "Checking stock for {order_flavor}."
narrate.prepare_scoop is "Preparing {order_flavor} for {entity}."
narrate.suggest_alternative is "No {original_flavor} available — suggesting an alternative."
narrate.serve_customer is "Serving {entity} their ice cream."
narrate.process_payment is "Payment received from {entity}. Enjoy!"
narrate.serve_express is "Express service for {entity} — served and paid in one step!"

# Tool rules (Form 12: entity-scoped preconditions)
tool.take_order requires order_needed for ?cust
tool.take_order causes preparation_needed
tool.take_order precondition_value is_a.waiting_customer

tool.check_stock requires preparation_needed for ?cust
tool.check_stock causes stock_checked
tool.check_stock precondition_value is_a.ordering_customer

tool.prepare_scoop requires preparation_needed for ?cust
tool.prepare_scoop requires stock_checked for ?cust
tool.prepare_scoop causes serving_needed
tool.prepare_scoop precondition_value is_a.ordering_customer
tool.prepare_scoop precondition_value stock_available

tool.suggest_alternative requires stock_checked for ?cust
tool.suggest_alternative causes stock_available
tool.suggest_alternative precondition_value is_a.ordering_customer

tool.serve_customer requires serving_needed for ?cust
tool.serve_customer causes payment_needed
tool.serve_customer precondition_value is_a.scoop_prepared
tool.serve_customer applies unless is_a.rush_customer present

tool.process_payment requires payment_needed for ?cust
tool.process_payment causes payment_received
tool.process_payment precondition_value is_a.served_customer

tool.serve_express requires serving_needed for ?cust
tool.serve_express causes payment_received
tool.serve_express precondition_value is_a.scoop_prepared
tool.serve_express precondition_value is_a.rush_customer

# Derive rule (Form 11): rush_customer emerges from high urgency
?cust is a rush_customer derives when ?cust is a customer and ?cust is very urgent

# Universal quantification (Form 15): all customers must pay
all customer must have payment_received

# Scoring rules (Form 19): urgency priority by service stage
?cust is a waiting_customer scores urgency 1.0
?cust is a ordering_customer scores urgency 0.5
?cust is a scoop_prepared    scores urgency 0.3

# Goal and objective (Forms 20-21)
goal requires all_complete to be true
urgency scoring weight 2.0

# Domain dynamics
urgency.per_tick is 0.2
urgency.max is 1.0

# Slot reasons (Form 25)
reason order_needed as "The customer has not placed an order yet."
reason preparation_needed as "An order must be taken before preparation can begin."

# Step explanations (Form 25)
explains take_order as "Takes the customer's order and queues them for preparation."
explains check_stock as "Checks whether the requested flavour is in stock."
explains prepare_scoop as "Scoops the requested flavour into a cup or cone."
explains serve_customer as "Serves the prepared scoop to the customer via the standard queue."
explains serve_express as "Serves a waiting customer immediately via the express lane."
explains suggest_alternative as "Suggests an available alternative when the requested flavour is out of stock."
explains process_payment as "Processes payment and marks the customer order as complete."
```

### What this corpus does

- Three customers arrive concurrently. Each is an entity scope with `order_needed = True`.
- The planner selects which customer to serve next based on **urgency score** — waiting customers (score 1.0) before customers mid-order (0.5).
- As time passes (`urgency.per_tick`), urgency grows. When it hits `very urgent` (≥ 0.8), the derive rule fires and the customer becomes a `rush_customer`.
- Rush customers bypass the standard `serve_customer` tool (which is NAC'd for them) and go directly to `serve_express`.
- When all customers have `payment_received`, the `all_complete` protocol fires the goal.

All of this — priority, rush handling, narration — is authored entirely in the `.cnl` file. The Python demo file provides only tool function implementations and the shop inventory state.

---

## 8. Common Patterns

### Procedure (ordered steps)

```
cook_turkey has parts thaw, preheat, season, roast, rest
thaw precedes preheat
preheat precedes season
season precedes roast
roast precedes rest

thaw requires turkey_frozen
thaw causes turkey_thawed
preheat causes oven_ready
season requires turkey_thawed
season causes turkey_seasoned
roast requires oven_ready
roast requires turkey_seasoned
roast causes turkey_cooked
rest requires turkey_cooked
rest causes turkey_ready
```

### Tool binding (real external tool)

```
tool.run_tests requires source_file
tool.run_tests causes test_report
tool.run_tests uses tool pytest_runner
```

### Gradable variants (same goal, different decompositions)

```
simple_web_page has parts header, body
simple_web_page is simple

complex_web_page has parts header, nav_bar, hero, body, sidebar, footer, analytics
complex_web_page is complex
complex_web_page is detailed

web_page is a simple_web_page
web_page is a complex_web_page
```

When the goal says "create a complex web page", the planner selects `complex_web_page` based on the embedding signal `{complex: 1.0}` matching the `is complex` dimension.

### NAC guard (idempotent step)

```
tool.init_db applies unless db_initialized present
tool.init_db causes db_initialized
```

Without the NAC, the planner would re-initialize the DB on every run. With it, the step is skipped if already done.

---

## 9. Quick Reference: All Sentence Forms

| Form | Template | Purpose |
|---|---|---|
| 1 | `S relation O [, O …]` | Hard fact / rule |
| 2 | `S is [not] [very] ADJ` | Qualitative preference signal |
| 3 | `?x relation ?y` / `S requires "literal"` | Parametric rule / opaque data |
| 4 | `S applies unless COND present` | Negative application condition |
| 5 | `S [hedge] relation O` | Soft/probabilistic fact |
| 11 | `?x is a T derives when ?x is a T2 and ?x is ADJ` | Runtime derivation rule |
| 12 | `tool.T requires SLOT for ?x` | Entity-scoped precondition |
| 15 | `all TYPE must have SLOT` | Universal quantification |
| 19 | `?x is a TYPE scores DIM VALUE` | Scoring rule (priority signal) |
| 20 | `goal requires SLOT to be true` | Goal declaration |
| 21 | `DIM scoring weight N.N` | Objective dimension weight |
| 25 | `explains TOOL as "…"` / `reason SLOT as "…"` | Documentation |
| 27 | `narrate.TOOL is "template {slot}"` | Step narration template |

---

## 10. `compile_corpus` API

```python
from harneskills.corpus_reader import compile_corpus
from pathlib import Path

# From a string
kb, stats = compile_corpus("tool.step_a requires x\ntool.step_a causes y\n")

# From a file
kb, stats = compile_corpus(Path("corpus/my_domain.cnl"))

# With options
kb, stats = compile_corpus(src, min_support=2, smoothing=0.1)
```

`stats` is an `ExtractionReport` with fields `rules`, `triples`, `embeddings`, `hedged`, `nacs`, `derives`, `scoring`, `narration`.

`min_support=2` requires a rule to appear at least twice before being added (noise filter).  
`smoothing=0.1` adds Laplace pseudo-counts to prevent zero probabilities.
