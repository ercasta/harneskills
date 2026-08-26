"""The filesystem domain: what a person's words mean, and what to do about it.

    python -m harneskills harneskills.examples.fs:install

Eleven systems over `model.py`'s components and `fs_tools.py`'s three
tools. Read top to bottom, they are the order they run in each tick, and
that order is the whole of the plan::

    hear            Said              -> a goal entity
    list_dir        ListWanted        -> the tools, and Listed
    reply_listing   Listed            -> one line per entry, then a count
    approve         RenameWish+NeedsApproval  -> asks you, then detaches the tag
    flag_stale      StaleHunt         -> Stale on every old entry, FoundStale
    propose_rename  FoundStale        -> RenameWish + NeedsApproval  NEVER a rename
    do_rename       RenameWish (without NeedsApproval)  -> the tool
    focus_big       HuntHere          -> BigHunt, aimed at the folder you mean
    flag_big        BigHunt           -> Big on every large entry, FoundBig
    reply_big / reply_renamed / reply_failed        -> what you are told

`approve` sits ABOVE the system that proposes, which reads like a mistake
and is not: a proposal made this tick is therefore asked about on the NEXT
one, which is what puts "2 of 5 older than 7 day(s)" on screen before the
prompt asking what to do about the first of them. System order is the
schedule, and a tick boundary is the only thing there is to schedule
against.

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
and approving is `w.detach(entity, NeedsApproval)` -- the same wish, no
longer waiting. Wanting your own renames held too is one more `attach`,
not a different design.

## A system loops, so a guard is rarely needed

`flag_big` walks every entry in the folder in a `for`, in one call, and
destroys the goal entity that let it run. It cannot fire twice on the same
goal because the goal is gone, so there is no per-file bookkeeping to
write, and none to get wrong.
"""

from __future__ import annotations

import os
import time

from ..world import Reply, Said
from . import fs_tools
from .model import (Big, BigHunt, Contents, Entry, Failed, Focus, Folder,
                    FoundBig, FoundStale, HuntHere, IsDir, ListWanted, Listed,
                    Modified, NeedsApproval, RenameWish, Renamed, Session,
                    Size, Stale, StaleHunt)

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
    """The entity for this directory -- the one that already exists, or a
    new one. The only place a `Folder` is made, so two systems asking
    about the same directory are asking about the same entity."""
    for entity, folder in w.each(Folder):
        if folder.path == path:
            return entity
    return w.spawn(Folder(path), Contents())


def here(w):
    """The folder the conversation is about: the one you last looked at,
    or the one the session started in."""
    focused = w.first(Folder, Focus)
    if focused is not None:
        return focused[0]
    return folder_at(w, w.the(Session).cwd)


def _focus(w, folder) -> None:
    """You are looking at this folder now, and at no other."""
    for entity, _ in w.each(Focus):
        w.detach(entity, Focus)
    w.attach(folder, Focus())


def _listed(w, folder) -> None:
    """Make sure the world has actually looked at this folder. A question
    about a folder nobody listed is a question about nothing, and
    answering `0 files` would be a lie about the disk rather than a fact
    about it."""
    if not w.get(folder, Contents).by_name:
        fs_tools.ls(w, folder)


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


def _say(w, text: str) -> None:
    w.spawn(Reply("user", text))


# -- what a typed line means ---------------------------------------------

def _path(text: str) -> str:
    """A path as a person types one: quoted if it needs to be, `~` if they
    like, and the rest of the line taken whole so a space is nothing
    special."""
    return os.path.expanduser(text.strip().strip('"').strip("'"))


