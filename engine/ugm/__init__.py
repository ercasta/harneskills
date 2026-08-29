"""UGM -- Universal Graph Machine: an entity-component world, a loop that
runs rules over it, and one thread to run a session on.

    from ugm import Engine, Loop, World

* `ugm.world` -- entities (identity, no data) and components: plain
  `@dataclasses.dataclass` instances, no base class, holding only
  `None`/`bool`/`int`/`float`/`str` and `list`/`dict`/`tuple` of those --
  another entity is referenced by its plain id, never a live handle. An
  entity may carry SEVERAL components of one type.
* `ugm.delta` -- what a rule RETURNS instead of touching the world:
  `spawn`, `attach`, `replace`, `detach`, `remove`, `destroy`, as data.
* `ugm.loop` -- call every rule, in order, until a whole pass changes
  nothing. A rule is a function of one `World` that returns a list of
  deltas; `Loop.tick` is what applies them. A rule may declare
  `watches=` -- the component types it could possibly do anything with --
  and stay uncalled on any tick where none of them exist yet; it may also
  declare `priority=` to run ahead of another rule, regardless of which
  was registered first.
* `ugm.engine` -- ONE thread that runs the loop, and the channels
  attached to it. `Said(name, "...")` in from whichever channel it
  arrived on; `Reply(user, "...")` out to every channel there is.
* `ugm.save` -- the world as JSONL (one record per line), and back.

That is the whole of `ugm`: entities and components, nothing else in this
package's own vocabulary. `harneskills` is the worked door onto it --
`harneskills.repl`, `harneskills.serve` and `harneskills.client` are
channels built on top of `Engine`, and `harneskills.examples.fs` is a
domain built on top of `World` and `Loop` alone -- neither of which this
package knows exists.

⚠⚠ `ugm.facts` / `ugm.arbitration` / `ugm.request` are NOT imported here.
They predate the rewrite above (plain dataclasses, several components per
type, primitives-only fields) and do not currently work against it --
`facts.Relation` subclassed a `Component` base class this package no
longer has. They are ON HOLD, not deleted, pending a decision on whether a
`fact`/`state`/`deny` vocabulary belongs in this package at all, or only as
an optional, clearly-separate pattern library -- see `docs/TODO.md`.
"""

from __future__ import annotations

from . import delta, engine, loop, save, world
from .engine import Engine
from .loop import Loop
from .world import World

__version__ = "0.1.0"

__all__ = ["Engine", "Loop", "World", "delta", "engine", "loop", "save",
          "world", "__version__"]
