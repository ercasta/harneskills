"""The filesystem domain: what a person's words mean, and what to do about it.

    python -m harneskills harneskills.examples.fs:install

Thirteen systems over `model.py`'s components and `fs_tools.py`'s three
tools. Read top to bottom, they are the order they run in each tick, and
that order is the whole of the plan::

    hear            Said                       -> a goal entity
    hear_answer     Said ("y"/"n")              -> resolves the wish being Asked
    list_dir        ListWanted                  -> the tools, and Listed
    reply_listing   Listed                      -> one line per entry, then a count
    approve         RenameWish+NeedsApproval, not yet Asked  -> a question
    flag_stale      StaleHunt                   -> Stale on every old entry, FoundStale
    propose_rename  FoundStale                  -> RenameWish + NeedsApproval  NEVER a rename
    do_rename       RenameWish (without NeedsApproval)  -> the tool
    focus_big       HuntHere                    -> BigHunt, aimed at the folder you mean
    flag_big        BigHunt                     -> Big on every large entry, FoundBig
    reply_big / reply_renamed / reply_failed     -> what you are told

`approve` sits ABOVE the system that proposes, which reads like a mistake
and is not: a proposal made this tick is therefore asked about on the NEXT
one, which is what puts "2 of 5 older than 7 day(s)" on screen before the
question about the first of them. System order is the schedule, and a
tick boundary is the only thing there is to schedule against.

Every system here RETURNS a list of deltas instead of touching the world
-- see `ugm.delta` -- and `Loop.tick` applies one system's own deltas
right after calling it, before the next system runs. That is what makes
the schedule above still mean what it says: `list_dir` returning what
makes a folder's listing real is applied before `reply_listing` runs, in
the SAME tick, the same as if `list_dir` had spawned it directly.

## The compounding step is `propose_rename`, and it is one line

Finding a stale file attaches `Stale`. Deciding what to DO about a stale
file is a different system, and what it spawns is a WISH carrying
`NeedsApproval` -- not a rename. A domain that wanted to archive instead
of rename changes that system and nothing else: the tools, the listing,
the approval prompt and every reply stay exactly as they are.

## Approval is a component, not a feature

`propose_rename` attaches `NeedsApproval` because an automation proposed
it. Typing `rename a to b` yourself spawns the same `RenameWish` WITHOUT
the tag, and `do_rename` asks for exactly that::

    w.each(RenameWish, without=NeedsApproval)

So nothing holds your own renames, one system asks about everything held,
and approving is `detach(entity, NeedsApproval)` -- the same wish, no
longer waiting. Wanting your own renames held too is one more `attach`,
not a different design.

Asking is a component too. `approve` cannot call a function and wait for
your answer -- the world may have other channels attached, and nothing
here is allowed to stop for one of them (see `ugm.engine`) -- so
it returns the question as an ordinary `Reply` and marks the wish `Asked`.
`hear_answer` is the other half: a bare "y" or "n", on whichever channel
it arrives, resolves whichever wish is currently `Asked`. The suspension
IS the state; there is no callback held anywhere waiting to be called.

## A system loops, so a guard is rarely needed

`flag_big` walks every entry in the folder in a `for`, in one call, and
destroys the goal entity that let it run. It cannot fire twice on the same
goal because the goal is gone, so there is no per-file bookkeeping to
write, and none to get wrong.
"""

from __future__ import annotations

import os
import time

from ugm.delta import attach, destroy, detach, spawn
from ugm.world import Reply, Said

from . import fs_tools
from .model import (Asked, Big, BigHunt, Contents, Entry, Failed, Focus,
                    Folder, FoundBig, FoundStale, HuntHere, IsDir,
                    ListWanted, Listed, Modified, NeedsApproval, RenameWish,
                    Renamed, Session, Size, Stale, StaleHunt)

BIG_BYTES = 1000
STALE_PREFIX = "stale-"
DAY = 86400

# What this domain expects a person to type -- the only thing the prompt's
# autocorrect will pull a typo towards. Both spellings of `file` are here
# because both are understood; nothing has to be corrected into the other.
WORDS = ("show", "file", "files", "big", "in", "stale", "after", "day",
         "days", "rename", "to")