def _understand(w, line: str) -> bool:
    """Spawn the goal this line asks for. False if this domain has no
    reading of it -- plain Python over plain words, no grammar and no
    parser, and every case here is one a person actually types."""
    words = line.split()
    low = [word.lower() for word in words]
    if not words:
        return False

    if low[0] == "show" and len(words) >= 2:
        rest = words[2:]
        where = _path(" ".join(rest[1:])) if low[2:3] == ["in"] and rest[1:] else None
        if low[1] in ("file", "files"):
            w.spawn(ListWanted(folder_at(w, where or w.the(Session).cwd)))
            return True
        if low[1] == "big":
            if where is None:
                w.spawn(HuntHere())
            else:
                w.spawn(BigHunt(folder_at(w, where)))
            return True

    if low[0] == "stale" and "after" in low:
        at = low.index("after")
        days = low[at + 1] if low[at + 1:at + 2] and low[at + 1].isdigit() else None
        # `stale in DIR after N days` -- everything between `in` and
        # `after` is the folder; `stale after N days` means where you are.
        where = _path(" ".join(words[2:at])) if low[1:2] == ["in"] and at > 2 else None
        if days is not None:
            folder = folder_at(w, where) if where else here(w)
            w.spawn(StaleHunt(folder, int(days)))
            return True

    if low[0] == "rename" and "to" in low:
        at = low.index("to")
        old, new = " ".join(words[1:at]), " ".join(words[at + 1:])
        folder = here(w)
        _listed(w, folder)
        by_name = w.get(folder, Contents).by_name
        if old and new and old in by_name:
            # No `NeedsApproval`: you are not an automation, and nothing
            # holds what you asked for yourself.
            w.spawn(RenameWish(by_name[old], new))
            return True
        if old and new:
            w.spawn(Failed("rename %s" % old, "no such file here"))
            return True
    return False


# -- the systems ----------------------------------------------------------

def hear(w):
    """What you typed -> a goal, if this domain has a reading of it."""
    for entity, said in w.each(Said):
        if said.channel == "user" and _understand(w, said.text):
            w.destroy(entity)
        # Left standing otherwise: the prompt says nobody understood it.


def list_dir(w):
    """ListWanted -> the `ls` tool, and the folder you are now in."""
    for entity, want in w.each(ListWanted):
        w.destroy(entity)
        count = fs_tools.ls(w, want.folder)
        if count is None:
            continue   # `Failed` is already spawned; reply_failed says it
        _focus(w, want.folder)
        w.spawn(Listed(want.folder, count))


def reply_listing(w):
    """One line per entry, then the count -- in that order, because this
    system spawns them in that order and nothing reorders replies."""
    for entity, listed in w.each(Listed):
        w.destroy(entity)
        for child in _entries(w, listed.folder):
            _say(w, _describe(w, child))
        _say(w, "%d item(s) in %s"
             % (listed.count, w.get(listed.folder, Folder).path))


def flag_stale(w):
    """StaleHunt -> `Stale` on every entry older than it asked about."""
    for entity, hunt in w.each(StaleHunt):
        w.destroy(entity)
        _listed(w, hunt.folder)
        now, found, children = w.the(Session).now, 0, _entries(w, hunt.folder)
        for child in children:
            written = w.get(child, Modified)
            if written is None or w.has(child, IsDir):
                continue
            if (now - written.when) // DAY >= hunt.days:
                w.attach(child, Stale())
                w.spawn(FoundStale(child))
                found += 1
        _say(w, "%d of %d older than %d day(s) in %s"
             % (found, len(children), hunt.days,
                w.get(hunt.folder, Folder).path))


def propose_rename(w):
    """FoundStale -> a PROPOSAL to rename it. The compounding step: a
    finding becomes a plan, and a plan is not an act."""
    for entity, found in w.each(FoundStale):
        w.destroy(entity)
        entry = w.get(found.entry, Entry)
        if entry is None or entry.name.startswith(STALE_PREFIX):
            continue   # already carries the mark; renaming it again is noise
        w.spawn(RenameWish(found.entry, STALE_PREFIX + entry.name),
                NeedsApproval())


def do_rename(w):
    """A wish nobody is waiting on -> the tool. Reached by an approval
    detaching the tag, or straight from a person typing `rename a to b`,
    and this system cannot tell which -- which is the point: holding is
    the proposer's business, not the act's."""
    for entity, wish in w.each(RenameWish, without=NeedsApproval):
        w.destroy(entity)
        if fs_tools.rename(w, wish.entry, wish.new_name):
            w.detach(wish.entry, Stale)   # dealt with: the claim is unmade


