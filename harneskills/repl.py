"""A prompt: take a line, put it in the world, run the loop, print what
the world says back.

    harneskills> show file
    fs_demo.py (4096 bytes)
    ...
    12 item(s) in /home/you/notes

Everything between the second line and the third is `harneskills.loop`
calling systems -- Python functions over the entities and components in
`harneskills.world` -- until nothing changes. This module is the door: it
does not know what a directory is, what `show` means, or that `fs`
exists.

## Typing at this prompt is SAYING something, not authoring

A line becomes one entity carrying one component -- `Said(user, "show
file")` -- and that is all the REPL does with it. Whether those words
mean anything is a question for the systems a domain installed, and a
line nobody destroyed is a line nothing understood: it is still there
when the world settles, and the prompt says so (`(nothing understood:
...)`) rather than pretending.

There is no way to author a system at this prompt, and no mode that would
let you: a system is a Python function, so writing one means editing a
module and `/reload`ing. What you get back for that is a system that can
loop, branch, call a library and read a clock.

## The world outlives the process, and this loop is where it is written

Nothing here opens a file. `on_settle(loop)` is called every time the
world stops moving and everything it had to say has been printed -- the
one moment there is a consistent world to write down -- and what the
caller does with that is the caller's business
(`harneskills.__main__` hands it to `harneskills.save`). Writing on every
settle rather than on the way out is deliberate: a prompt living in a
service is killed, not quit, and a save that only ran at `/quit` would be
a save that never ran.

## The output is a channel, and a reply is the only thing printed unasked

Nothing about the world's state reaches the terminal on its own. A domain
that wants to say something spawns `Reply(user, "...")`, and this loop
prints exactly that text -- one line, no decoration -- and then destroys
the entity, because a thing said is over and saying it again is a new
act. A reply to any other channel is prefixed (`[gauge] ...`). `/show` is
the whole world, on demand, any time.

## Autocorrect is against the DOMAIN's vocabulary, and stops at a path

A domain calls `world.learn("show", "file", "big", ...)` for the words it
expects, and a typed word close to exactly ONE of them is corrected and
echoed (`~ fiel -> file`), never silently. Close means `_max_edits` --
one edit for a short word, two for a long one, with a swapped pair
counting as one -- and exactly one means a tie is left alone, because a
word equally near two known words is a word this prompt cannot read.

Correction stops at the first span that looks like a path (a `/`, a `.`,
a `~`, or a quoted span) and never resumes: `show file in /etc/rc.d` must
reach the rules with `rc.d` intact, and a folder called `Documnets` is
not a typo this prompt is entitled to have an opinion about.
"""

from __future__ import annotations

import re
import sys
from typing import Optional, TextIO

from .world import Reply, Said

# A quoted span, taken whole and never corrected, or a run of non-space.
_SPAN = re.compile(r'"[^"]*"|\S+')
# What makes a span a path rather than a word: a separator, an extension,
# a home dir, or quotes someone put there on purpose.
_PATHISH = re.compile(r'[/\\~"]|\.\w')

HELP = """\
/show      every entity in the world right now, and what it carries
/systems   the systems installed, in the order they run each tick
/quit      leave

Type what you want in words -- `show file`, `show file in /tmp`, `show
big`. A line becomes `Said(user, "...")` and means whatever the installed
domains' systems make of it; a line nobody claims is reported, not
guessed at. Only a reply is printed unasked. A misspelled word is
corrected against the vocabulary a domain registered, and echoed (`~ fiel
-> file`); a path, and everything after it on the line, is left exactly
as typed.
"""


def _distance(a: str, b: str) -> int:
    """Edits from `a` to `b`, counting a SWAPPED PAIR as one.

    Plain Levenshtein calls `shwo -> show` two edits, the same as `for ->
    to`, and a threshold loose enough for the first is loose enough for
    the second. Two adjacent keys hit in the wrong order is the single
    commonest way to mistype a word anyone knows how to spell; it is not
    two mistakes and should not be priced as two.
    """
    if a == b:
        return 0
    rows = [[0] * (len(b) + 1) for _ in range(len(a) + 1)]
    for i in range(len(a) + 1):
        rows[i][0] = i
    for j in range(len(b) + 1):
        rows[0][j] = j
    for i in range(1, len(a) + 1):
        for j in range(1, len(b) + 1):
            cost = a[i - 1] != b[j - 1]
            rows[i][j] = min(rows[i - 1][j] + 1, rows[i][j - 1] + 1,
                             rows[i - 1][j - 1] + cost)
            if i > 1 and j > 1 and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]:
                rows[i][j] = min(rows[i][j], rows[i - 2][j - 2] + 1)
    return rows[-1][-1]


def _max_edits(word: str) -> int:
    """How wrong a word of this length may be and still be a typo.

    Two edits into a three-letter word is not a typo, it is a different
    word -- `for` is two from `to`, and correcting it turns "what is for
    dinner" into a sentence nobody typed. Longer words have room to be
    wrong in: `Documnets` is unmistakable at two.
    """
    return 1 if len(word) <= 4 else 2


