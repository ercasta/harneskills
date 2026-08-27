"""The game loop: call every system, over and over, until nothing changes.

A system is a Python function of one argument, the `World`. It QUERIES
the world -- `each`, `get`, `has`, `first`, `the` -- and it RETURNS a
list of deltas describing what should change, from `ugm.delta`. It does
not spawn, attach, detach or destroy anything itself::

    @loop.system
    def list_dir(w):
        deltas = []
        for entity, want in w.each(ListWanted):
            deltas.append(destroy(entity))
            deltas.extend(fs_tools.ls(w, want.folder))
        return deltas

`tick()` calls every registered system once, in registration order, and
applies each one's own deltas to the world immediately after calling it
-- before the next system runs, so a later system in the SAME tick still
sees what an earlier one just did, exactly as if it had mutated directly.
`run()` ticks until a whole pass changes nothing -- the world has
SETTLED, a full sweep of every system with nothing left to apply -- and
that is the moment the REPL gets its prompt back.

## Why deltas, and not a system calling `world.spawn` itself

A system that only ever RETURNS what it wants done is a pure function of
one `World` in the way `w.each(...)` already implies it should be: given
the same world, it answers the same way, every time, and answering it
does not require a running loop, a thread, or anything to clean up
afterward -- call it, read what it handed back. `ugm.delta.spawn(...)`
and friends are the same four verbs `World` always had, just handed back
as data instead of acted out immediately, so porting a system that used
to call `w.spawn(...)` is `spawn(...)`, appended to a list.

`tick()` checks this rather than trusting it: if a system's OWN code
moved `world.revision` (a stray `w.spawn`/`attach`/`detach`/`destroy`
call, forgetting the new contract), that is a loud, named error on
`loop.errors` -- not a silent bypass of the very discipline `Loop` exists
to hold everyone to.

## Order is registration order, and that is the whole of arbitration

There is no ranking, no attention, no scoring of which system most
deserves a turn. Systems run in the order they were installed, every tick,
and a system whose query is empty does nothing and costs a dict lookup. This
is a deliberately small idea, and it buys the thing it is hardest to buy
otherwise: the same input produces the same output, in the same order,
every time. If a listing should be reported entry-by-entry and then
counted, register the entry rule before the count rule and it is so.

## A system fires by CHANGING something

The loop cannot see inside a system and does not try. It reads
`world.revision` before and after applying what a system handed back --
a system whose deltas spawned an entity, destroyed one, or attached a
component that was not already there, fired; a system whose deltas
re-attached a component equal to the one already on the entity did not.
That is what settling is measured in, and it is why `World.attach`
comparing before it stores is load-bearing rather than a convenience.

## The budget is the circuit breaker

Two systems can feed each other forever -- one spawns what the other
destroys, which spawns what the first destroys. Nothing detects that in general, so the
loop counts ticks and stops at `budget`, handing back the systems that were
still firing when it ran out. The REPL prints them. A settled run reports
no hot systems, and that is how a caller tells the two apart.

## A system that raises does not take the session with it

The exception is caught, recorded on `loop.errors` (once per system and
message, however many ticks it raises on), and the loop goes on to the
next system. Nothing it returned is applied -- a system that raises
building its list of deltas has made none of them yet, and a system that
raises applying one (an entity a delta names that got destroyed by
another system first, say) may have applied the ones before it; either
way the world still settles, and the person at the prompt gets both
their prompt and the traceback's message, which is better than a REPL
that dies on a typo in a domain nobody is editing right now.
"""

from __future__ import annotations

import collections

from .delta import Delta

Settled = collections.namedtuple("Settled", "ticks hot")


def _name_of(fn) -> str:
    """`fs.flag_big` -- the module a system came from, then the function.

    Qualified because two domains installed at once will both have one
    called `hear`, and `/systems` listing it twice, or an error naming one
    of them, would send you to the wrong file.
    """
    module = getattr(fn, "__module__", "") or ""
    return "%s.%s" % (module.rsplit(".", 1)[-1], getattr(fn, "__name__", "rule"))


class Loop:
    """Systems, in order, over one world."""

    def __init__(self, world=None, budget: int = 200) -> None:
        from .world import World
        self.world = World() if world is None else world
        self.budget = budget
        self.systems: "list[tuple[str, object]]" = []
        # (system name, exception) for everything that blew up in the last
        # `run`. The caller drains it; the loop only ever appends.
        self.errors: "list[tuple[str, BaseException]]" = []

    # -- registering --------------------------------------------------

    def system(self, fn=None, *, name=None):
        """Register a system. Bare or called::

            @loop.system
            def flag_big(w): ...          # -> "fs.flag_big"

            @loop.system(name="flag big")
            def _(w): ...
        """
        if fn is None:
            return lambda f: self.system(f, name=name)
        self.systems.append((name or _name_of(fn), fn))
        return fn

    def install(self, fn, *args, **kwargs):
        """Hand this loop to a domain's own installer -- `install(loop)` --
        which is expected to register its rules and seed its facts. The one
        thing `harneskills.config` names, and the only shape of a domain
        this harness knows."""
        return fn(self, *args, **kwargs)

    # -- running ------------------------------------------------------

    def _record(self, name: str, error: BaseException) -> None:
        # Once per settle, not once per tick: a system that raises (or
        # keeps failing the same way) raises again on every pass until
        # the world stops moving, and one typed line should not print the
        # same traceback message four times.
        if not any(n == name and str(seen) == str(error)
                   for n, seen in self.errors):
            self.errors.append((name, error))

    def tick(self) -> "list[str]":
        """One pass over every system: call it, apply what it returned,
        move on. Returns the names of the ones that changed something."""
        fired = []
        for name, fn in self.systems:
            before = self.world.revision
            try:
                deltas = fn(self.world)
            except Exception as e:  # noqa: BLE001 -- see the module docstring
                self._record(name, e)
                continue
            if self.world.revision != before:
                self._record(name, RuntimeError(
                    "touched the world directly -- a system returns a "
                    "list of ugm.delta.spawn/attach/detach/destroy, it "
                    "does not call world.spawn/attach/detach/destroy "
                    "itself"))
                continue
            if not deltas:
                continue
            try:
                resolved: "dict" = {}
                for d in deltas:
                    if not isinstance(d, Delta):
                        raise TypeError(
                            "%r is not a delta -- see ugm.delta for the "
                            "four kinds a system may return" % (d,))
                    d._apply(self.world, resolved)
            except Exception as e:  # noqa: BLE001 -- see the module docstring
                self._record(name, e)
                continue
            if self.world.revision != before:
                fired.append(name)
        return fired

    def run(self, budget=None, after_tick=None) -> Settled:
        """Tick until a whole pass changes nothing.

        `Settled(ticks, hot)`: `hot` is empty on a clean settle, and holds
        the systems still firing if the budget ran out first.

        `after_tick()` is called after every tick that changed something,
        and it is not decoration: a system may BLOCK -- ask a person to
        approve something, wait on a network -- and everything the world
        had to say before that moment should already be on their screen
        when it does. Draining only once, at the end, is how a prompt ends
        up asking `approve rename X?` above the line explaining why.
        """
        budget = self.budget if budget is None else budget
        fired: "list[str]" = []
        for tick in range(1, budget + 1):
            fired = self.tick()
            if not fired:
                return Settled(tick, [])
            if after_tick is not None:
                after_tick()
        return Settled(budget, fired)