def focus_big(w):
    """HuntHere -> the same entity, now a BigHunt aimed at the folder you
    last looked at."""
    for entity, _ in w.each(HuntHere):
        w.detach(entity, HuntHere)
        w.attach(entity, BigHunt(here(w)))


def flag_big(w):
    """BigHunt -> `Big` on every entry over the session's floor. One call,
    one `for`, no per-file bookkeeping."""
    for entity, hunt in w.each(BigHunt):
        w.destroy(entity)
        _listed(w, hunt.folder)
        floor, found = w.the(Session).big_floor, 0
        for child in _entries(w, hunt.folder):
            size = w.get(child, Size)
            if size is None or w.has(child, IsDir) or size.bytes < floor:
                continue
            w.attach(child, Big())
            w.spawn(FoundBig(child))
            found += 1
        if not found:
            _say(w, "nothing over %d bytes in %s"
                 % (floor, w.get(hunt.folder, Folder).path))


# -- what you are told ----------------------------------------------------
# Every system above decides what HAPPENED. These decide what a person
# reading the prompt hears about it, and they are the ones to edit for a
# quieter or louder session -- nothing above this line prints anything.

def reply_big(w):
    for entity, found in w.each(FoundBig):
        w.destroy(entity)
        _say(w, _describe(w, found.entry))


def reply_renamed(w):
    for entity, renamed in w.each(Renamed):
        w.destroy(entity)
        _say(w, "renamed %s -> %s" % (renamed.was, w.get(renamed.entry, Entry).name))


def reply_failed(w):
    for entity, failed in w.each(Failed):
        w.destroy(entity)
        _say(w, "! could not %s: %s" % (failed.what, failed.why))


# -- installing -----------------------------------------------------------

def _approver(ask):
    """`approve(w)`, asking at the terminal. A closure because the question
    has to be askable some other way in a test -- `install(loop, ask=...)`
    -- and because nothing else in this module needs to know there is a
    terminal at all."""
    def approve(w):
        """A held wish -> asks you, and the answer is a component.

        ONE question per tick, however many are waiting: what happened to
        the last answer is drained before the next question is asked, so a
        run of prompts reads as a conversation rather than as a stack of
        questions followed by a stack of outcomes.
        """
        held = w.first(RenameWish, NeedsApproval)
        if held is None:
            return
        # `each`/`first` hand back the entity and then EVERY component
        # asked for, in order -- the tag included, even though asking for
        # it was the whole of what it had to say.
        entity, wish, _ = held
        entry = w.get(wish.entry, Entry)
        folder = w.get(entry.folder, Folder).path
        said = ask("approve rename %s -> %s in %s? [y/N] "
                   % (entry.name, wish.new_name, folder))
        if said.strip().lower() in ("y", "yes"):
            # The same wish, no longer waiting. `do_rename` asks for
            # exactly this and will pick it up in the same tick.
            w.detach(entity, NeedsApproval)
        else:
            w.destroy(entity)
            _say(w, "left %s alone" % entry.name)
    return approve


SYSTEMS = (hear, list_dir, reply_listing,
           None,   # `approve` goes here -- it needs `ask`, built per install
           flag_stale, propose_rename, do_rename, focus_big, flag_big,
           reply_big, reply_renamed, reply_failed)


def install(loop, ask=input, clock=time.time, cwd=os.getcwd) -> None:
    """Every system, in order, plus the one `Session` they read.

    `clock` and `cwd` are arguments because a domain that reads the world
    outside the world should say where it does it. Both are read ONCE,
    here -- see `model.Session`.
    """
    for system in SYSTEMS:
        loop.system(_approver(ask) if system is None else system)
    loop.world.learn(*WORDS)
    loop.world.spawn(Session(cwd(), int(clock()), BIG_BYTES))
