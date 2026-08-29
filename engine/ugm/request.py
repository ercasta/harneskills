"""General request/response, over the same substrate `arbitration.py` uses:
propose as facts, let any number of oblivious rules answer, run to a fixpoint
-- plus the one thing a candidate-set decision does not need and a fan-out
request does: a **watchdog**, because a responder can be silent forever
(hung, buggy, simply absent) where a judge that lacks information at least
says so (`needs`, see `arbitration.py`'s own note on that).

    hub = f.node("analysis-requests")            # a singleton, or not
    details = request(f, hub, "analyze_python", program)
    ...
    f.run()                                       # responders race, watchdog ages it

A REQUEST is a `details` entity -- minted fresh per ask, characterized by
ordinary facts on it (`f.fact("analyze_python", details, program)`), and
listed in one row of `request(hub, details)`. Any number of "interested"
rules watch `request`, decide for themselves (by reading `details`'s own
facts, exactly the way a judge in `arbitration.py` reads a candidate's
`realizes` chain) whether they have anything to say, and if so:

    f.fact("responding", details, my_worker)      # "I'm on it"
    ...
    f.fact("completed", details, my_worker)       # "done" -- my own answer is
                                                   # wherever I deposited it,
                                                   # this module does not care

`watch()` is the ONE generic reader, the counterpart to `arbitration.commit`:
every tick it is installed, it ages every still-open request by one, and
retires it -- `deny`s the `request` row off the hub -- the moment either of
two things is true: every worker that signalled `responding` has also
signalled `completed` (**fulfilled**), or the age reaches `timeout` ticks,
widened by whatever a responder asked for with `extend()` (**timed_out**).
Either way `outcome(details, word)` is `state()`d so a reader never has to
tell "still open" from "gave up" by absence.

## Why this needs an active clock, and `arbitration.py` needs none

`arbitration.commit` only ever fires because something a judge wrote changed
-- a `ruled_out`, a `ranked`. `watch()` fires every tick a request is open
whether or not anything else did, because ageing a counter *is* the
observable: a request nobody is answering has to be seen and retired, not
sit invisibly waiting for a change that will never come. That is a
deliberate, narrow exception to `Loop`'s "a rule fires by changing
something" -- it is still true here, the changing thing is just the clock
itself, and it is bounded: the counter can move at most `timeout` (plus
extensions) ticks past a request's birth before `watch()` closes it and stops
touching it, so a session that never issues another request settles exactly
as it always did.

## Why the details entity carries facts, not raw components

`facts.py`'s whole discipline is that a rule describes by writing
`fact`/`state` onto an entity, never by touching the world -- so "the
request has extra components that characterize it" is spelled the same way
everything else here is: ordinary relations on `details`, readable by
`f.of`/`f.has`/`f.one` exactly like a candidate's `realizes` chain, rather
than a second, raw-`Component` path this module would have to special-case.

## What this module deliberately does not do

No priority, no cancellation, no result channel. A worker's answer is
whatever facts it deposits about `details`, addressed however the domain
likes (`f.reify`, a fresh entity of its own, a fact directly on `details`) --
this module only ever asks "did everyone who started finish, or did the
clock run out," the same way `arbitration.commit` only ever asks "who
survived, who leads."
"""
from __future__ import annotations

from .facts import Facts, relation
from .world import Entity

Request = relation("request")          # request(hub, details)
Responding = relation("responding")    # responding(details, worker)
Completed = relation("completed")      # completed(details, worker)
Extend = relation("extend")            # extend(details, worker, ticks)   -- fact
Elapsed = relation("elapsed")          # elapsed(details, ticks)          -- state
Outcome = relation("outcome")          # outcome(details, word)           -- state


# -- the asking side: sugar, not a second mechanism -----------------------------

def request(f: Facts, hub: Entity, kind: str, *objects: Entity) -> Entity:
    """Mint a fresh `details` entity, characterize it as `kind(details,
    *objects)` -- the fact interested rules read to know what is being
    asked -- and list it in the hub's open requests. Returns `details` so
    the caller may deposit further facts onto it before or after.

    ⭐ A thin wrapper, not a special path: `f.fact("kind", details, ...)`
    followed by `f.fact("request", hub, details)` is exactly what this does,
    spelled once so a caller does not have to remember the order (the
    request must name a `details` that already carries its own kind, or a
    responder racing it on the very next tick reads nothing there yet).
    """
    details = f.node(kind)
    f.fact(kind, details, *objects)
    f.fact("request", hub, details)
    return details


def extend(f: Facts, details: Entity, worker: Entity, ticks: int) -> None:
    """A responder's own ask for more time -- widens `watch()`'s deadline
    for this request by `ticks`, on top of whatever `timeout` it was
    installed with. Idempotent per `(details, worker, ticks)`, the same as
    any other fact: asking twice for the same extension does not grant it
    twice."""
    f.fact("extend", details, worker, f.value(ticks))


# -- the generic watchdog: the one reader, symmetric to arbitration.commit ------

def watch(f: Facts, timeout: int = 20):
    """Age every open request by one tick; retire it fulfilled the moment
    every worker that started has finished, or timed out once its age
    reaches `timeout` plus whatever `extend()` granted it -- whichever
    comes first. See the module note for why this, alone here, fires on a
    clock rather than on a change a responder made.
    """

    def rule(world) -> None:
        for hub, details in f.each("request", arity=1):
            if f.has("outcome", details):
                # ⚠ Retired on an earlier tick; the row itself is already
                # `deny`d below the tick it happened, so this only guards
                # the one tick in between "denied" and the loop no longer
                # yielding it from `f.each("request")` at all.
                continue
            current = f.one("elapsed", details)
            age = 1 if current is None else f.payload(current) + 1
            f.state("elapsed", details, f.value(age))

            responding = {f.show(w) for w in f.objects("responding", details)}
            completed = {f.show(w) for w in f.objects("completed", details)}
            if responding and responding <= completed:
                f.state("outcome", details, f.word("fulfilled"))
                f.deny("request", hub, details)
                continue

            deadline = timeout + sum(
                f.payload(row[1]) for row in f.of("extend", details)
                if len(row) == 2
            )
            if age >= deadline:
                f.state("outcome", details, f.word("timed_out"))
                f.deny("request", hub, details)

    return rule


def install(loop, f: Facts, timeout: int = 20) -> None:
    """Register the watchdog. `timeout` is in ticks, not wall time -- the
    same unit `Loop.budget` already counts in.

    ⚠ `watches="request"`, not `"elapsed"` or `"outcome"`: this rule
    WRITES those two every tick it runs, so watching either would mean
    "run again because I just ran" -- a self-feeding dormancy check is no
    dormancy at all. `request` is the one relation only the ASKING side
    ever writes, which is exactly the type whose presence should wake this
    up and whose absence should let it sleep.
    """
    f.rule(watch(f, timeout=timeout), name="request.watch", watches="request")