# -- getting hold of things ----------------------------------------------

def folder_at(w, path: str):
    r"""`(deltas, entity)` -- the entity for this directory: the one that
    already exists, or a new one this call's own `deltas` describe. The
    only place a `Folder` is described, so two systems asking about the
    same directory are asking about the same entity -- once the `Spawn`
    that names it has actually been applied.

    Matched through `os.path.normcase`, which is what makes `C:\Notes`
    and `c:\notes` one folder on a filesystem that thinks they are one
    folder, and leaves them two where it does not (it is the identity
    function on Unix). What is STORED is the spelling first seen, because
    that is the one to show a person -- normalising for comparison and
    normalising for display are different jobs, and only the first one is
    the world's business.

    Not `realpath`: two paths to one directory through a symlink stay two
    folders here, deliberately. Asking about `/var/log` is not the same
    act as asking about wherever it points, and a listing that silently
    answered about somewhere else would be worse than one that answers
    about both.
    """
    wanted = os.path.normcase(path)
    for entity, folder in w.each(Folder):
        if os.path.normcase(folder.path) == wanted:
            return [], entity
    made = spawn(Folder(path), Contents())
    return [made], made.entity


def here(w):
    """`(deltas, entity)` -- the folder the conversation is about: the
    one you last looked at, or the one the session started in."""
    focused = w.first(Folder, Focus)
    if focused is not None:
        return [], focused[0]
    return folder_at(w, w.the(Session).cwd)


def _known_here(w):
    """The folder the conversation is about, IF the world already has
    one -- `None` otherwise, and nothing is described to find out.

    What `_understand`'s rename branch needs: it must read `Contents`
    back THIS SAME CALL to look a name up, which only a REAL, already
    -applied folder has. A folder nobody has listed answers every name
    the same way `here`/`folder_at` creating one fresh would -- an empty
    `Contents` -- so there is nothing to create only to find that out.
    """
    focused = w.first(Folder, Focus)
    if focused is not None:
        return focused[0]
    wanted = os.path.normcase(w.the(Session).cwd)
    for entity, folder in w.each(Folder):
        if os.path.normcase(folder.path) == wanted:
            return entity
    return None


def _focus(w, folder):
    """You are looking at this folder now, and at no other."""
    return [detach(e, Focus) for e, _ in w.each(Focus)] + [attach(folder, Focus())]


def _listed(w, folder):
    """`(deltas, entries)` -- `entries` as `(entity, name, size, modified,
    is_dir)`, either read straight off the world (already listed --
    `deltas` is empty) or freshly found by `fs_tools.ls` THIS TURN if
    nobody had looked yet, in which case `entries` is what `ls` itself
    just found and `deltas` is what makes that listing durable.

    A question about a folder nobody listed is a question about nothing,
    and answering `0 files` would be a lie about the disk rather than a
    fact about it -- so this never skips listing, only skips it a SECOND
    time, the same policy `_listed` always had.
    """
    contents = w.get(folder, Contents)
    if contents.by_name:
        entries = []
        for name in sorted(contents.by_name):
            child = contents.by_name[name]
            size = w.get(child, Size)
            modified = w.get(child, Modified)
            entries.append((child, name, size.bytes if size else None,
                           modified.when if modified else None,
                           w.has(child, IsDir)))
        return [], entries
    deltas, entries, _count = fs_tools.ls(w, folder)
    return deltas, entries


def _entries(w, folder) -> "list":
    """Every entity in the folder, by name. Sorted here rather than
    trusted from the index: what order the world happens to hold things in
    is not something a person reading the answer should be able to
    notice."""
    by_name = w.get(folder, Contents).by_name
    return [by_name[name] for name in sorted(by_name)]


def _describe(w, entity) -> str:
    """`todo.txt (17 bytes)`, or `archive/` -- one entry, for a person."""
    name = w.get(entity, Entry).name
    if w.has(entity, IsDir):
        return "%s/" % name
    size = w.get(entity, Size)
    return "%s (%d bytes)" % (name, size.bytes) if size else "%s (unreadable)" % name


def _say(text: str):
    return spawn(Reply("user", text))


# -- what a typed line means ---------------------------------------------

