# UGM

**An entity-component world, a loop that runs systems over it, and one
thread to run a session on.**

An *entity* is an identity with no data — `#7`. A *component* is data
with no identity — `Size(bytes=4300)`. A *system* is a Python function of
one `World` that asks for the entities carrying a set of components,
walks them, and RETURNS what should change, as a list of deltas —
`ugm.delta.spawn`/`attach`/`detach`/`destroy` — rather than touching the
world itself. The *loop* calls every system, applies what it returned,
and moves to the next, over and over, until a whole pass changes
nothing, and that is when the world has something to say. The *engine*
is one thread that owns that loop and routes what it says to however
many channels are attached to it.

```
ugm/
  world.py     entities, components, and the queries systems ask
  delta.py     what a system RETURNS instead of touching the world
  loop.py      every system, in order, until nothing changes
  engine.py    one thread, the world, and the channels attached to it
  save.py      the world as JSON: entities are ints, components are values
tests/
  test_world.py    identity, values, and the intersection of the two
  test_delta.py    a Pending resolves to what its own Spawn became
  test_loop.py     order, settling, the budget, a system that raises
  test_engine.py   one world, several channels, a broadcast reply
  test_save.py     the same world, ids and all, next time
```

## Try it

```bash
pip install -e .
python3 -c "
from ugm import Loop
from ugm.delta import destroy, spawn
from ugm.world import Reply, Said

loop = Loop()

@loop.system
def greet(w):
    return [d for e, said in w.each(Said)
           for d in (destroy(e), spawn(Reply('user', 'hi, %s' % said.text)))]

loop.world.spawn(Said('user', 'world'))
loop.run()
for e, r in loop.world.each(Reply):
    print(r.text)
"
```

## Scope

**No domain, no channel, no transport.** `world.py`, `delta.py`,
`loop.py`, `engine.py` and `save.py` ship no systems, no components
beyond `Said` and `Reply` (the shapes `Engine.drain` and `Engine._do`
route by), no vocabulary, and no knowledge of files, sockets, or
terminals. `Engine` wants anything with `.name`, `.deliver(message)`,
and optionally `.start(engine)` / `.close()` — no base class, no import
required to be one.

**`harneskills`, in the parent of this directory, is the worked door onto
it** — a `Terminal` channel, a WebSocket `Listener` and `client`, a
config-file format for naming domains, and `harneskills.examples.fs`, a
domain built on `World` and `Loop` alone. None of that is imported here;
this package does not know `harneskills` exists.

## History

This is `ugm` a second time. The first `universal-graph-machine` was a
graph substrate `harneskills` was a terminal onto — a corpus format, a
loader, attention and arbitration over a graph of facts. That dependency
was dropped and replaced with `loop.py`: a system is a Python function
of one `World`, not a rule matched against a graph, and the loop calls
every one of them in registration order until a pass changes nothing.
This package is that replacement, carved back out once `harneskills`'s
own split between "the engine" and "the doors onto it" had already drawn
the line the old dependency used to sit on.

**Deltas, 2026-08-27.** A system stopped being allowed to touch a world
at all. It used to call `world.spawn`/`attach`/`detach`/`destroy`
directly, applied and visible the moment it did; now it RETURNS a list
of `ugm.delta` values describing what should happen, and `Loop.tick` is
the only thing that ever calls those four methods, right after a system
returns, before the next one runs -- so a later system in the same tick
still sees an earlier one's own effect, the same as direct mutation
always let it. `tick()` checks this rather than trusting it: a system
whose own code moved `world.revision` is a named, loud error on
`loop.errors`, not a silent bypass. The one real wrinkle was a `spawn`
a system wants to use again before its own turn ends -- attach more to
it, embed it in another component's field -- solved by handing back a
`Pending` from `spawn()` that resolves to the real entity the moment its
`Spawn` is applied, walking every later delta in the same list and every
field of every component in it for the same token (`_resolve_component`,
built the way `ugm.save` already rebuilds a component off disk, without
its `__init__`).
