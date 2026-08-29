# UGM

**An entity-component world, a loop that runs rules over it, and one
thread to run a session on.**

An *entity* is an identity with no data — `#7`. A *component* is data
with no identity — `Size(bytes=4300)`. A *rule* is a Python function of
one `World` that asks for the entities carrying a set of components,
walks them, and WRITES to it directly — `spawn`/`attach`/`replace`/
`detach`/`remove`/`destroy`. The *loop* calls every rule, once a tick,
over and over, until a whole pass changes nothing, and that is when the
world has something to say. The *engine* is one thread that owns that
loop and routes what it says to however many channels are attached to it.

```
ugm/
  world.py        entities, components, and the queries rules ask
  loop.py         every rule, in order, until nothing changes
  engine.py       one thread, the world, and the channels attached to it
  save.py         the world as JSONL: entities are ints, components are values
tests/
  test_world.py        identity, values, and the intersection of the two
  test_loop.py         order, settling, the budget, a rule that raises
  test_engine.py       one world, several channels, a broadcast reply
  test_save.py         the same world, ids and all, next time
DECISION_PATTERNS.md   a design note this package no longer ships the code
                          for -- see History, "Facts/arbitration/request
                          removed"
```

## Try it

```bash
pip install -e .
python3 -c "
from ugm import Loop
from ugm.world import Reply, Said

loop = Loop()

@loop.rule
def greet(w):
    for e, said in w.each(Said):
        w.destroy(e)
        w.spawn(Reply('user', 'hi, %s' % said.text))

loop.world.spawn(Said('user', 'world'))
loop.run()
for e, r in loop.world.each(Reply):
    print(r.text)
"
```

## Scope

**No domain, no channel, no transport.** `world.py`, `loop.py`,
`engine.py` and `save.py` ship no rules, no components
beyond `Said` and `Reply` (the shapes `Engine.drain` and `Engine._do`
route by), and no knowledge of files, sockets, or terminals. `Engine`
wants anything with `.name`, `.deliver(message)`, and optionally
`.start(engine)` / `.close()` — no base class, no import required to be
one.

**And no vocabulary above entities and components either, any more.**
This package used to also ship `facts.py`/`arbitration.py` — a
`fact`/`state`/`deny` way of writing relations as components, and a
generic reader arbitrating between rules proposing/vetoing/ranking
candidates for one contested decision. Removed, not ported, once the
core above was rewritten — see History, "Facts/arbitration/request
removed." `DECISION_PATTERNS.md` keeps the argument for why a generic
arbitration reader beats agency in the base rule (extracted from
`pystrider`, a domain that measured the alternative's cost first: two
repair rules firing on one bug, "correct by luck"); it just is not code
in this package any more. A domain that wants that pattern writes its
own components and its own generic reader over them, the way
`harneskills.examples.fs` already writes everything else it needs.

**`harneskills`, in the parent of this directory, is the worked door onto
it** — a `Terminal` channel, a WebSocket `Listener` and `client`, a
config-file format for naming domains, and `harneskills.examples.fs`, a
domain built on `World` and `Loop` alone. None of that is imported here;
this package does not know `harneskills` exists.

## History

**Facts/arbitration/request removed, 2026-08-30.** `facts.py`,
`arbitration.py` and `request.py` -- ON HOLD since the previous entry,
below -- are deleted outright, along with their tests. Nothing in this
repository ever imported any of the three (`harneskills.examples.fs`
writes its own components throughout), they had not imported themselves
since the core rewrite two entries down, and there was no third path
between "port them" and "delete them" left worth keeping open: the
standing argument for a generic arbitration reader
(`DECISION_PATTERNS.md`, kept) does not need the CODE to survive, only
a domain that wants it to reach for the pattern by hand.

**Deltas removed, 2026-08-30.** A rule calls `world.spawn`/`attach`/
`replace`/`detach`/`remove`/`destroy` directly again, the same as
`install()` always did — see "Deltas, 2026-08-27" below for what this
undoes. The guarantee deltas bought (a rule that forgot the contract and
touched the world anyway got caught, named, on `loop.errors`) had already
stopped holding in practice: three rules in `harneskills`'s own test suite
called `w.spawn`/`w.destroy` directly, `loop.errors` recorded the
violation every tick, and the suite stayed green throughout because
nothing asserted it was empty. The other half of the argument for
removing it: a "proposed" action that matters to a domain is better
modelled as an explicit component sitting in the world for another rule
to query (`fs.py`'s `RenameWish` + `NeedsApproval` already does exactly
this) than as a second, lower-level notion of "not yet real" underneath
every write, including the ones no domain ever treats as provisional at
all. `ugm.delta` — `Pending`, the six delta classes, the two `_resolve_*`
functions — is deleted outright, not deprecated; `Loop.tick` is
correspondingly a few lines shorter, with nothing left to apply after
calling a rule and nothing left to check for a rule having "cheated."