def _path(text: str) -> str:
    """A path as a person types one: quoted if it needs to be, `~` if they
    like, and the rest of the line taken whole so a space is nothing
    special.

    Absolute on the way out, because `folder_at` compares what comes out
    of here and two spellings of one directory must not become two
    folders: `notes`, `./notes`, `notes/` and `/home/you/notes` are one
    place, each with its own `Contents` to fill and its own `Focus` to
    fight over if they are not.
    """
    return os.path.abspath(os.path.expanduser(text.strip().strip('"').strip("'")))


def _understand(w, line: str):
    """The deltas this line asks for, if this domain has a reading of it
    -- `None` if it does not. Plain Python over plain words, no grammar
    and no parser, and every case here is one a person actually types."""
    words = line.split()
    low = [word.lower() for word in words]
    if not words:
        return None

    if low[0] == "show" and len(words) >= 2:
        rest = words[2:]
        where = _path(" ".join(rest[1:])) if low[2:3] == ["in"] and rest[1:] else None
        if low[1] in ("file", "files"):
            deltas, folder = folder_at(w, where or w.the(Session).cwd)
            return deltas + [spawn(ListWanted(folder))]
        if low[1] == "big":
            if where is None:
                return [spawn(HuntHere())]
            deltas, folder = folder_at(w, where)
            return deltas + [spawn(BigHunt(folder))]

    if low[0] == "stale" and "after" in low:
        at = low.index("after")
        days = low[at + 1] if low[at + 1:at + 2] and low[at + 1].isdigit() else None
        # `stale in DIR after N days` -- everything between `in` and
        # `after` is the folder; `stale after N days` means where you are.
        where = _path(" ".join(words[2:at])) if low[1:2] == ["in"] and at > 2 else None
        if days is not None:
            deltas, folder = folder_at(w, where) if where else here(w)
            return deltas + [spawn(StaleHunt(folder, int(days)))]

    if low[0] == "rename" and "to" in low:
        at = low.index("to")
        old, new = " ".join(words[1:at]), " ".join(words[at + 1:])
        folder = _known_here(w)
        by_name = w.get(folder, Contents).by_name if folder is not None else {}
        if old and new and old in by_name:
            # No `NeedsApproval`: you are not an automation, and nothing
            # holds what you asked for yourself.
            return [spawn(RenameWish(by_name[old], new))]
        if old and new:
            return [spawn(Failed("rename %s" % old, "no such file here"))]
    return None


# -- the systems ----------------------------------------------------------

def hear(w):
    """What you typed -> a goal, if this domain has a reading of it.

    Any channel -- `said.channel` is whichever terminal or socket a person
    is attached as (`ugm.engine`'s own concern), and `"user"` is
    not one of those any more, it is where a reply meant for everyone
    goes. This domain does not (yet) answer only the one who asked; every
    reply it makes is `Reply("user", ...)`, heard by whoever is
    connected, which is the ordinary MUD answer for a world nobody has
    taught to whisper.
    """
    deltas = []
    for entity, said in w.each(Said):
        understood = _understand(w, said.text)
        if understood is not None:
            deltas.extend(understood)
            deltas.append(destroy(entity))
        # Left standing otherwise: the prompt says nobody understood it.
    return deltas


def hear_answer(w):
    """A bare yes/no -> the wish now waiting on an answer, if there is one.

    Runs before `approve` asks about anything else, so at most one wish is
    ever waiting -- see `Asked`. A "y" or "n" that arrives with nothing
    outstanding is not this domain's business and is left for `hear` to
    try as everything else it might mean (which, being one letter, is
    nothing -- and it is reported unheard, same as any other line no
    system claims).
    """
    held = w.first(RenameWish, NeedsApproval, Asked)
    if held is None:
        return None
    entity, wish, _, _ = held
    for said_entity, said in w.each(Said):
        answer = said.text.strip().lower()
        if answer not in ("y", "yes", "n", "no"):
            continue
        entry = w.get(wish.entry, Entry)
        if answer in ("y", "yes"):
            # The same wish, no longer waiting. `do_rename` asks for
            # exactly this and will pick it up this same tick.
            return [destroy(said_entity), detach(entity, NeedsApproval),
                   detach(entity, Asked)]
        return [destroy(said_entity), destroy(entity),
               _say("left %s alone" % entry.name)]
    return None


