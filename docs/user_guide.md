# HarneSkills — User Guide

**Audience:** Users running the TUI to perform real tasks using a knowledge base.

---

## 1. Starting the App

```bash
harneskills
```

A splash screen appears briefly, then the main CLI screen loads.

### Screen layout

```
┌──────────────────────────────────────────────────────┐
│                                                      │
│  [Log pane — scrollable output]                      │
│                                                      │
│  Step 1: tool.take_order  (entity: alice)            │
│    Taking order from alice.                          │
│  Step 2: tool.check_stock  (entity: alice)           │
│    Checking stock for chocolate.                     │
│  ...                                                 │
│                                                      │
│  [Suggestions — appears when typing]                 │
│                                                      │
├──────────────────────────────────────────────────────┤
│ > _                                                  │
├──────────────────────────────────────────────────────┤
│ [Status bar]                 Ctrl+S=Submit  Ctrl+Q=Quit │
└──────────────────────────────────────────────────────┘
```

- **Log pane** (top): session output, step narration, errors. Scrollable with mouse or arrow keys.
- **Input bar** (lower): type commands here. Tab autocompletes. Up/Down cycles history.
- **Status bar** (bottom): shows current state (ready / running / step-paused) and key hints.

---

## 2. Key Bindings

| Key | Action |
|---|---|
| `Ctrl+S` | Submit input |
| `Ctrl+Q` | Quit |
| `Ctrl+T` | Toggle multiline input mode |
| `Ctrl+V` | Cycle verbosity (0 → 1 → 2) |
| `Ctrl+L` | Focus log pane (scroll with arrow keys) |
| `Tab` | Autocomplete command or slot name |
| `Up / Down` | Command history |
| `Escape` | Return focus to input bar |

---

## 3. The Basic Workflow

Every session follows the same four steps:

```
1. /kb <path>          Load a knowledge base
2. /entity + /suppose  Declare entities (if the domain uses multiple entities)
3. /seed               Set initial world state
4. /run                Let the planner work
```

---

## 4. Loading a Knowledge Base

```
/kb path/to/corpus.cnl
/kb path/to/kb_module.py
```

- `.cnl` files are compiled directly from CNL sentences.
- `.py` modules must export a `build_kb()` function.

The KB is compiled at `/run` time (not immediately on `/kb`), so you can set it up before entering other parameters.

```
/config
```

Shows the current configuration including the loaded KB path, goal, seeds, and entities.

---

## 5. Declaring Entities

For multi-entity domains (e.g., multiple customers, documents, tasks), declare each entity before running.

### `/entity <label>`

Creates a named entity scope:

```
/entity alice
/entity bob
```

### `/seed @label slot=value`

Seeds initial state into that entity's scope:

```
/seed @alice order_needed=True
/seed @alice order_flavor=chocolate
/seed @bob order_needed=True
/seed @bob order_flavor=vanilla
```

### `/suppose ?var is_a TYPE [with slot value ...]`

A more compact alternative — declares an entity and seeds it in one command:

```
/suppose ?cust is_a customer with order_needed True order_flavor chocolate
```

Multiple `/suppose` commands add multiple entities. They are applied at `/run` time.

### `/unseed`

Remove a previously seeded slot:

```
/unseed order_needed            # session scope
/unseed @alice order_needed     # entity scope
```

---

## 6. Setting a Goal

If the KB declares a goal (`goal requires all_complete to be true`), no explicit goal is needed — the engine reads it from the KB.

For ad-hoc goals, use `/goal`:

```
/goal slot=value [slot2=value2 ...]
```

Examples:

```
/goal turkey_ready_to_serve=True
/goal all_complete=True
/goal web_page_ready=True
```

Values are auto-parsed: `True`/`False` → bool, digits → int/float, anything else → string.

---

## 7. Seeding Initial State

`/seed` sets session-level domain model slots — the initial world state the planner starts from:

```
/seed turkey_frozen=True
/seed kitchen_available=True
/seed page_topic="My Blog"
```

Session seeds apply to all entity scopes unless prefixed with `@label`.

---

## 8. Running the Planner

```
/run [goal text]
```

Starts the planning loop. The planner selects actions, invokes tools, and updates the world state until the goal is satisfied or `max_steps` is exhausted.

```
/run                                # use current goal from /goal or KB
/run turkey_ready_to_serve=True     # set goal inline and start
```

To stop a running session:

```
/stop
```

### What you see

During a run, each step is logged:

```
Step 1: tool.take_order  [entity: alice]
  Taking order from alice.
Step 2: tool.check_stock  [entity: alice]
  Checking stock for chocolate.
...
Goal reached in 6 steps.
```

Narration text (the human-readable line under each step) comes from `narrate.TOOL` templates in the corpus. If no template is defined, the raw tool ID and slot values are shown.

---

## 9. Step Mode

Step mode pauses the planner after each action, waiting for you to press Enter before continuing. Useful for debugging or demonstration.

```
/step          # toggle step mode on/off
```

While paused you can:
- `/dm` — inspect current world state
- `/explain` — understand why the step was chosen
- Press Enter (or `/run`) — advance one step

---

## 10. Verbosity

Controls how much detail is shown per step.

```
/verbose 0     # steps and narration only (default)
/verbose 1     # + slot values read and written
/verbose 2     # + residuals and evidence trace
```

Cycle with `Ctrl+V`.

At verbosity 1 you see which slots changed:

