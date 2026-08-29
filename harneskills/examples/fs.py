"""The filesystem domain: what a person's words mean, and what to do about it.

    python -m harneskills harneskills.examples.fs:install

Eighteen rules over `model.py`'s components and `fs_tools.py`'s three
tools. Read top to bottom, they are the order they run in each tick, and
that order is the whole of the plan::

    hear                Said                        -> a ParseRequest, once
    hear_answer         Said ("y"/"n")              -> resolves the wish being Asked
    propose_*           ParseRequest                -> a candidate: Proposal + a goal
    arbitrate_parse      ParseRequest + Proposal(s)  -> one goal, real; the rest, gone
    list_dir            ListWanted                  -> the tools, and Listed
    reply_listing       Listed                      -> one line per entry, then a count
    approve             RenameWish+NeedsApproval, not yet Asked  -> a question
    flag_stale          StaleHunt                   -> Stale on every old entry, FoundStale
    propose_rename      FoundStale                  -> RenameWish + NeedsApproval  NEVER a rename
    do_rename           RenameWish (without NeedsApproval)  -> the tool
    focus_big           HuntHere                    -> BigHunt, aimed at the folder you mean
    flag_big            BigHunt                     -> Big on every large entry, FoundBig
    reply_big / reply_renamed / reply_failed         -> what you are told

`approve` sits ABOVE the rule that proposes, which reads like a mistake
and is not: a proposal made this tick is therefore asked about on the NEXT
one, which is what puts "2 of 5 older than 7 day(s)" on screen before the
question about the first of them. Rule order is the schedule, and a
tick boundary is the only thing there is to schedule against.

## Understanding a line is the SAME propose/arbitrate/act shape, one level up

What used to be one `_understand` function -- try each reading in turn,
return on the first match -- is now four small `propose_*` rules and one
`arbitrate_parse`, the general pattern from `docs/intake processing.md`
applied to this domain's own input: `hear` turns a `Said` into a
`ParseRequest` (the occasion); every `propose_*` rule gets a look at it
and may spawn a CANDIDATE -- an entity tagged `Proposal` carrying
whichever goal it thinks the line asked for (`ListWanted`, `StaleHunt`,
`RenameWish`, even a `Failed` for "recognized, but factually wrong");
`arbitrate_parse` picks one winner and destroys the rest, in the SAME
tick, because rule order already puts every `propose_*` rule ahead of it
in the list above.

The arbiter itself is the trivial rule the pattern doc asks for: first
proposal registered wins. These four `propose_*` rules never actually
collide -- each recognizes a disjoint shape of line -- so nothing here
has needed more than that yet. The day two of them legitimately
compete for the same line, THAT is what grows real judge machinery
(a priority, a real ranking) -- not before.

Every rule here writes to the world directly -- `w.spawn`, `w.attach`,
`w.detach`, `w.destroy` -- and `Loop.tick` calls one rule fully before the
next, so a write it makes is already there for the next rule in the SAME
tick to see: `list_dir` making a folder's listing real happens before
`reply_listing` runs, in the same tick, because that write already
happened by the time `list_dir` returns.

## The compounding step is `propose_rename`, and it is one line

Finding a stale file attaches `Stale`. Deciding what to DO about a stale
file is a different rule, and what it spawns is a WISH carrying
`NeedsApproval` -- not a rename. A domain that wanted to archive instead
of rename changes that rule and nothing else: the tools, the listing,
the approval prompt and every reply stay exactly as they are.

## Approval is a component, not a feature

`propose_rename` attaches `NeedsApproval` because an automation proposed
it. Typing `rename a to b` yourself spawns the same `RenameWish` WITHOUT
the tag, and `do_rename` asks for exactly that::

    w.each(RenameWish, without=NeedsApproval)

So nothing holds your own renames, one rule asks about everything held,
and approving is `detach(entity, NeedsApproval)` -- the same wish, no
longer waiting. Wanting your own renames held too is one more `attach`,
not a different design. This is what "proposed" means in this domain --
an entity, sitting there to be queried, approved, or left alone -- not a
lower-level notion the engine has to know about.

Asking is a component too. `approve` cannot call a function and wait for
your answer -- the world may have other channels attached, and nothing
here is allowed to stop for one of them (see `ugm.engine`) -- so
it spawns the question as an ordinary `Reply` and marks the wish `Asked`.
`hear_answer` is the other half: a bare "y" or "n", on whichever channel
it arrives, resolves whichever wish is currently `Asked`. The suspension
IS the state; there is no callback held anywhere waiting to be called.

## A rule loops, so a guard is rarely needed

`flag_big` walks every entry in the folder in a `for`, in one call, and
destroys the goal entity that let it run. It cannot fire twice on the same
goal because the goal is gone, so there is no per-file bookkeeping to
write, and none to get wrong.
"""