def list_dir(w):
    """ListWanted -> the `ls` tool, and the folder you are now in."""
    deltas = []
    for entity, want in w.each(ListWanted):
        deltas.append(destroy(entity))
        ls_deltas, _entries, count = fs_tools.ls(w, want.folder)
        deltas.extend(ls_deltas)
        if count is None:
            continue   # `Failed` is already in ls_deltas; reply_failed says it
        deltas.extend(_focus(w, want.folder))
        deltas.append(spawn(Listed(want.folder, count)))
    return deltas


def reply_listing(w):
    """One line per entry, then the count -- in that order, because this
    system returns them in that order and nothing reorders replies."""
    deltas = []
    for entity, listed in w.each(Listed):
        deltas.append(destroy(entity))
        for child in _entries(w, listed.folder):
            deltas.append(_say(_describe(w, child)))
        deltas.append(_say("%d item(s) in %s"
                          % (listed.count, w.get(listed.folder, Folder).path)))
    return deltas


def flag_stale(w):
    """StaleHunt -> `Stale` on every entry older than it asked about."""
    deltas = []
    for entity, hunt in w.each(StaleHunt):
        deltas.append(destroy(entity))
        listed_deltas, entries = _listed(w, hunt.folder)
        deltas.extend(listed_deltas)
        now, found = w.the(Session).now, 0
        for child, _name, _size, modified, is_dir in entries:
            if modified is None or is_dir:
                continue
            if (now - modified) // DAY >= hunt.days:
                deltas.append(attach(child, Stale()))
                deltas.append(spawn(FoundStale(child)))
                found += 1
        deltas.append(_say("%d of %d older than %d day(s) in %s"
                          % (found, len(entries), hunt.days,
                             w.get(hunt.folder, Folder).path)))
    return deltas


def propose_rename(w):
    """FoundStale -> a PROPOSAL to rename it. The compounding step: a
    finding becomes a plan, and a plan is not an act."""
    deltas = []
    for entity, found in w.each(FoundStale):
        deltas.append(destroy(entity))
        entry = w.get(found.entry, Entry)
        if entry is None or entry.name.startswith(STALE_PREFIX):
            continue   # already carries the mark; renaming it again is noise
        deltas.append(spawn(RenameWish(found.entry, STALE_PREFIX + entry.name),
                            NeedsApproval()))
    return deltas


def do_rename(w):
    """A wish nobody is waiting on -> the tool. Reached by an approval
    detaching the tag, or straight from a person typing `rename a to b`,
    and this system cannot tell which -- which is the point: holding is
    the proposer's business, not the act's."""
    deltas = []
    for entity, wish in w.each(RenameWish, without=NeedsApproval):
        deltas.append(destroy(entity))
        rename_deltas, ok = fs_tools.rename(w, wish.entry, wish.new_name)
        deltas.extend(rename_deltas)
        if ok:
            deltas.append(detach(wish.entry, Stale))   # dealt with: the claim is unmade
    return deltas


def focus_big(w):
    """HuntHere -> the same entity, now a BigHunt aimed at the folder you
    last looked at."""
    deltas = []
    for entity, _tag in w.each(HuntHere):
        deltas.append(detach(entity, HuntHere))
        here_deltas, folder = here(w)
        deltas.extend(here_deltas)
        deltas.append(attach(entity, BigHunt(folder)))
    return deltas


def flag_big(w):
    """BigHunt -> `Big` on every entry over the session's floor. One call,
    one `for`, no per-file bookkeeping."""
    deltas = []
    for entity, hunt in w.each(BigHunt):
        deltas.append(destroy(entity))
        listed_deltas, entries = _listed(w, hunt.folder)
        deltas.extend(listed_deltas)
        floor, found = w.the(Session).big_floor, 0
        for child, _name, size, _modified, is_dir in entries:
            if size is None or is_dir or size < floor:
                continue
            deltas.append(attach(child, Big()))
            deltas.append(spawn(FoundBig(child)))
            found += 1
        if not found:
            deltas.append(_say("nothing over %d bytes in %s"
                              % (floor, w.get(hunt.folder, Folder).path)))
    return deltas


