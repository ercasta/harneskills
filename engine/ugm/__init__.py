"""UGM -- Universal Graph Machine: an entity-component world, a loop that
runs systems over it, and one thread to run a session on.

    from ugm import Engine, Loop, World

* `ugm.world` -- entities (identity, no data) and components (data, no
  identity). Everything anything knows.
* `ugm.delta` -- what a system RETURNS instead of touching the world:
  `spawn`, `attach`, `detach`, `destroy`, as data.
* `ugm.loop` -- call every system, in order, until a whole pass changes
  nothing. A system is a function of one `World` that returns a list of
  deltas; `Loop.tick` is what applies them.
* `ugm.engine` -- ONE thread that runs the loop, and the channels
  attached to it. `Said(name, "...")` in from whichever channel it
  arrived on; `Reply(user, "...")` out to every channel there is.
* `ugm.save` -- the world as plain data, and back.

* `ugm.facts` -- the VOCABULARY systems say things in: a relation is a
  component type, its objects are that component's ordered rows, and a
  kind is one empty row. `fact`/`state`/`deny` to write, `of`/`one`/
  `holds` to read.
* `ugm.arbitration` -- how several systems decide ONE contested thing
  without knowing about each other: propose `candidate`s, justify them
  through `realizes`, veto with `ruled_out`, order with `ranked`, and let
  ONE generic `commit` read the whole set and name a `winner`.

⚠⚠ THE LAST TWO ARE A DISCIPLINE, NOT A DOMAIN. `ugm` still ships no
files, no sockets, no syntax and no business — `facts.py` cannot tell you
what a relation MEANS. What it does ship is the way to write systems that
compose, and unlike a domain that is not optional: a system that keeps its
conclusion in a local variable is invisible to every other system, to
`arbitration.commit` and to `save`, and a rule family that decides for
itself whether to fire has an opinion about registration order whether or
not its author meant it to. Both were measured, at cost, in a domain built
on this package; see each module's own note.

UGM ships no domain, no channel and no transport. `Engine.attach` wants
anything with `.name`, `.deliver(message)`, and optionally `.start(engine)`
/ `.close()` -- a terminal, a WebSocket, a test double, all the same
shape. `harneskills` is the worked door onto this: `harneskills.repl`,
`harneskills.serve` and `harneskills.client` are channels built on top of
`Engine`, and `harneskills.examples.fs` is a domain built on top of
`World` and `Loop` -- neither of which this package knows exists.
"""

from __future__ import annotations

from . import arbitration, delta, engine, facts, loop, save, world
from .engine import Engine
from .facts import Facts, relation
from .loop import Loop
from .world import World

__version__ = "0.1.0"

__all__ = ["Engine", "Facts", "Loop", "World", "arbitration", "delta",
          "engine", "facts", "loop", "relation", "save", "world",
          "__version__"]