from __future__ import annotations

import os
import time

from ugm.world import Reply, Said

from . import fs_tools
from .model import (Asked, Big, BigHunt, Contents, Entry, Failed, Focus,
                    Folder, FoundBig, FoundStale, HuntHere, IsDir,
                    ListWanted, Listed, Modified, NeedsApproval, Parsing,
                    ParseRequest, Proposal, RenameWish, Renamed, Session,
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
    r"""The entity for this directory: the one that already exists, or a
    fresh one this call spawns. The only place a `Folder` is spawned, so
    two rules asking about the same directory -- even in the same call --
    are asking about the same entity.

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
            return entity
    return w.spawn(Folder(path), Contents())


def here(w):
    """The folder the conversation is about: the one you last looked at,
    or the one the session started in."""
    focused = w.first(Folder, Focus)
    if focused is not None:
        return focused[0]
    return folder_at(w, w.the(Session).cwd)


def _known_here(w):
    """The folder the conversation is about, IF the world already has
    one -- `None` otherwise, and nothing is spawned to find out.

    What `_understand`'s rename branch needs: it must read `Contents`
    back THIS SAME CALL to look a name up, which only an already-real
    folder has. A folder nobody has listed answers every name the same
    way `here`/`folder_at` spawning one fresh would -- an empty
    `Contents` -- so there is nothing to spawn only to find that out.
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
    for e, _ in w.each(Focus):
        w.detach(e, Focus)
    w.attach(folder, Focus())


def _listed(w, folder):
    """`entries` as `(entity, name, size, modified, is_dir)`, either read
    straight off the world (already listed) or freshly found by
    `fs_tools.ls` THIS TURN if nobody had looked yet.

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
        return entries
    entries, _count = fs_tools.ls(w, folder)
    return entries


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
    special.

    Absolute on the way out, because `folder_at` compares what comes out
    of here and two spellings of one directory must not become two
    folders: `notes`, `./notes`, `notes/` and `/home/you/notes` are one
    place, each with its own `Contents` to fill and its own `Focus` to
    fight over if they are not.
    """
    return os.path.abspath(os.path.expanduser(text.strip().strip('"').strip("'")))


def _split(text: str):
    """`(words, low)` for one line of a `ParseRequest`, or `None` for a
    blank one -- shared by every `propose_*` rule below so each says only
    what ITS shape looks like, never how to tokenize one."""
    words = text.split()
    if not words:
        return None
    return words, [word.lower() for word in words]


# -- the rules ----------------------------------------------------------

def hear(w):
    """What you typed -> a `ParseRequest`, once. What it MEANS is every
    `propose_*` rule's business below, not this one's -- see this
    module's docstring, "Understanding a line is the SAME
    propose/arbitrate/act shape."

    `without=Parsing` is load-bearing: without it this rule would spawn a
    fresh request for the same unclaimed line every tick it sits there,
    and the loop would never settle.

    Any channel -- `said.channel` is whichever terminal or socket a person
    is attached as (`ugm.engine`'s own concern), and `"user"` is
    not one of those any more, it is where a reply meant for everyone
    goes. This domain does not (yet) answer only the one who asked; every
    reply it makes is `Reply("user", ...)`, heard by whoever is
    connected, which is the ordinary MUD answer for a world nobody has
    taught to whisper.
    """
    for entity, said in w.each(Said, without=Parsing):
        w.attach(entity, Parsing())
        w.spawn(ParseRequest(entity, said.text))


def hear_answer(w):
    """A bare yes/no -> the wish now waiting on an answer, if there is one.

    Runs before `approve` asks about anything else, so at most one wish is
    ever waiting -- see `Asked`. A "y" or "n" that arrives with nothing
    outstanding is not this domain's business and is left for `hear` to
    try as everything else it might mean (which, being one letter, is
    nothing -- and it is reported unheard, same as any other line no
    rule claims).
    """
    held = w.first(RenameWish, NeedsApproval, Asked)
    if held is None:
        return
    entity, wish, _, _ = held
    for said_entity, said in w.each(Said):
        answer = said.text.strip().lower()
        if answer not in ("y", "yes", "n", "no"):
            continue
        entry = w.get(wish.entry, Entry)
        w.destroy(said_entity)
        if answer in ("y", "yes"):
            # The same wish, no longer waiting. `do_rename` asks for
            # exactly this and will pick it up this same tick.
            w.detach(entity, NeedsApproval)
            w.detach(entity, Asked)
        else:
            w.destroy(entity)
            _say(w, "left %s alone" % entry.name)
        return


def propose_list(w):
    """`show file(s) [in DIR]` -> a candidate carrying `ListWanted`."""
    for request, req in w.each(ParseRequest):
        split = _split(req.text)
        if split is None:
            continue
        words, low = split
        if low[0] != "show" or len(words) < 2 or low[1] not in ("file", "files"):
            continue
        rest = words[2:]
        where = _path(" ".join(rest[1:])) if low[2:3] == ["in"] and rest[1:] else None
        folder = folder_at(w, where or w.the(Session).cwd)
        w.spawn(Proposal(request), ListWanted(folder))


def propose_big(w):
    """`show big [in DIR]` -> a candidate carrying `HuntHere` (the folder
    is decided later, by `focus_big`) or `BigHunt`."""
    for request, req in w.each(ParseRequest):
        split = _split(req.text)
        if split is None:
            continue
        words, low = split
        if low[0] != "show" or len(words) < 2 or low[1] != "big":
            continue
        rest = words[2:]
        where = _path(" ".join(rest[1:])) if low[2:3] == ["in"] and rest[1:] else None
        if where is None:
            w.spawn(Proposal(request), HuntHere())
        else:
            w.spawn(Proposal(request), BigHunt(folder_at(w, where)))


def propose_stale(w):
    """`stale [in DIR] after N days` -> a candidate carrying `StaleHunt`."""
    for request, req in w.each(ParseRequest):
        split = _split(req.text)
        if split is None:
            continue
        words, low = split
        if low[0] != "stale" or "after" not in low:
            continue
        at = low.index("after")
        days = low[at + 1] if low[at + 1:at + 2] and low[at + 1].isdigit() else None
        if days is None:
            continue
        # `stale in DIR after N days` -- everything between `in` and
        # `after` is the folder; `stale after N days` means where you are.
        where = _path(" ".join(words[2:at])) if low[1:2] == ["in"] and at > 2 else None
        folder = folder_at(w, where) if where else here(w)
        w.spawn(Proposal(request), StaleHunt(folder, int(days)))


def propose_typed_rename(w):
    """`rename OLD to NEW` -> a candidate carrying `RenameWish` if OLD
    exists, `Failed` if it doesn't -- recognized either way. Not to be
    confused with `propose_rename` below, the AUTOMATED one that turns a
    `FoundStale` into a held wish: that one never competes for a
    `ParseRequest` and is no part of this arbitration.
    """
    for request, req in w.each(ParseRequest):
        split = _split(req.text)
        if split is None:
            continue
        words, low = split
        if low[0] != "rename" or "to" not in low:
            continue
        at = low.index("to")
        old, new = " ".join(words[1:at]), " ".join(words[at + 1:])
        if not old or not new:
            continue
        folder = _known_here(w)
        by_name = w.get(folder, Contents).by_name if folder is not None else {}
        if old in by_name:
            # No `NeedsApproval`: you are not an automation, and nothing
            # holds what you asked for yourself.
            w.spawn(Proposal(request), RenameWish(by_name[old], new))
        else:
            w.spawn(Proposal(request), Failed("rename %s" % old, "no such file here"))


def arbitrate_parse(w):
    """One winner per `ParseRequest` -- first candidate registered wins,
    every other candidate for the same request is destroyed outright.

    This IS the arbiter from `docs/intake processing.md`, kept exactly as
    trivial as this domain has ever needed: the four `propose_*` rules
    above recognize disjoint shapes of line, so real rivalry has never
    actually happened here. A domain that hits real rivalry grows a
    real judge (a priority field, `ranked`-style scoring -- see
    `engine/DECISION_PATTERNS.md`) at THAT rule, not here; "first wins"
    stays correct for every occasion nobody has taught to compete yet.

    A request with no candidates at all is destroyed too, quietly --
    nobody proposed a reading, so its `Said` is left exactly as it was,
    to be reported unheard once the world settles (`ugm.engine.drain`).
    """
    for request, req in w.each(ParseRequest):
        candidates = [entity for entity, proposal in w.each(Proposal)
                     if proposal.request == request.id]
        if not candidates:
            w.destroy(request)
            continue
        winner, *losers = candidates
        for loser in losers:
            w.destroy(loser)
        w.detach(winner, Proposal)
        w.destroy(request)
        w.destroy(req.said)


def list_dir(w):
    """ListWanted -> the `ls` tool, and the folder you are now in."""
    for entity, want in w.each(ListWanted, without=Proposal):
        w.destroy(entity)
        _entries, count = fs_tools.ls(w, want.folder)
        if count is None:
            continue   # `Failed` already spawned; reply_failed says it
        _focus(w, want.folder)
        w.spawn(Listed(want.folder, count))


def reply_listing(w):
    """One line per entry, then the count -- in that order, because this
    rule says them in that order and nothing reorders replies."""
    for entity, listed in w.each(Listed):
        w.destroy(entity)
        for child in _entries(w, listed.folder):
            _say(w, _describe(w, child))
        _say(w, "%d item(s) in %s"
            % (listed.count, w.get(listed.folder, Folder).path))


def flag_stale(w):
    """StaleHunt -> `Stale` on every entry older than it asked about."""
    for entity, hunt in w.each(StaleHunt, without=Proposal):
        w.destroy(entity)
        entries = _listed(w, hunt.folder)
        now, found = w.the(Session).now, 0
        for child, _name, _size, modified, is_dir in entries:
            if modified is None or is_dir:
                continue
            if (now - modified) // DAY >= hunt.days:
                w.attach(child, Stale())
                w.spawn(FoundStale(child))
                found += 1
        _say(w, "%d of %d older than %d day(s) in %s"
            % (found, len(entries), hunt.days, w.get(hunt.folder, Folder).path))


def propose_rename(w):
    """FoundStale -> a PROPOSAL to rename it. The compounding step: a
    finding becomes a plan, and a plan is not an act."""
    for entity, found in w.each(FoundStale):
        w.destroy(entity)
        entry = w.get(found.entry, Entry)
        if entry is None or entry.name.startswith(STALE_PREFIX):
            continue   # already carries the mark; renaming it again is noise
        w.spawn(RenameWish(found.entry, STALE_PREFIX + entry.name), NeedsApproval())


def do_rename(w):
    """A wish nobody is waiting on -> the tool. Reached by an approval
    detaching the tag, or straight from a person typing `rename a to b`,
    and this rule cannot tell which -- which is the point: holding is
    the proposer's business, not the act's."""
    for entity, wish in w.each(RenameWish, without=(NeedsApproval, Proposal)):
        w.destroy(entity)
        if fs_tools.rename(w, wish.entry, wish.new_name):
            w.detach(wish.entry, Stale)   # dealt with: the claim is unmade


def focus_big(w):
    """HuntHere -> the same entity, now a BigHunt aimed at the folder you
    last looked at."""
    for entity, _tag in w.each(HuntHere, without=Proposal):
        w.detach(entity, HuntHere)
        w.attach(entity, BigHunt(here(w)))


def flag_big(w):
    """BigHunt -> `Big` on every entry over the session's floor. One call,
    one `for`, no per-file bookkeeping."""
    for entity, hunt in w.each(BigHunt, without=Proposal):
        w.destroy(entity)
        entries = _listed(w, hunt.folder)
        floor, found = w.the(Session).big_floor, 0
        for child, _name, size, _modified, is_dir in entries:
            if size is None or is_dir or size < floor:
                continue
            w.attach(child, Big())
            w.spawn(FoundBig(child))
            found += 1
        if not found:
            _say(w, "nothing over %d bytes in %s"
                % (floor, w.get(hunt.folder, Folder).path))


# -- what you are told ----------------------------------------------------
# Every rule above decides what HAPPENED. These decide what a person
# reading the prompt hears about it, and they are the ones to edit for a
# quieter or louder session -- nothing above this line spawns a reply.

def reply_big(w):
    for entity, found in w.each(FoundBig):
        w.destroy(entity)
        _say(w, _describe(w, found.entry))


def reply_renamed(w):
    for entity, renamed in w.each(Renamed):
        w.destroy(entity)
        _say(w, "renamed %s -> %s" % (renamed.was, w.get(renamed.entry, Entry).name))


def reply_failed(w):
    for entity, failed in w.each(Failed, without=Proposal):
        w.destroy(entity)
        _say(w, "! could not %s: %s" % (failed.what, failed.why))


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
    a rule does may stop the world for everyone else. The fix is not a
    trick, it is the thing this whole domain already does for every other
    goal -- suspend as a component (`Asked`), and let the answer arrive as
    an ordinary line whenever it does.
    """
    if w.first(RenameWish, NeedsApproval, Asked) is not None:
        return   # a question is already outstanding; wait for its answer
    held = w.first(RenameWish, NeedsApproval, without=Asked)
    if held is None:
        return
    entity, wish, _tag = held
    entry = w.get(wish.entry, Entry)
    folder = w.get(entry.folder, Folder).path
    w.attach(entity, Asked())
    _say(w, "approve rename %s -> %s in %s? [y/n]" % (entry.name, wish.new_name, folder))


RULES = (hear, hear_answer,
           propose_list, propose_big, propose_stale, propose_typed_rename,
           arbitrate_parse,
           list_dir, reply_listing, approve,
           flag_stale, propose_rename, do_rename, focus_big, flag_big,
           reply_big, reply_renamed, reply_failed)


def install(loop, clock=time.time, cwd=os.getcwd) -> None:
    """Every rule, in order, plus the one `Session` they read.

    `clock` and `cwd` are arguments because a domain that reads the world
    outside the world should say where it does it. Both are read ONCE,
    here -- see `model.Session`.

    ⚠ The world handed in may already hold everything this domain knew
    last time (`ugm.save`), and reconciling that is this
    function's job -- nothing in the harness can tell a restored entity
    from a fresh one. The policy here: every folder and entry stays
    exactly as it was, and the `Session` is REPLACED, because the clock
    and the working directory belong to the process now running and not
    to the one that wrote the file. `world.replace` on the entity that
    already carries one is the whole of that -- same entity, new
    component, and the OLD one gone rather than standing alongside it
    (`Session` is not a kind an entity should ever carry two of).

    This function runs once, before the loop is running at all -- there
    is no tick for it to be a rule's own turn in, only a world to seed.
    """
    for rule in RULES:
        loop.rule(rule)
    world = loop.world
    world.learn(*WORDS, "y", "yes", "n", "no")
    was = world.first(Session)
    world.replace(was[0] if was else world.spawn(),
                  Session(cwd(), int(clock()), BIG_BYTES))
