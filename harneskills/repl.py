"""A REPL: load a corpus, run to quiescence, take a line, repeat.

Carved out of `ugm.repl` (the engine's own shipped REPL) into HarneSkills --
this file's logic is UGM's, not a reimplementation of it. `ugm/__main__.py`
deliberately has none of this -- it runs one corpus once and exits, because
`--save`/`--resume` were never built (see its own docstring). This is not
that. There is still no session file: the state that would need saving is
the one `Machine` this process holds, for as long as the process runs. What
a REPL adds over one run is a human answering a tool mid-session, and typing
a NEW rule once the facts it would read already exist, which is the
"compounding" this exists to show (see UGM's `docs/tools-approval.md`).

One Loader for the whole session, not one per line: a rule named `<hold>` on
line 1 has to still resolve when line 40 writes `<producing(<hold>, ...)>`
about it, and name resolution lives on the Loader instance, not the scope
string (see `Loader.rule_nodes`).

Everything a corpus can do, this REPL asks for the same way a corpus does --
`.ugm` text, one line at a time. A real path or filename (colons, spaces,
backslashes) is an ordinary, typeable quoted string (`core/text.py`'s
lexer): `+want(list("C:\\Users\\ercas\\Documents"))` -- no REPL command that
knows what a directory listing means; the tool that does is a rule an
engine-side corpus ships (see `ugm/repl_fs.py` and `ugm/rules/fs/` upstream).

## Typing at this prompt is talking on a channel, not authoring

A `fact` is standing knowledge; what a PERSON types is an utterance, and
§13 says an arrival is not a belief until a rule trusts it -- the same
distinction the engine already draws for every other channel. So a bare
line (`+want(list("..."))`) is wrapped as `say user: <line>` before it
reaches the loader, and `TRUST_USER` below is the rule that turns it into
a belief -- unconditional, because the person at the keyboard IS the
authority a REPL exists to ask. It is an ORDINARY rule, loaded like any
other: replace it (or add a condition to it) in your own corpus and the
REPL's trust in `user` is whatever you wrote, not a hidden default.

`/godmode` and `/usermode` switch which one a line IS, for every line until
the other is typed -- an explicit, visible session state (the prompt shows
it), not sniffed per line from what the text happens to start with. In
user mode a line can only ever be a proposition (`say` reads nothing else);
authoring a rule live needs `/godmode` first.

## Autocorrect is against the CORPUS's own vocabulary, and only ever a
## name -- never a quote, a variable or a rule reference

A typo in a relation name does not fail loudly: it mints a fresh atom,
same as any other word, and `gates.vocabulary` exists to catch that AFTER
the fact by reading `nothing writes this`. At the keyboard the fix is
closer to hand -- every relation name the loaded rules and facts already
use, at any nesting depth (`_vocabulary`), is a known word, and a typed
word that is not one gets corrected to the nearest known word IF exactly
one is nearest and close enough (`_LEVENSHTEIN_MAX`). Ambiguous (two
words equally close) or too far: left alone, so the loader's own error is
what a genuinely new word gets, same as always. Printed either way -- an
autocorrect that changed what you typed without saying so would be a
worse trap than the typo. `"quoted text"`, `$variables` and `<rule refs>`
are never touched: a filename is not vocabulary.

## A line that is not a proposition is heard as a SENTENCE, not refused

`+want(list("..."))` is precise -- a person does not talk that way.
"show files" is not `.ugm` syntax at all: no sign, no parens. Rather than
refuse it, a line that fails to parse as a proposition is tried again as
`sentence(show, files)` -- every word, in order, on the SAME `user`
channel an ordinary `say` uses (§13 again: an arrival, not a belief).
Nothing built in knows what a sentence MEANS; an "intake" rule in the
loaded corpus is what gives one. A sentence with no rule reading it just
sits there, unbelieved, same as any other untrusted arrival -- and `/show`
still lists it, so nothing is hidden.
"""

import os
import re
import sys
from typing import Optional, TextIO

from ugm.core.machine import Machine
from ugm.core.text import Loader, ParseError, _LINE_FORM_STOPS, tokenise

# A quoted string, a `<rule reference>`, a `$variable` -- consumed whole and
# never corrected -- or a bare name, which might be.
_SPAN = re.compile(r'"(?:[^"\\]|\\.)*"|<[^>]*>|\$[A-Za-z_][A-Za-z0-9_-]*'
                    r'|[A-Za-z_][A-Za-z0-9_-]*')
_LEVENSHTEIN_MAX = 2

# The surface's OWN vocabulary -- statement keywords (`_LINE_FORM_STOPS`,
# reused so this stays in sync with the parser rather than drifting), plus
# everything else `Parser` dispatches on by spelling: connectives,
# bindings, postcondition ops. None of it is domain vocabulary and none
# of it may ever be a correction target -- `fact +wnat(...)` mangling
# `fact` itself into `want` (found live: `wnat` IS closer to `want` than
# `fact` is to anything else) is exactly the failure this guards.
_GRAMMAR_WORDS = _LINE_FORM_STOPS | {
    "no", "as", "at", "implies", "causes", "extends", "alt",
    "stop", "attend", "unattend", "push", "pop",
    "merge", "unmerge", "destroy", "label", "unlabel", "forget",
}


