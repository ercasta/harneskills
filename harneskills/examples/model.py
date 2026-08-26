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
`StaleHunt`, `BigHunt`, `HuntHere`, `RenameWish`, `NeedsApproval` are
goals; `Listed`, `FoundStale`, `FoundBig`, `Renamed`, `Failed` are
occasions. A system destroys the entity it acted on, so the next tick has
nothing to match and the loop settles.

`NeedsApproval` is the one worth pausing on. A rename waiting for a person
and a rename about to happen are the same entity, and the only difference
is that tag::

    w.each(RenameWish, NeedsApproval)             # ask about these
    w.each(RenameWish, without=NeedsApproval)     # do these

Approving detaches it. Nothing moves between queues, nothing is copied,
and no flag has to be read to tell the two apart.
"""

from __future__ import annotations

from harneskills.world import Component


# -- what something is ---------------------------------------------------

class Folder(Component):
    """A directory, by path. One entity per path, and `fs.folder_at` is
    the only thing that makes them, so two systems asking about the same
    directory are asking about the same entity."""

    def __init__(self, path: str) -> None:
        self.path = path


class Contents(Component):
    """The folder's index: `name -> entity`, mutated in place.

    The one hand-kept structure in the domain, and it earns that: `ls`
    looks up every name it reads to decide whether the entry is new, and a
    query per name would make listing a folder quadratic in its size. Only
    `fs_tools` writes it -- see the ⚠ in that module.
    """

    def __init__(self) -> None:
        self.by_name: dict = {}


class Entry(Component):
    """Something in a folder, by name. `folder` is the folder's ENTITY,
    which is how a relationship is spelled here -- no object graph, no
    back reference to keep in step."""

    def __init__(self, folder, name: str) -> None:
        self.folder = folder
        self.name = name


class Size(Component):
    def __init__(self, num_bytes: int) -> None:
        self.bytes = int(num_bytes)


class Modified(Component):
    """When it was last written, as a unix time."""

    def __init__(self, when: int) -> None:
        self.when = int(when)


class IsDir(Component):
    """It is a directory. A tag: carrying it is the whole of the claim."""


class Session(Component):
    """Where the conversation is and what it measures by -- one entity,
    spawned at install.

    `now` is read from the clock ONCE, so a session open for an hour ages
    files against the clock it started with and the same question twice
    gets the same answer. `cwd` is where you launched, which is what a
    bare `show file` means however far a later listing wanders.
    """

    def __init__(self, cwd: str, now: int, big_floor: int) -> None:
        self.cwd = cwd
        self.now = int(now)
        self.big_floor = int(big_floor)


# -- what a system has concluded -----------------------------------------

class Focus(Component):
    """The folder you are looking at. Exactly one entity carries it, and
    `fs._focus` is what moves it: list A, list B, ask, and you get B.
    There is no attention model, nothing fades, and nothing is ranked."""


class Stale(Component):
    """Older than someone asked about. Detached when the file is dealt
    with -- a claim unmade, not a flag set back to False."""


class Big(Component):
    """Over the session's floor."""


# -- what is being asked for ---------------------------------------------

class ListWanted(Component):
    def __init__(self, folder) -> None:
        self.folder = folder


class StaleHunt(Component):
    def __init__(self, folder, days: int) -> None:
        self.folder = folder
        self.days = int(days)


class BigHunt(Component):
    def __init__(self, folder) -> None:
        self.folder = folder


class HuntHere(Component):
    """The hunt is on, but which folder is not decided yet. `focus_big`
    trades this tag for a `BigHunt` aimed at the folder you last looked
    at -- the same entity, now knowing where it is going."""


class RenameWish(Component):
    def __init__(self, entry, new_name: str) -> None:
        self.entry = entry
        self.new_name = new_name


class NeedsApproval(Component):
    """A person has not said yes yet. See this module's docstring."""


# -- what just happened --------------------------------------------------

class Listed(Component):
    def __init__(self, folder, count: int) -> None:
        self.folder = folder
        self.count = int(count)


class FoundStale(Component):
    def __init__(self, entry) -> None:
        self.entry = entry


class FoundBig(Component):
    def __init__(self, entry) -> None:
        self.entry = entry


class Renamed(Component):
    def __init__(self, entry, was: str) -> None:
        self.entry = entry
        self.was = was


class Failed(Component):
    def __init__(self, what: str, why: str) -> None:
        self.what = what
        self.why = why