# -- what you are told ----------------------------------------------------
# Every system above decides what HAPPENED. These decide what a person
# reading the prompt hears about it, and they are the ones to edit for a
# quieter or louder session -- nothing above this line returns a reply.

def reply_big(w):
    deltas = []
    for entity, found in w.each(FoundBig):
        deltas.append(destroy(entity))
        deltas.append(_say(_describe(w, found.entry)))
    return deltas


def reply_renamed(w):
    deltas = []
    for entity, renamed in w.each(Renamed):
        deltas.append(destroy(entity))
        deltas.append(_say("renamed %s -> %s"
                          % (renamed.was, w.get(renamed.entry, Entry).name)))
    return deltas


def reply_failed(w):
    deltas = []
    for entity, failed in w.each(Failed):
        deltas.append(destroy(entity))
        deltas.append(_say("! could not %s: %s" % (failed.what, failed.why)))
    return deltas


# -- installing -----------------------------------------------------------

def approve(w):
    """The next unasked wish -> a question, and `Asked`, so it is not asked
    twice.

    Asks at most ONE thing at a time, however many wishes are waiting, and
    that is TWO checks, not one: not-yet-`Asked` picks which wish is next,
    and the guard above it -- nothing to do if one is `Asked` already --
    is what stops a second question going out before the first is
    answered. Losing the second check does not show up against one stale
    file; the moment two are proposed in the same tick, the loop simply
    ticks again after asking the first (asking IS a change), and without
    the guard it asks about the second right then, before anyone could
    have answered the first. `hear_answer` reads the answer off whichever
    channel it arrives on, so a live question has to be the only one, or
    a bare "y" would not say which it meant.

    ⚠ This used to call `ask(prompt)` and block for the answer -- the
    right thing for one terminal owning the loop, and wrong the moment
    more than one channel can be attached (`ugm.engine`): nothing
    a system does may stop the world for everyone else. The fix is not a
    trick, it is the thing this whole domain already does for every other
    goal -- suspend as a component (`Asked`), and let the answer arrive as
    an ordinary line whenever it does.
    """
    if w.first(RenameWish, NeedsApproval, Asked) is not None:
        return None   # a question is already outstanding; wait for its answer
    held = w.first(RenameWish, NeedsApproval, without=Asked)
    if held is None:
        return None
    entity, wish, _tag = held
    entry = w.get(wish.entry, Entry)
    folder = w.get(entry.folder, Folder).path
    return [attach(entity, Asked()),
           _say("approve rename %s -> %s in %s? [y/n]"
               % (entry.name, wish.new_name, folder))]


SYSTEMS = (hear, hear_answer, list_dir, reply_listing, approve,
           flag_stale, propose_rename, do_rename, focus_big, flag_big,
           reply_big, reply_renamed, reply_failed)


def install(loop, clock=time.time, cwd=os.getcwd) -> None:
    """Every system, in order, plus the one `Session` they read.

    `clock` and `cwd` are arguments because a domain that reads the world
    outside the world should say where it does it. Both are read ONCE,
    here -- see `model.Session`.

    ⚠ The world handed in may already hold everything this domain knew
    last time (`ugm.save`), and reconciling that is this
    function's job -- nothing in the harness can tell a restored entity
    from a fresh one. The policy here: every folder and entry stays
    exactly as it was, and the `Session` is REPLACED, because the clock
    and the working directory belong to the process now running and not
    to the one that wrote the file. `attach` on the entity that already
    carries one is the whole of that -- same entity, new component.

    ⚠ This function, unlike every system above it, calls `world.spawn`
    and `world.attach` directly -- and correctly. It runs once, before
    the loop is running at all, not on every tick over a query; there is
    no "turn" for it to return deltas from, only a world to seed.
    """
    for system in SYSTEMS:
        loop.system(system)
    world = loop.world
    world.learn(*WORDS, "y", "yes", "n", "no")
    was = world.first(Session)
    world.attach(was[0] if was else world.spawn(),
                 Session(cwd(), int(clock()), BIG_BYTES))