def _levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i] + [0] * len(b)
        for j, cb in enumerate(b, 1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1,
                         prev[j - 1] + (ca != cb))
        prev = cur
    return prev[-1]


def _vocabulary(m: Machine) -> "set[str]":
    """Every WORD the loaded rules and facts use, at ANY nesting depth --
    a relation name (`want`, `list`), unlike `Machine.web`, which only
    looks at the top of each antecedent/consequent pattern and so misses
    `list` in `want(list($d))` -- and a plain literal argument too
    (`show`, `in`, in an intake rule's `sentence(show, files, in, $dir)`),
    which is not a relation at all and so `web` could never see it either
    way. A numeral is excluded -- `7` autocorrecting toward some unrelated
    word is nonsensical, never useful.

    `m._bookkeeping` (the same filter `_visible` prints through) is
    excluded: every loaded rule deposits `rule(<name>)`/`ant(...)`/`con(...)`
    as ordinary believed facts (§ a rule is a node), so without this,
    `ant` -- never something a person means to type -- sits in the
    vocabulary and ties `want` at distance 2, refusing a correction that
    would otherwise be unambiguous. Measured, not guessed: this is exactly
    the failure `_wnat_ -> want` hit before the filter was added.
    """
    out: "set[str]" = set()

    def collect(node) -> None:
        if m.g.is_var(node):
            return
        rel = m.g.relation_of(node)
        members = m.g.members(node)
        if rel is not None:
            if rel not in m._bookkeeping:
                out.add(m.g.show(rel))
        elif not members and not m.g.show(node).isdigit():
            out.add(m.g.show(node))  # a bare literal, used as an argument
        for mm in members:
            collect(mm)

    for r in m.rules.rules:
        for x in r.antecedent:
            collect(x.pattern)
        for x in r.consequent:
            collect(x.pattern)
    for p in m.pad.believed():
        collect(p)
    return out


def _autocorrect(line: str, vocab: "set[str]"):
    """`(corrected_line, [(typed, fixed), ...])`. Only a bare name span is
    ever a candidate; see `_SPAN`."""
    corrections = []
    out = []
    last = 0
    for match in _SPAN.finditer(line):
        text = match.group()
        out.append(line[last:match.start()])
        last = match.end()
        if (text[0] in ('"', "<", "$") or text in vocab
                or text in _GRAMMAR_WORDS or len(text) <= 2):
            out.append(text)
            continue
        best, best_dist, ties = None, _LEVENSHTEIN_MAX + 1, 0
        for word in vocab:
            d = _levenshtein(text, word)
            if d < best_dist:
                best, best_dist, ties = word, d, 1
            elif d == best_dist:
                ties += 1
        if best is not None and best_dist <= _LEVENSHTEIN_MAX and ties == 1:
            out.append(best)
            corrections.append((text, best))
        else:
            out.append(text)
    out.append(line[last:])
    return "".join(out), corrections

# `no trusted($p)` is not optional. Without it this rule matches the same
# `says(user, $p)` -- which nothing ever retracts, an utterance stays said
# -- forever, winning arbitration every tick without producing anything
# new and starving every other rule out. Same discipline as a `<flag-stale>`
# style rule: the guard is consumed in the SAME firing that acts on it, not
# a later stage.
# `=> brush(...)` is not optional. A move consumes what it matched on, and
# this rule is NOT the last thing that should happen to a saying: every
# intake rule in every corpus reads `says(user, ...)` too. Believing you is
# one use of what you said, not the end of it.
TRUST_USER = ('rule <trust-user> = implies( { +says(user, $p), no trusted($p) }, '
              '{ +$p, +trusted($p) } ) => brush(says(user, $p))')

HELP = """\
/show      what is believed right now
/load PATH load another .ugm file -- or a folder of them -- into this session
/godmode   author directly -- a line is `.ugm` text (fact, rule, say, ...)
/usermode  back to the default -- a line is what you're SAYING
/quit      leave

Starts in user mode: a line is wrapped as `say user: <line>` and believed
only because <trust-user> (loaded at start) trusts this channel
unconditionally -- an ORDINARY rule, replaceable in your own corpus. A path
or filename needing a space or a backslash is a quoted string: "like this",
never autocorrected. A misspelled relation name IS -- against whatever the
loaded rules already use -- and it's echoed (`~ typed -> fixed`), never
silent. Extra spacing between tokens has always been ignored.
example:  +want(list("C:\\Users\\ercas\\Documents"))
A line that is not a proposition is heard as a sentence instead of
refused -- "show files" becomes `sentence(show, files)`, on the same
channel, meaning whatever the loaded corpus's own intake rules give it.
"""



def _visible(m: Machine, p) -> bool:
    return m.g.relation_of(p) not in m._bookkeeping


