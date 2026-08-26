"""HarneSkills -- an entity-component world, a loop that runs systems over
it, and a prompt onto both.

    python -m harneskills harneskills.examples.fs:install

Three small modules and no engine:

* `harneskills.world` -- entities (identity, no data) and components
  (data, no identity). Everything anything knows.
* `harneskills.loop` -- call every system, in order, until a whole pass
  changes nothing. A system is a function of one `World`.
* `harneskills.repl` -- a line becomes `Said(user, "...")`, the loop runs,
  and whatever a system spawned as `Reply(user, "...")` is printed.

...and `harneskills.save`, which writes the world down every time it
settles, so a restart is not an amnesia.

A DOMAIN is one callable, `install(loop)`, that registers systems and
spawns what they read -- named on the command line or in
`~/.config/harneskills/config`, never shipped by the harness.
`harneskills.examples.fs` is the worked one: listing, ageing and renaming
real files, with every rename an automation proposes held for approval by
one component.
"""

from __future__ import annotations

from . import loop, repl, save, world
from .loop import Loop
from .world import World

__version__ = "0.3.0"

__all__ = ["Loop", "World", "loop", "repl", "save", "world", "__version__"]
