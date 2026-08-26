"""HarneSkills -- an entity-component world, a loop that runs systems over
it, and any number of channels attached to it.

    python -m harneskills harneskills.examples.fs:install
    python -m harneskills --serve harneskills.examples.fs:install   # + a WebSocket door

* `harneskills.world` -- entities (identity, no data) and components
  (data, no identity). Everything anything knows.
* `harneskills.loop` -- call every system, in order, until a whole pass
  changes nothing. A system is a function of one `World`.
* `harneskills.engine` -- ONE thread that runs the loop, and the channels
  attached to it: a terminal, several WebSocket connections, any mix.
  `Said(name, "...")` in from whichever channel it arrived on;
  `Reply(user, "...")` out to every channel there is.
* `harneskills.repl` -- a `Terminal` channel: stdin in, prose out.
* `harneskills.serve` / `harneskills.ws` -- a `Listener` channel and the
  WebSocket codec under it, for a connection that is not this process's
  own terminal. `harneskills.client` is the other end of that wire, a
  small program with no world of its own.
* `harneskills.save` -- writes the world down every time it settles, so a
  restart is not an amnesia.

A DOMAIN is one callable, `install(loop)`, that registers systems and
spawns what they read -- named on the command line or in
`~/.config/harneskills/config`, never shipped by the harness.
`harneskills.examples.fs` is the worked one: listing, ageing and renaming
real files, with every rename an automation proposes held for approval,
asked as an ordinary reply rather than a blocked keypress -- nothing a
system does may stop the world for a channel that is not the one asking.
"""

from __future__ import annotations

from . import engine, loop, repl, save, world
from .engine import Engine
from .loop import Loop
from .world import World

__version__ = "0.4.0"

__all__ = ["Engine", "Loop", "World", "engine", "loop", "repl", "save",
          "world", "__version__"]
