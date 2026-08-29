"""The game loop: call every rule, over and over, until nothing changes.

A rule is a Python function of one argument, the `World`. It QUERIES
the world -- `each`, `get`, `has`, `first`, `the` -- and it WRITES to it
directly -- `spawn`, `attach`, `replace`, `detach`, `remove`, `destroy` --
the same four-turned-six verbs `install()` already calls outside any
rule's turn::

    @loop.rule
    def list_dir(w):
        for entity, want in w.each(ListWanted):
            w.destroy(entity)
            fs_tools.ls(w, want.folder)

`tick()` calls every registered rule once, in tick order (see `priority`,
below), and a rule's own writes are visible to the world -- and so to the
next rule in the SAME tick -- the instant it makes them, because there is
nothing in between: no list of changes to build, nothing later that
applies it. `run()` ticks until a whole pass changes nothing -- the world
has SETTLED -- and that is the moment the REPL gets its prompt back.

## Why a rule may touch the world directly

A rule is already a plain function of one `World`, called once per tick
in a known order, by the one place (`Loop.tick`) that ever calls it --
nothing about reasoning over what it does needs its writes described
rather than made: `world.revision` before and after the call already
says whether it fired (see below), the same as it would if the writes
arrived by way of a returned list first. Handing back a description of a
change instead of making it bought exactly one thing -- a rule that
FORGOT the contract and touched the world anyway could be caught, named,
and refused -- and it cost real weight for that one guarantee: a second
vocabulary for the four things `World` already does, and a `Pending`
placeholder standing in for an entity `spawn()` had not made "real" yet
even though nothing was stopping it from being real immediately. That
guarantee also stopped holding well before this note did: three of this
harness's own rules called `w.spawn`/`w.destroy` directly for a while
before anyone noticed, and the suite stayed green throughout, because
nothing asserted `loop.errors == []`. A rule that wants to defer or hold
something (a proposed rename, say) still can -- the same way `fs.py`
already does it, as a component sitting in the world (`RenameWish` +
`NeedsApproval`) for another rule to query, approve, or leave alone. That
is what "proposed" means here now; it never needed a second, lower-level
notion of "not yet real" underneath every ordinary write too.

## Order is registration order, unless a rule says otherwise

By default there is no ranking, no attention, no scoring of which rule
most deserves a turn: rules run in the order they were installed, every
tick, and a rule whose query is empty does nothing and costs a dict
lookup. This is a deliberately small idea, and it buys the thing it is
hardest to buy otherwise: the same input produces the same output, in the
same order, every time. If a listing should be reported entry-by-entry and
then counted, register the entry rule before the count rule and it is so.

`loop.rule(fn, priority=N)` is the one deliberate override: HIGHER runs
FIRST, ties (including the default, `0`, when nobody sets one) keep
registration order. This is what settles the case registration order
cannot express on its own -- two rules `watches`-ing the SAME component
type, installed by two domains that do not know about each other and so
cannot agree on which one to register first. Declared once, by whichever
rule actually needs to run before the other, it is a property of the
RULE rather than an accident of install order.

⚠ Priority is a total order over every rule, not a per-type one -- two
rules that watch entirely disjoint types are still ordered by it. That
is not a hazard: only a shared type ever makes the relative order of two
rules OBSERVABLE (each rule in its own tick still ends up doing what
its own query finds, regardless of who ran first, unless they touch the
same entities), so widening the ordering as a matter of policy costs
nothing a domain could actually notice going wrong, and it is far simpler
than the alternative -- an ordering that is only PARTIALLY defined, so
that a rule newly given a shared type with another discovers the tie is
suddenly broken by installation order it never chose.

## A rule fires by CHANGING something

The loop cannot see inside a rule and does not try. It reads
`world.revision` before and after calling it -- a rule that spawned an
entity, destroyed one, or attached a component that was not already
there, fired; a rule that re-attached a component equal to the one
already on the entity did not. That is what settling is measured in, and
it is why `World.attach` comparing before it stores is load-bearing
rather than a convenience.

## A rule may declare what would ever wake it

`loop.rule(fn, watches=(Kind, ...))` tells the loop the component types a
rule could possibly have something to do with. A rule that declared
`watches` is skipped -- its Python body never called at all -- on any tick
where `world.populated(*watches)` is false, i.e. NOTHING carries any of
those types yet. `watches=None` (the default) means what it always meant:
called every tick, no questions asked.

⚠ `watches` must be an OVER-approximation of what could matter, not the
exact query -- get it right and a whole class of rules in a large ruleset
stay silent, entities and all, until their own domain has anything on the
world at all; get it wrong (name too NARROW a set) and the rule goes
dormant while something it depended on sits unnoticed on a type it never
declared, which looks exactly like the old "no inert set" hang except
inverted: not too much firing, but a rule that should have fired and
silently didn't. There is no way to catch this from here -- `populated` does
not know what a rule's own body reads -- so declare a superset when in
doubt; a rule that watches one type too many merely gets called with
nothing to do, the same cost `each()` already pays on an empty bucket.

⚠ A rule is one entry in `self.rules` and `tick()` visits each entry
exactly once, so watching several types is never a reason to be called
more than once in the same tick -- there is no per-type dispatch loop
here to accidentally invoke a rule twice for two types that both
happen to be populated. "Watch three types, run once" is not a rule this
module enforces; it is a rule this module's SHAPE makes impossible to
break.

## The budget is the circuit breaker

Two rules can feed each other forever -- one spawns what the other
destroys, which spawns what the first destroys. Nothing detects that in general, so the
loop counts ticks and stops at `budget`, handing back the rules that were
still firing when it ran out. The REPL prints them. A settled run reports
no hot rules, and that is how a caller tells the two apart.

## A rule that raises does not take the session with it

The exception is caught, recorded on `loop.errors` (once per rule and
message, however many ticks it raises on), and the loop goes on to the
next rule. Whatever the rule already wrote before it raised stands --
there is nothing to roll back to, the same as any ordinary function that
mutates something and then throws -- but the world still settles, and the
person at the prompt gets both their prompt and the traceback's message,
which is better than a REPL that dies on a typo in a domain nobody is
editing right now.
"""