```
Step 3: tool.prepare_scoop  [entity: alice]
  Preparing chocolate for alice.
  ← preparation_needed: True, stock_checked: True
  → serving_needed: True
```

At verbosity 2 you see why the planner selected this step over alternatives.

---

## 11. Inspecting State

### `/dm`

Dumps the full domain model — every slot in every scope:

```
> /dm
session:
  (empty)
entity:alice:
  order_needed: False
  order_flavor: chocolate
  preparation_needed: True
  stock_checked: True
  serving_needed: True
  is_a.ordering_customer: True
```

### `/explain`

Explains the last step selection:

```
> /explain
Chose tool.prepare_scoop for alice.
  Preconditions satisfied: preparation_needed, stock_checked
  Postconditions: serving_needed
  Score: urgency=0.60 (waiting_customer weight 1.0 × dim 0.6)
  No NAC blocks.
  Alternative considered: tool.serve_customer — blocked, serving_needed not yet True
```

The explanation draws on `explains` and `reason` sentences in the corpus.

---

## 12. Setting Step Limit

```
/steps 50
```

Default is 20. Increase for complex domains with many entities or long procedures.

---

## 13. The Slot Explorer

Type `?` followed by a prefix to autocomplete domain model or KB slot names:

```
> ?order
  order_needed
  order_flavor
```

Press Tab to complete; press Enter to inspect the current value of that slot.

---

## 14. Profiles

Save and reload full configurations (KB path, goal, seeds, entities, verbosity):

```
/save my_profile           # save current config
/profile my_profile        # load it later
/profiles                  # list all saved profiles
/delete my_profile         # remove one
```

Profiles are stored in `~/.harneskills/profiles.toml`.

---

## 15. Session Logs

Every session is automatically logged to `~/.harneskills/sessions/<YYYYMMDD_HHMMSS>/session.log`.

```
/logs              # list recent session logs
/log               # view the most recent log
/log 3             # view the 3rd most recent log
```

Logs include timestamps relative to session start. To convert to HTML:

```bash
session-to-html ~/.harneskills/sessions/20260623_120000/session.log > session.html
```

---

## 16. Clearing the Screen

```
/clear
```

Clears the log pane. Does not affect the session state.

---

## 17. Full Walkthrough: Ice Cream Shop

This walkthrough uses the ice cream demo (`corpus/demos/ice_cream.py`).

### Setup

```
/kb corpus/demos/ice_cream.py
```

Declare three customers:

```
/suppose ?cust is_a customer with order_needed True order_flavor chocolate
/suppose ?cust is_a customer with order_needed True order_flavor vanilla
/suppose ?cust is_a customer with order_needed True order_flavor strawberry
```

The KB declares the goal (`all customer must have payment_received`), so no `/goal` is needed.

### Run

```
/run
```

The planner processes all three customers concurrently, picking the highest-urgency one at each step:

```
Step 1: tool.take_order  [entity: cust_1]
  Taking order from cust_1.
Step 2: tool.take_order  [entity: cust_2]
  Taking order from cust_2.
Step 3: tool.check_stock  [entity: cust_1]
  Checking stock for chocolate.
...
Step 9: tool.suggest_alternative  [entity: cust_3]
  No strawberry available — suggesting an alternative.
...
Step 14: tool.serve_express  [entity: cust_2]
  Express service for cust_2 — served and paid in one step!
...
Goal reached in 18 steps.
```

Things to notice:
- **No explicit ordering** — the planner decides who gets served next based on urgency.
- **Rush handling emerges** — if a customer's urgency grows to "very urgent" mid-session, the derive rule fires and they become a `rush_customer`. The `serve_express` tool takes over and the `serve_customer` NAC blocks the standard path.
- **Stock-out recovery** — `cust_3` tries to order strawberry (out of stock), `check_stock` fires, then `suggest_alternative` runs, then preparation continues for the alternative flavour.

### Inspect a step

Enable step mode and check what happened:

```
/step
/run
```

After Step 1, press nothing yet:

```
> /explain
Chose tool.take_order for cust_1.
  Preconditions: order_needed (True in cust_1 scope)
  Postconditions: preparation_needed
  Score: urgency=1.00 (waiting_customer scores 1.0, weight 2.0)
  No competing entity scored higher.
```

Press Enter to advance.

### Try different scenarios

After a run, adjust and re-run:

```
/stop
/unseed @cust_2 order_flavor
/seed @cust_2 order_flavor=chocolate
/run
```

Or add a fourth customer:

```
/entity cust_4
/seed @cust_4 order_needed=True
/seed @cust_4 order_flavor=vanilla
/steps 30
/run
```

### Save the config for later

```
/save icecream_3cust
```

Next session:

```
/profile icecream_3cust
/run
```

---

## 18. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| "Impasse" reached before goal | A required slot was never set, or a precondition is unsatisfiable | `/dm` to inspect state; check tool preconditions against initial seeds |
| "No applicable actions" on first step | Goal already satisfied, or no entity has matching preconditions | Check `/dm` and `/config`; verify entity seeds match corpus `requires` slots |
| Narration shows raw tool IDs instead of text | The corpus has no `narrate.TOOL` templates | Add `narrate.TOOL_ID is "..."` sentences to the corpus |
| Step count exhausted | Domain needs more steps than `max_steps` | `/steps 50` |
| KB fails to load | Syntax error in CNL | Check corpus for malformed sentences; the error message names the offending line |
| Entity slots not seeded | `/suppose` syntax error | Use exactly `?var is_a TYPE with slot value` format; values must be unquoted |