def _autocorrect(line: str, vocab: "set[str]"):
    """`(corrected_line, [(typed, fixed), ...])` -- see the module
    docstring. Spacing is preserved exactly: spans are spliced back into
    the original text rather than rejoined."""
    corrections, out, last, stop = [], [], 0, False
    for match in _SPAN.finditer(line):
        text = match.group()
        out.append(line[last:match.start()])
        last = match.end()
        if _PATHISH.search(text):
            stop = True   # a path, and everything after it, is left alone
        if stop or len(text) <= 2 or text in vocab or text.isdigit():
            out.append(text)
            continue
        limit = _max_edits(text)
        best, best_dist, ties = None, limit + 1, 0
        for word in vocab:
            d = _distance(text, word)
            if d < best_dist:
                best, best_dist, ties = word, d, 1
            elif d == best_dist:
                ties += 1
        if best is not None and best_dist <= limit and ties == 1:
            out.append(best)
            corrections.append((text, best))
        else:
            out.append(text)
    out.append(line[last:])
    return "".join(out), corrections


def _drain(loop, said: bool = True) -> None:
    """Everything the world has to say since the last time we asked, in the
    order it was said: replies first, then whatever blew up, then the lines
    nobody claimed.

    `said=False` between ticks -- a line no system has claimed YET is not a
    line nobody understood; only a settled world can say that.
    """
    w = loop.world
    for entity, reply in w.each(Reply):
        w.destroy(entity)
        print(reply.text if reply.channel == "user"
              else "[%s] %s" % (reply.channel, reply.text))
    for name, err in loop.errors:
        print("  ! %s: %s: %s" % (name, type(err).__name__, err))
    loop.errors.clear()
    if said:
        for entity, heard in w.each(Said):
            w.destroy(entity)
            print("  (nothing understood: %s)" % heard.text)


def run(loop, prompt: str = "harneskills", stdin: Optional[TextIO] = None,
        echo_prompt: bool = True, commands=None, on_settle=None) -> int:
    """`commands` is `{"/name": fn}`, the one seam this loop has for a
    caller that knows something it does not. `fn(argument_text)` may return
    None -- it handled itself -- or a fresh `Loop` to carry on with, which
    is how `/reload` exists: re-importing an edited domain means building
    the world again from nothing, and only this loop can swap the one it is
    holding. Each fn's first docstring line is its help text.

    `on_settle(loop)` is called every time the world stops moving and
    everything it had to say has been printed -- the moment there is a
    consistent world to write down, which is what `harneskills.save` is
    handed. It is called with the loop rather than closing over one
    because `/reload` swaps it.
    """
    stdin = stdin or sys.stdin
    extra = "".join(
        "%-10s %s\n" % (name, ((fn.__doc__ or "").strip().splitlines() or [""])[0])
        for name, fn in (commands or {}).items())
    print(HELP.replace("/quit      leave\n", extra + "/quit      leave\n", 1))

    def settle() -> None:
        # `_drain` after every tick, not just at the end: a rule that stops
        # to ask you something (`fs`'s approval prompt) must not do it over
        # the top of replies the same tick already produced.
        ticks, hot = loop.run(after_tick=lambda: _drain(loop, said=False))
        _drain(loop)
        if hot:
            # The budget ran out with systems still firing -- almost always
            # two feeding each other. Name them: that is the whole of what
            # anyone needs to find the pair.
            print("  ! gave up after %d ticks, still firing: %s"
                  % (ticks, ", ".join(sorted(set(hot)))))
        if on_settle is not None:
            on_settle(loop)

    # Whatever a domain seeded at install time may already have something
    # to say. Ask before the first prompt, not after the first line.
    settle()
    while True:
        if echo_prompt:
            sys.stdout.write("%s> " % prompt)
            sys.stdout.flush()
        line = stdin.readline()
        if line == "":
            break
        line = line.strip()
        if not line:
            continue
        if line in ("/q", "/quit", "/exit"):
            break
        if line in ("/?", "/help"):
            print(HELP)
            continue
        if line == "/show":
            for entity in loop.world.entities():
                print("  %s" % loop.world.show(entity))
            continue
        if line == "/systems":
            for i, (name, _) in enumerate(loop.systems, 1):
                print("  %2d. %s" % (i, name))
            continue
        if commands and line.startswith("/"):
            name, _, arg = line.partition(" ")
            fn = commands.get(name)
            if fn is not None:
                fresh = fn(arg.strip())
                if fresh is not None:
                    loop = fresh
                    settle()
                continue
            print("  ! no such command: %s" % name)
            continue
        line, corrections = _autocorrect(line, loop.world.vocabulary)
        for typed, fixed in corrections:
            print("  ~ %s -> %s" % (typed, fixed))
        loop.world.spawn(Said("user", line))
        settle()
    return 0
