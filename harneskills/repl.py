"""A terminal: one channel onto a running `ugm.engine.Engine`.

    harneskills> show file
    fs_demo.py (4096 bytes)
    ...
    12 item(s) in /home/you/notes

`Terminal` is a CHANNEL, in the sense `ugm.engine` defines one: it
reads lines, posts them to the engine, and renders whatever comes back.
It does not run the loop, does not own the world, and does not know
whether it is the only channel attached -- a WebSocket client
(`harneskills.serve`) can be reading the same settle at the same time,
and neither has to know the other is there. This module used to BE the
loop ("take a line, run the loop, print what it says"); the engine is
what that turned into, so several of these -- and several sockets -- can
say things to one world at once.

## Typing at this prompt is SAYING something, not authoring

A line is posted as `say`, which the engine turns into `Said(name, "show
file")` where `name` is this terminal's own channel name -- never
literally `"user"`, which the engine reserves for "everyone" (see its own
docstring, "Channels, and who hears what"). Whether the words mean
anything is a question for the rules a domain installed; a line no
rule claims comes back as `{"unheard": ...}` and is printed as such,
not guessed at.

There is no way to author a rule at this prompt, and no mode that would
let you: a rule is a Python function, so writing one means editing a
module and `/reload`ing.

## The output is a channel, and a reply is the only thing printed unasked

A domain that wants to say something spawns `Reply(user, "...")`; the
engine turns that into `{"reply": {"channel": "user", "text": "..."}}`
and delivers it to every attached channel, and THIS module is what turns
that back into one bare printed line. A reply to a channel other than
`user` -- meant for one asker, not everyone -- is prefixed
(`[gauge] ...`). `/show` asks the engine for the whole world and prints
it, on demand, any time.

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

Reading `engine.loop.world.vocabulary` straight off the engine's own
object, from this channel's thread, is the one place this module touches
the world without going through `post` -- deliberately: a domain calls
`learn` at install and essentially never again, so the set this reads is,
in practice, never being written while it is being read. Anything that
IS live -- the world's facts, what a line means -- goes through the queue
like everyone else's.

## /quit ends the whole session, here and only here

A WebSocket client's own `/quit` (`harneskills.client`) closes ITS
connection and nothing else -- other channels carry on. THIS terminal is
the one that started the process (`python -m harneskills`), and typing
`/quit` at it stops the engine outright, the same way it always ended the
session before there was a second door in. If a server is meant to
outlive its terminal, do not attach one.
"""

from __future__ import annotations

import re
import sys
import threading
from typing import Optional, TextIO

# A quoted span, taken whole and never corrected, or a run of non-space.
_SPAN = re.compile(r'"[^"]*"|\S+')
# What makes a span a path rather than a word: a separator, an extension,
# a home dir, or quotes someone put there on purpose.
_PATHISH = re.compile(r'[/\\~"]|\.\w')

HELP = """\
/show      every entity in the world right now, and what it carries
/rules     the rules installed, in the order they run each tick
/quit      leave -- ends the whole session (see this module's docstring)

Type what you want in words -- `show file`, `show file in /tmp`, `show
big`. A line becomes `Said("%s", "...")` and means whatever the installed
domains' rules make of it; a line nobody claims is reported, not
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


def autocorrect(line: str, vocab: "set[str]"):
    """`(corrected_line, [(typed, fixed), ...])`. Spacing is preserved
    exactly: spans are spliced back into the original text rather than
    rejoined. See this module's docstring, "Autocorrect is against the
    DOMAIN's vocabulary"."""
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


