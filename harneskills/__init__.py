"""HarneSkills -- doors onto a `ugm` world: a terminal, any number of
WebSocket connections, and the domains that give either one something to
say.

    python -m harneskills harneskills.examples.fs:install
    python -m harneskills --serve harneskills.examples.fs:install   # + a WebSocket door

The engine itself -- the entity-component world, the loop of systems over
it, the one thread and the channel contract -- is `ugm`, not this
package; see `ugm`'s own docstring. What lives here is everything that
was never the engine's to know:

* `harneskills.repl` -- a `Terminal` channel: stdin in, prose out.
* `harneskills.serve` / `harneskills.ws` -- a `Listener` channel and the
  WebSocket codec under it, for a connection that is not this process's
  own terminal. `harneskills.client` is the other end of that wire, a
  small program with no world of its own.
* `harneskills.config` -- which domains a session installs, and where the
  world and server files live on this platform.
* `harneskills.__main__` -- argv, wiring an `Engine` from `ugm` around
  whichever channels were asked for.

A DOMAIN is one callable, `install(loop)`, that registers systems and
spawns what they read -- named on the command line or in
`~/.config/harneskills/config`, never shipped by the harness.
`harneskills.examples.fs` is the worked one: listing, ageing and renaming
real files, with every rename an automation proposes held for approval,
asked as an ordinary reply rather than a blocked keypress -- nothing a
system does may stop the world for a channel that is not the one asking.
"""

from __future__ import annotations

from ugm import Engine, Loop, World

from . import repl

__version__ = "0.4.0"

__all__ = ["Engine", "Loop", "World", "repl", "__version__"]
