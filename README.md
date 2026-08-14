# HarneSkills

**A door onto a [UGM](https://github.com/ercasta/Universal-Graph-Machine) machine.**

UGM is an agent that plans, acts, observes and explains itself on one graph
substrate. Everything it concludes is already in that graph — its own design
notes make the point that the missing piece was never more reasoning, it was a
way to *be told*. HarneSkills is that: a terminal you can drive it from, with the
graph on screen beside the transcript while it thinks.

```
┌────────────────────────────────────────┬──────────────────────────────┐
│ > /load corpus/kettle.ugm              │ world 3  goal 27  act 4      │
│   loaded corpus/kettle.ugm: 4 statem…  │ ┌ asked for/graph/rules/play┐│
│ > /run                                 │  asked for:                  │
│     1 [applied] a rule applied         │    boiling(kettle)   [held]  │
│         +recall(boiling(kettle))       │      water(kettle)   [held]  │
│     …                                  │      doing(heat(kettle))     │
│   >> heat(kettle)                      │  did:                        │
│   — 37 ticks, ended quiescent          │    heat(kettle)              │
├────────────────────────────────────────┴──────────────────────────────┤
│ > why boiling(kettle)                                                 │
└───────────────────────────────────────────────────────────────────────┘
```

---

## Try it

```bash
pip install -e ../ugm          # the engine, editable, from its own checkout
pip install -e .
harneskills corpus/kettle.ugm  # or: python -m harneskills_tui
```

Then, at the prompt:

```
/run                    think until there is nothing left
/report                 what became of what was asked for
/why boiling(kettle)    why it believes that, and on whose word
/graph act              what left the agent
/scenarios              something to play
```

No terminal? `python -m harneskills` is the same thing without Textual.

---

## The one idea worth knowing

**What you type is the corpus language.** A line starting `rule`, `fact` or `say`
goes straight into the machine, unchanged:

```
fact +water(kettle)
rule <boil> = causes( { +doing(heat(?w)), +water(?w) }, { +boiling(?w) } )
say user: +raining(here)
```

There is no second, friendlier syntax to learn and nothing to keep in sync — an
interactive session is one document that happens to arrive slowly, and anything
you type here you can paste into a `.ugm` file. Anything that is *not* a
statement or a `/command` is read as a term to ask about: type `boiling(kettle)`
and you get the verdict and the provenance trail.

---

## What you can see

The right-hand pane re-reads the machine while it thinks. Three views, because a
reader has three different questions:

| view | answers |
|---|---|
| **asked for** | the goal → plan → subgoal tree: *is it getting anywhere?* Rows are coloured `held` / `open` / **BLOCKED** |
| **graph** | every settled proposition in one layer: *what does it believe?* |
| **rules** | what can come to mind, and which have actually applied |

Press <kbd>Ctrl+G</kbd> to cycle the layer, or <kbd>Enter</kbd> on a row to print
its provenance in the transcript.

**Layers** exist because a working machine holds ~150 propositions of bookkeeping
for every 3 about the world, and showing them undifferentiated shows nothing:

- `world` — what the corpus is about: relations *it* coined
- `goal` — what is wanted, the plans for it, what they need
- `act` — what left the agent, what it did, what it expected
- `search` — how it is looking: fits, checks, recall, verdicts
- `talk` — what arrived, who said it, where it was loaded from
- `meta` — the bookkeeping: rules as data, tools, standing, silences

The split is drawn from the engine's own `Machine.reserved` rather than a list
kept here, so a relation your corpus coins is `world` automatically and a new
engine relation lands in `meta` — neither needs this repo edited.

---

## You are a tool

UGM can register an *answerer*: something that answers a request without
searching for it. HarneSkills registers **you** as one.

```
/load corpus/ask.ugm
/run
  ? weather(today)
> sunny(here)
```

The agent asks, the driver blocks, and what comes back is
`answered(<human>, question, answer)` — a *record that you said so*, not a
belief. Whether to believe you is an ordinary rule in the corpus:

```
rule <believe-human> = implies( { +answered(<human>, ?q, ?a) }, { +?a } )
```

Delete it and you have an agent that consults you and then decides for itself.
Wrap it as `+likely(?a)` and it takes your word as a hint. That the harness
*cannot* decide this for you is the design working: an interface that believed
its user directly would be settling something the corpus is entitled to argue
with.

---

## Play the dungeon

The engine ships a turn-based fight authored entirely in rules
(`ugm/rules/dungeon.ugm`) — initiative, hit resolution, damage, fleeing, death
and victory are all ordinary `implies`/`causes` over ordinary claims, and the
engine has never heard of a goblin. Upstream runs it as a batch test with the
player's moves scripted at the bottom of the corpus. Here you play it:

```
/play dungeon 7     seeded — the same fight every time
/run
  ? round 1 -- what does the hero do?
  e.g. attack(goblin1)   attack(goblin2)
> attack(goblin1)
```

It stops each round, asks, and carries on. The **play** tab keeps the scoreboard:

```
round 3 -- hero to act

> hero      hp 3   standing
  goblin1   hp 5   standing
  goblin2   hp 5   standing
```

Leave `/play`'s seed off for a genuinely external die. Answer blank to decline —
the corpus has a standing policy (`<hero-holds>`) that swings for you.

Nothing in the engine or the corpus was modified to make this work. A **cue** is
a state the harness watches for between ticks; when it fires, the drive pauses,
you are asked, and your answer is `say`'d on the `player` channel — which is all
a player ever was. `<trust-player>` is the corpus rule that turns your utterance
into an intention, and deleting it leaves your declarations on the record,
believed by nobody.

Because the roll is a *tool* rather than a hidden dice-roller, the provenance
goes all the way down:

```
/why hp(goblin1, 1)
  +hp(goblin1, 1) @M0, licensed by applied(<wound>)
    because +hits(hero, goblin1, 4) @M0, licensed by applied(<hit>)
    because +answered(dice, roll(d6, hurt(hero, goblin1), 4), 4) …
    because +hp(goblin1, 5) @M0, via dungeon, licensed by loaded(hp(goblin1, 5))
    because +answered(arith, calc(sub, 5, 4), 1) …
```

The roll that hurt it, the arithmetic that did the subtraction, and the round it
happened in are all on the trail, because a tool *proposes* and a rule concludes.

⚠ The hero can lose, and does at seed 7. Try 1, 2 or 11.

---

## Layout

```
harneskills/
  runner.py     a Machine, its corpora and name scopes, driven a tick at a time
  view.py       read-only projections: what holds, what is wanted, what applied
  commands.py   the verb vocabulary, as data, shared by every front end
  play.py       cues: where a machine stops so a person can speak into it
  dungeon.py    the engine's fight corpus, made playable
  repl.py       a plain terminal front end, no Textual
harneskills_tui/
  screen.py     transcript left, machine right, prompt below
  panes.py      the graph pane
  session.py    the driver thread, and the human-as-a-tool door
corpus/
  kettle.ugm    a goal, a plan, and an act that leaves the agent
  weather.ugm   the boundary: the agent does not simply believe its user
  ask.ugm       you, as a tool the agent consults
```

`view.py` never concludes anything — it walks the graph, groups and formats, and
that invariant is asserted in `tests/test_view.py`. A viewer that starts deriving
is a second engine with no provenance.

---

## Scope

**HarneSkills is a UI/UX layer over UGM. Nothing else.** The two were split
precisely to separate these concerns, so the test for anything proposed here is
one question: *is this how a human sees, drives, or authors for UGM?* Planning,
arbitration, norms, procedures, credit assignment and provenance are the
engine's. Earlier versions of this repo grew all of them; re-growing them would
be un-splitting the split.

## Status

Rebuilt against the current UGM (`restart`). ⚠ That engine is under active
redesign — grades left the entry and `@` left the surface between two afternoons
— so read `../ugm/docs/HANDOFF.md` before diagnosing an import error. The
previous harness, built on the deleted production-rule/CNL engine, is in git
history; nothing was ported from it.

Run the suite with `pytest` (63 tests, including a headless drive of the real TUI
and a whole dungeon fight played through it).
