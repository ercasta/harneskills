# Architecture

## Layers

```text
../loopingrules/   world.py    entities, components, and the queries rules ask
                   loop.py     call every rule, in order, until nothing changes
                   engine.py   ONE thread that runs the loop; any number of channels
                   save.py     the world on disk (JSONL)
                   circuits.py, help.py, share.py, chart.py, ...  optional helpers

harneskills/       __main__.py wiring: argv -> Engine + channels + domains
                   repl.py     Terminal channel (stdin in, prose out) + autocorrect
                   serve.py    Listener/Connection channels (WebSocket, JSON)
                   ws.py       the WebSocket codec under serve.py
                   client.py   a small program that speaks to a served engine
                   config.py   which domains to install; where state/server files live
                   examples/   worked domains: fs, automations, context, market
```

HarneSkills owns everything that was never the engine's to know: doors and configuration. **A domain is one callable, `install(loop)`**, that registers rules and spawns what they read. The harness ships none.

## Anatomy of a turn

You type `show file`. The terminal spawns one entity carrying `Said(user, "show file")` and runs the loop.

| tick | rule | what changed |
|---|---|---|
| 1 | `hear` | spawns `ParseRequest`, the occasion |
| 1 | `propose_list` | recognises the line, spawns a candidate: `Proposal` + `ListWanted` on one entity |
| 1 | `arbitrate_parse` | one candidate, no rival: detaches `Proposal`, destroys occasion and `Said` |
| 1 | `list_dir` | destroys the goal, calls `ls`, spawns an entity per entry, moves `Focus`, spawns `Listed` |
| 1 | `reply_listing` | destroys `Listed`, spawns `Reply` entities |
| 2 | *(everything)* | nothing changes: settled |

Then replies are printed and destroyed. Every arrow is *an entity spawned by one rule and destroyed by another*; no rule calls another. Inserting a rule between two of them is just registering it in between.

## Core rules of the model

- **Rule order is arbitration of who runs.** Rules run in registration order every tick; the same input gives the same output. `Loop.rule(priority=N)` (higher first, default 0) is the one override, for rules from domains that do not know about each other. There is no `watches=` argument: `loopingrules.analyze` infers which component types a rule reads and skips it on ticks where none exist.
- **A rule fires by changing something.** The loop compares `world.revision` before and after. Re-attaching an equal component is not a change, which is why `World.attach` compares before storing.
- **Destroying makes a rule fire once.** Goals and occasions are destroyed by whoever acts on them; standing entities (a folder, the session) are not.
- **A budget is the circuit breaker.** 200 ticks by default (`Loop(budget=...)`); the loop then reports which rules were still firing. Rule names are `module.function`, and must be unique per loop (`name=` overrides).
- **Nothing may block.** One thread, the engine's, touches the world. A rule that waits for a person must suspend *as state*: `fs.approve` spawns the question as a `Reply` and marks the wish `Asked`, and a later rule reads the answer off whichever channel it came from.

## Design notes

Longer arguments live under *Design notes*: [Propose / arbitrate / act](../intake processing.md) for resolving rival readings of one occasion, [Tunable knobs](../tunable knobs.md) for values that shape a decision, and the [Overview](../overview.md) for what changed in the engine and why.
