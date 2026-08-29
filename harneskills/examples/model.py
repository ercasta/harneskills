"""What a thing in the filesystem domain can BE: the components, and
nothing that does anything with them.

Read as three groups, because a system reads them that way too:

**What something is.** `Folder`, `Contents`, `Entry`, `Size`, `Modified`,
`IsDir`, `Session`. Observation and setting -- put there by a tool or at
install time, and true until the disk says otherwise.

**What a system has concluded.** `Stale`, `Big`, `Focus`. Tags: no fields,
so every instance is equal to every other and attaching one twice is not a
change. Being stale is not a property of a file, it is a claim
`flag_stale` made about it -- and `detach(entity, Stale)` unmakes it.

**What is being asked for, and what just happened.** `ListWanted`,
`StaleHunt`, `BigHunt`, `HuntHere`, `RenameWish`, `NeedsApproval`,
`Asked` are goals; `Listed`, `FoundStale`, `FoundBig`, `Renamed`,
`Failed` are occasions. A system destroys the entity it acted on, so the
next tick has nothing to match and the loop settles.

`NeedsApproval` is the one worth pausing on. A rename waiting for a person
and a rename about to happen are the same entity, and the only difference
is that tag::

    w.each(RenameWish, NeedsApproval)             # ask about these
    w.each(RenameWish, without=NeedsApproval)     # do these

Approving detaches it. Nothing moves between queues, nothing is copied,
and no flag has to be read to tell the two apart. `Asked` is the same
idea one step earlier: the question has gone out and the wish is
waiting on an answer that will arrive as an ordinary line on an ordinary
channel, not as a return value nothing here is allowed to block for.

## Every class here is a plain, frozen dataclass

`ugm.world` ships no `Component` base class to inherit -- a component is
whatever `dataclasses.is_dataclass` says yes to. `folder`/`entry`/every
other field that names another entity holds its plain integer id, never a
live handle: `World.attach` lowers a handle passed in (the ergonomic thing
to write, straight from a query) to its `.id` on the way in, so nothing
below has to spell `.id` itself.
"""

from __future__ import annotations

from dataclasses import dataclass, field


# -- what something is ---------------------------------------------------

@dataclass(frozen=True)
class Folder:
    """A directory, by path. One entity per path, and `fs.folder_at` is
    the only thing that makes them, so two systems asking about the same
    directory are asking about the same entity."""

    path: str


@dataclass(frozen=True)
class Contents:
    """The folder's index: `name -> entity id`.

    Computed fresh by `fs_tools.ls`/`rename` every time -- never mutated
    in place -- and put on with `world.replace`, which is what makes
    re-listing an unchanged folder cost a dict comparison rather than a
    revision: this used to be the one hand-kept structure in the domain,
    mutated by hand and reported with `world.changed()`, until a system
    stopped being the thing allowed to touch a world at all -- see
    `ugm.delta`.
    """

    by_name: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Entry:
    """Something in a folder, by name. `folder` is the folder's ENTITY id,
    which is how a relationship is spelled here -- no object graph, no
    back reference to keep in step."""

    folder: int
    name: str


@dataclass(frozen=True)
class Size:
    bytes: int


@dataclass(frozen=True)
class Modified:
    """When it was last written, as a unix time."""

    when: int


@dataclass(frozen=True)
class IsDir:
    """It is a directory. A tag: carrying it is the whole of the claim."""


@dataclass(frozen=True)
class Session:
    """Where the conversation is and what it measures by -- one entity,
    spawned at install.

    `now` is read from the clock ONCE, so a session open for an hour ages
    files against the clock it started with and the same question twice
    gets the same answer. `cwd` is where you launched, which is what a
    bare `show file` means however far a later listing wanders.
    """

    cwd: str
    now: int
    big_floor: int


# -- what a system has concluded -----------------------------------------

@dataclass(frozen=True)
class Focus:
    """The folder you are looking at. Exactly one entity carries it, and
    `fs._focus` is what moves it: list A, list B, ask, and you get B.
    There is no attention model, nothing fades, and nothing is ranked."""


@dataclass(frozen=True)
class Stale:
    """Older than someone asked about. Detached when the file is dealt
    with -- a claim unmade, not a flag set back to False."""


@dataclass(frozen=True)
class Big:
    """Over the session's floor."""


# -- what is being asked for ---------------------------------------------

@dataclass(frozen=True)
class ListWanted:
    folder: int


@dataclass(frozen=True)
class StaleHunt:
    folder: int
    days: int


@dataclass(frozen=True)
class BigHunt:
    folder: int


@dataclass(frozen=True)
class HuntHere:
    """The hunt is on, but which folder is not decided yet. `focus_big`
    trades this tag for a `BigHunt` aimed at the folder you last looked
    at -- the same entity, now knowing where it is going."""


@dataclass(frozen=True)
class RenameWish:
    entry: int
    new_name: str


@dataclass(frozen=True)
class NeedsApproval:
    """A person has not said yes yet. See this module's docstring."""


@dataclass(frozen=True)
class Asked:
    """The question has already gone out for this wish -- `approve` put
    it on `Reply(user, ...)` and is now waiting for an answer on the same
    channel every other reply goes out on.

    A tag, not a callback: nothing here blocks, because nothing in an
    engine of several channels is allowed to (see `ugm.engine`).
    `approve` asks at most one thing at a time -- a wish carrying this is
    a wish `approve` will not ask about again, so the next tick's fresh
    proposal waits its turn instead of talking over the first question.
    """


# -- what just happened --------------------------------------------------

@dataclass(frozen=True)
class Listed:
    folder: int
    count: int


@dataclass(frozen=True)
class FoundStale:
    entry: int


@dataclass(frozen=True)
class FoundBig:
    entry: int


@dataclass(frozen=True)
class Renamed:
    entry: int
    was: str


@dataclass(frozen=True)
class Failed:
    what: str
    why: str