class Terminal:
    """A channel: stdin in, stdout out, over one attached `Engine`.

    `name` is left unset until `Engine.attach` names it -- a terminal
    started before the engine exists (which is every terminal there is)
    cannot know its own name any sooner than that.
    """

    def __init__(self, prompt: str = "harneskills",
                 stdin: Optional[TextIO] = None,
                 stdout: Optional[TextIO] = None,
                 echo_prompt: bool = True) -> None:
        self.name = None
        self.prompt = prompt
        self.stdin = stdin or sys.stdin
        self.stdout = stdout or sys.stdout
        self.echo_prompt = echo_prompt
        self.engine = None
        self._stop = threading.Event()

    # -- the channel contract (see ugm.engine) -----------------

    def start(self, engine) -> None:
        self.engine = engine
        self._print(HELP % self.name)
        threading.Thread(target=self._read_loop, daemon=True).start()

    def deliver(self, message: dict) -> None:
        self._render(message)

    def close(self) -> None:
        self._stop.set()

    # -- reading --------------------------------------------------------

    def _read_loop(self) -> None:
        while not self._stop.is_set():
            if self.echo_prompt:
                self.stdout.write("%s> " % self.prompt)
                self.stdout.flush()
            line = self.stdin.readline()
            if line == "":
                # EOF ends the session the same way `/quit` does -- not
                # just this channel's own read loop -- because for the
                # ordinary `python -m harneskills` case this terminal IS
                # the process, and `< script.txt` running out of lines
                # must exit rather than leave `engine.run()` blocked
                # forever on a queue nothing will ever feed again.
                self.engine.post(self, "stop", None)
                break
            line = line.strip()
            if not line:
                continue
            if line in ("/q", "/quit", "/exit"):
                # Ends the whole session -- see this module's docstring.
                # Posted, not called directly: a `say` typed just before
                # it must be acted on first, not stranded in the queue by
                # a stop that got there first (see `Engine.post`).
                self.engine.post(self, "stop", None)
                break
            if line == "/?" or line == "/help":
                self._print(HELP % self.name)
                continue
            if line.startswith("/"):
                self.engine.post(self, "command", line)
                continue
            vocab = self.engine.loop.world.vocabulary
            line, corrections = autocorrect(line, vocab)
            for typed, fixed in corrections:
                self._print("  ~ %s -> %s" % (typed, fixed))
            self.engine.post(self, "say", line)
        self._stop.set()

    # -- rendering --------------------------------------------------------

    def _print(self, text: str) -> None:
        print(text, file=self.stdout)

    def _render(self, message: dict) -> None:
        """One message from the engine, as lines for a person. Anything
        not one of the shapes `ugm.engine` documents is printed
        raw -- swallowing an unrecognised message is how a new one goes
        undebugged."""
        if "reply" in message:
            reply = message["reply"]
            text, channel = reply.get("text", ""), reply.get("channel")
            self._print(text if channel == "user" else
                        "[%s] %s" % (channel, text))
        elif "unheard" in message:
            self._print("  (nothing understood: %s)"
                        % message["unheard"].get("text", ""))
        elif "error" in message:
            self._print("  ! %s" % message["error"].get("text", ""))
        elif "lines" in message:
            for line in message["lines"]:
                self._print("  %s" % line)
        elif "settled" in message:
            pass          # nothing to say; a richer terminal could redraw
        elif "world" in message:
            # `ugm.save.dump`'s own shape: a header (no "entity" key) then
            # one record per component or bare entity, already grouped
            # contiguously by entity -- see that module's own docstring.
            entity_id, shown = None, []
            for record in message["world"]:
                if "entity" not in record:
                    continue                    # the header
                if record["entity"] != entity_id:
                    if entity_id is not None:
                        self._print("  #%-4s %s" % (entity_id, "  ".join(shown)))
                    entity_id, shown = record["entity"], []
                if "type" in record:
                    shown.append("%s(%s)" % (record["type"].rpartition(":")[2],
                                             ", ".join("%s=%r" % kv for kv
                                                       in record["fields"].items())))
            if entity_id is not None:
                self._print("  #%-4s %s" % (entity_id, "  ".join(shown)))
        else:
            self._print("  ? %r" % (message,))
