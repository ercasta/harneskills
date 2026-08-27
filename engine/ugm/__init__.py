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

UGM ships no domain, no channel and no transport. `Engine.attach` wants
anything with `.name`, `.deliver(message)`, and optionally `.start(engine)`
/ `.close()` -- a terminal, a WebSocket, a test double, all the same
shape. `harneskills` is the worked door onto this: `harneskills.repl`,
`harneskills.serve` and `harneskills.client` are channels built on top of
`Engine`, and `harneskills.examples.fs` is a domain built on top of
`World` and `Loop` -- neither of which this package knows exists.
"""

from __future__ import annotations

from . import delta, engine, loop, save, world
from .engine import Engine
from .loop import Loop
from .world import World

__version__ = "0.1.0"

__all__ = ["Engine", "Loop", "World", "delta", "engine", "loop", "save",
          "world", "__version__"]