def _as_sentence(ldr: Loader, raw: str):
    """Every word of a line that failed to parse as a proposition, as one
    `sentence(w1, w2, ...)` node -- `None` if the line has no words at
    all, or fails even to TOKENIZE (an unclosed quote: a typo in a
    proposition someone was clearly attempting, not a sentence). Signs,
    parens and commas are not words and are dropped rather than refused,
    so `+show(files)` half-typed still reads as `sentence(show, files)`."""
    try:
        toks = tokenise(raw)
    except ParseError:
        return None
    words = [t.text for t in toks if t.kind in ("name", "string")]
    if not words:
        return None
    return ldr.m.g.rel(ldr.atom("sentence"), *[ldr.atom(w) for w in words])


def run(m: Machine, ldr: Loader, limit: int = 400,
        prompt: str = "harneskills", stdin: Optional[TextIO] = None,
        echo_prompt: bool = True, commands=None) -> int:
    """`commands` is `{"/name": fn}`, the one seam this loop has for a caller
    that knows something it does not. `fn(argument_text)` may return None --
    it handled itself -- or a fresh `(Machine, Loader)` to carry on with,
    which is how `/reload` can exist at all: UGM will not redeclare a rule
    into a machine that already has it, so re-reading an edited corpus means
    a NEW machine, and only the loop can swap the one it is holding. Each
    fn's first docstring line is its help text.
    """
    stdin = stdin or sys.stdin
    ldr.load(TRUST_USER)
    extra = "".join(
        "%-10s %s\n" % (name, ((fn.__doc__ or "").strip().splitlines() or [""])[0])
        for name, fn in (commands or {}).items())
    print(HELP.replace("/quit      leave\n", extra + "/quit      leave\n", 1))
    seen = set(m.pad.believed())
    god = False

    def settle(label: str = "") -> None:
        nonlocal seen
        steps = m.run(limit=limit)
        now = set(m.pad.believed())
        for p in sorted(now - seen):
            if _visible(m, p):
                print(f"  + {m.g.show(p)}")
        for p in sorted(seen - now):
            if _visible(m, p):
                print(f"  - {m.g.show(p)}")
        seen = now
        ended = steps[-1].state if steps else "nothing to do"
        print(f"  ({len(steps)} ticks{label}, ended {ended})")

    while True:
        if echo_prompt:
            sys.stdout.write(f"{prompt}{'[god]' if god else ''}> ")
            sys.stdout.flush()
        line = stdin.readline()
        if line == "":
            break
        line = line.strip()
        if not line:
            continue
        if line in ("/q", "/quit", "/exit"):
            break
        if line == "/show":
            for p in sorted(seen):
                if _visible(m, p):
                    print(f"  {m.g.show(p)}")
            continue
        if line == "/godmode":
            god = True
            print("  authoring directly -- /usermode to go back")
            continue
        if line == "/usermode":
            god = False
            print("  back to talking on the `user` channel")
            continue
        if line.startswith("/load "):
            path = line[6:].strip().strip('"')
            # A folder loads every `.ugm` directly in it, alphabetically --
            # one level deep, the same reading `harneskills.config` gives a
            # folder, because `examples/fs` and `examples/fs/anything` are
            # different corpora that happen to nest.
            if os.path.isdir(path):
                targets = sorted(os.path.join(path, n) for n in os.listdir(path)
                                 if n.endswith(".ugm"))
                if not targets:
                    print(f"  ! {path}: no .ugm files")
                    continue
            else:
                targets = [path]
            for target in targets:
                # One bad file out of a folder must not take the prompt with
                # it -- and `ldr.load` is not transactional, so what came
                # before the bad line in that file is already in.
                try:
                    with open(target, "r", encoding="utf-8") as fh:
                        ldr.load(fh.read())
                except OSError as e:
                    print(f"  ! {target}: {e.strerror or e}")
                    continue
                except ParseError as e:
                    print(f"  ! {target}: partly loaded, then: {e}")
                    continue
                print(f"  loaded {target}")
            settle()
            continue
        if commands and line.startswith("/"):
            name, _, arg = line.partition(" ")
            fn = commands.get(name)
            if fn is not None:
                fresh = fn(arg.strip())
                if fresh is not None:
                    # A whole new session handed back. Rebind -- `settle`
                    # reads `m` from here, so it follows -- and re-lay the
                    # one rule this loop owns rather than a corpus, or user
                    # mode would quietly stop being believed. `seen` starts
                    # again too: nothing the old machine held is news about
                    # the new one.
                    m, ldr = fresh
                    ldr.load(TRUST_USER)
                    seen = set(m.pad.believed())
                continue
        line, corrections = _autocorrect(line, _vocabulary(m))
        for typed, fixed in corrections:
            print(f"  ~ {typed} -> {fixed}")
        if god:
            try:
                ldr.load(line)
            except ParseError as e:
                print(f"  ! {e}")
                continue
        else:
            try:
                ldr.load(f"say user: {line}")
            except ParseError as e:
                sentence = _as_sentence(ldr, line)
                if sentence is None:
                    print(f"  ! {e}")
                    continue
                channel = ldr.m.channels.use(ldr.atom("user"))
                ldr.m.channels.deliver(channel, sentence)
                print(f"  (heard as: {ldr.m.g.show(sentence)})")
        settle()
    return 0