**Priority ordering, 2026-08-29.** `Loop.rule(fn, priority=N)` -- higher
runs first, ties (the default, `0`, included) keep registration order.
The one deliberate override of "registration order is the whole of
arbitration": two rules `watches`-ing the same component type, installed
by two domains that do not know about each other and so cannot agree on
which one to register first. A rule is still one entry in `self.rules`
regardless of how many types it watches, so declaring `priority` changes
WHEN it runs, never how many times.

**Rules, not systems, 2026-08-29.** `Loop.system`/`Facts.system` →
`Loop.rule`/`Facts.rule`, `self.systems` → `self.rules`, the `/systems`
REPL command → `/rules`, `fs.py`'s `SYSTEMS` tuple → `RULES`, and every
docstring, comment, and README that said "a system is a function that..."
now says "a rule." "Filesystem," `SystemExit`, `systemd`, and TOML's own
`[build-system]` table name are the same words for something else
entirely and stayed put.

**A request/response protocol, 2026-08-29.** `request.py` extracted the
other pattern `docs/overview.md` had been asking for since before this package's
own split: a rule deposits a request (a `details` entity, characterized by
ordinary facts and listed in one row of `request(hub, details)`), any number
of responders `respond`/`complete` on it without knowing about each other or
the asker, and one generic `watch()` retires it -- `fulfilled` once every
responder that started has finished, `timed_out` if a tick budget (widened by
a responder's own `extend()`) runs out first. It is `arbitration.commit`'s
counterpart for a different shape of question ("did everyone answer" rather
than "who won"), and the one place either module fires on a clock rather
than a change: ageing the counter *is* the observable a silent, hung, or
simply absent responder needs someone to notice.

This is `ugm` a second time. The first `universal-graph-machine` was a
graph substrate `harneskills` was a terminal onto — a corpus format, a
loader, attention and arbitration over a graph of facts. That dependency
was dropped and replaced with `loop.py`: a rule is a Python function
of one `World`, not a rule matched against a graph, and the loop calls
every one of them in registration order until a pass changes nothing.
This package is that replacement, carved back out once `harneskills`'s
own split between "the engine" and "the doors onto it" had already drawn
the line the old dependency used to sit on.

**A vocabulary, 2026-08-28.** `facts.py` and `arbitration.py` arrived from
`pystrider`, which had carried them since it was rewritten onto this world.
`facts.py` lost the one thing that was about living in another checkout —
`_NEEDS`, a set of `ugm` names asserted on import so that drift failed by
name rather than three frames into a run. It versions with `world.py` now,
so there is no gap left to assert across.

**A world of facts survives a restart, 2026-08-28.** It did not before, and
it failed quietly, which is the worst way. `save` resolves a component by
`module:ClassName` with `getattr`; `relation()` MAKES its classes with
`type()`; so every relation in a saved world came back as one named problem
and a dropped component, and a relation whose name collided with something
`ugm.facts` imports (`spawn`, `attach`) raised `TypeError` out of `load` and
cost the session rather than the component. A class may now say how to name
itself — `Relation` answers `ugm.facts:relation(for_stmt)`, and the trailing
call is resolved by calling it. ⭐ The second half was that interning lived
in `Facts._words`, a dict beside the world: restoring the components alone
would have given you a fact pointing at one `Printed("loop")` and every new
rule asking for another. Which entity is THE one for its text is a component
now (`Interned`), so it comes back too, and `_words` is a cache of the world
rather than the truth about it.

**Deltas, 2026-08-27.** A rule stopped being allowed to touch a world
at all. It used to call `world.spawn`/`attach`/`detach`/`destroy`
directly, applied and visible the moment it did; now it RETURNS a list
of `ugm.delta` values describing what should happen, and `Loop.tick` is
the only thing that ever calls those four methods, right after a rule
returns, before the next one runs -- so a later rule in the same tick
still sees an earlier one's own effect, the same as direct mutation
always let it. `tick()` checks this rather than trusting it: a rule
whose own code moved `world.revision` is a named, loud error on
`loop.errors`, not a silent bypass. The one real wrinkle was a `spawn`
a rule wants to use again before its own turn ends -- attach more to
it, embed it in another component's field -- solved by handing back a
`Pending` from `spawn()` that resolves to the real entity the moment its
`Spawn` is applied, walking every later delta in the same list and every
field of every component in it for the same token (`_resolve_component`,
built the way `ugm.save` already rebuilds a component off disk, without
its `__init__`).