from __future__ import annotations

import collections

Settled = collections.namedtuple("Settled", "ticks hot")


def _name_of(fn) -> str:
    """`fs.flag_big` -- the module a rule came from, then the function.

    Qualified because two domains installed at once will both have one
    called `hear`, and `/rules` listing it twice, or an error naming one
    of them, would send you to the wrong file.
    """
    module = getattr(fn, "__module__", "") or ""
    return "%s.%s" % (module.rsplit(".", 1)[-1], getattr(fn, "__name__", "rule"))


class Loop:
    """Rules, in order, over one world."""

    def __init__(self, world=None, budget: int = 200) -> None:
        from .world import World
        self.world = World() if world is None else world
        self.budget = budget
        self.rules: "list[tuple[str, object]]" = []
        # (rule name, exception) for everything that blew up in the last
        # `run`. The caller drains it; the loop only ever appends.
        self.errors: "list[tuple[str, BaseException]]" = []

    # -- registering --------------------------------------------------

    def rule(self, fn=None, *, name=None, watches=None, priority=0):
        """Register a rule. Bare or called::

            @loop.rule
            def flag_big(w): ...          # -> "fs.flag_big"

            @loop.rule(name="flag big")
            def _(w): ...

            @loop.rule(watches=(Request,))
            def watch(w): ...             # skipped while no Request exists

            @loop.rule(watches=(Request,), priority=10)
            def watch_first(w): ...       # ahead of any priority-0 watcher
                                           # of Request, whoever installed it

        `watches`, if given, is a component type or a tuple of them --
        see the module note on what it promises and what it does not.
        `priority` orders the tick -- higher runs first, ties (the
        default, `0`, included) keep registration order -- see the module
        note on why this is a total order rather than a per-type one.
        """
        if fn is None:
            return lambda f: self.rule(f, name=name, watches=watches,
                                         priority=priority)
        if watches is not None:
            fn._ugm_watches = ((watches,) if isinstance(watches, type)
                               else tuple(watches))
        fn._ugm_priority = priority
        self.rules.append((name or _name_of(fn), fn))
        return fn

    def install(self, fn, *args, **kwargs):
        """Hand this loop to a domain's own installer -- `install(loop)` --
        which is expected to register its rules and seed its facts. The one
        thing `harneskills.config` names, and the only shape of a domain
        this harness knows."""
        return fn(self, *args, **kwargs)

    # -- running ------------------------------------------------------

    def _record(self, name: str, error: BaseException) -> None:
        # Once per settle, not once per tick: a rule that raises (or
        # keeps failing the same way) raises again on every pass until
        # the world stops moving, and one typed line should not print the
        # same traceback message four times.
        if not any(n == name and str(seen) == str(error)
                   for n, seen in self.errors):
            self.errors.append((name, error))

    def _tick_order(self) -> "list[int]":
        """Indices into `self.rules`, in the order THIS tick calls
        them: `priority` descending, registration index ascending on a
        tie -- `self.rules` itself stays in registration order (what
        `/rules` and every direct reader of it expects), this is purely
        `tick()`'s own execution order, recomputed fresh so a rule
        registered after the loop has already ticked once takes its
        declared priority into account immediately, not from whenever it
        happened to be appended.
        """
        return sorted(range(len(self.rules)), key=lambda i: (
            -getattr(self.rules[i][1], "_ugm_priority", 0), i))

    def tick(self) -> "list[str]":
        """One pass over every rule, in tick order: call it, done. Returns
        the names of the ones that changed something, in the order they
        ran."""
        fired = []
        for i in self._tick_order():
            name, fn = self.rules[i]
            watches = getattr(fn, "_ugm_watches", None)
            if watches is not None and not self.world.populated(*watches):
                continue    # dormant -- not even called, see the module note
            before = self.world.revision
            try:
                fn(self.world)
            except Exception as e:  # noqa: BLE001 -- see the module docstring
                self._record(name, e)
                continue
            if self.world.revision != before:
                fired.append(name)
        return fired

    def run(self, budget=None, after_tick=None) -> Settled:
        """Tick until a whole pass changes nothing.

        `Settled(ticks, hot)`: `hot` is empty on a clean settle, and holds
        the rules still firing if the budget ran out first.

        `after_tick()` is called after every tick that changed something,
        and it is not decoration: a rule may BLOCK -- ask a person to
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
