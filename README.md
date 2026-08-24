# HarneSkills

**A door onto a [UGM](https://github.com/ercasta/Universal-Graph-Machine) machine.**

UGM is an agent that plans, acts, observes and explains itself on one graph
substrate. It recently shipped its own REPL (`ugm.repl`) — talk to it, one
`.ugm` line at a time, with typo-correction against the loaded corpus's own
vocabulary and a plain-English fallback for a line that isn't `.ugm` syntax
at all. HarneSkills carves that REPL out and promotes it to be the thing
this repository builds on: `harneskills.repl` is `ugm.repl` carved out and
kept close to it, wired up by a thin `harneskills.__main__`. It has diverged
in exactly one place — a `commands` seam, so a caller can add a slash command
the loop knows nothing about (`/reload` is the only user of it so far). The engine itself
(`ugm.core`, and any rules a domain ships) stays where it is — an ordinary
dependency, not code duplicated into this repo.

## Try it

```bash
pip install -e ../ugm      # the engine, editable, from its own checkout
pip install -e .
python -m harneskills [corpus.ugm | folder ...]     # paths are optional
```

Nothing to configure to try it. The file-tools example is in this checkout,
and one line brings both halves of it — the Python (`--tools`) and the
corpus (a folder path, read one level deep):

```bash
python -m harneskills --no-config \
    --tools harneskills.examples.fs:register \
    examples/circuit_breaker.ugm examples/fs
```

```
loaded: examples/circuit_breaker.ugm, examples/fs/fs_demo.ugm
harneskills> show files
  + ls(/your/cwd)
  + file(/your/cwd, README.md)
  + size(/your/cwd, README.md, 15086)
  ...
```

`--no-config` is only there to keep a config you may already have out of the
way; drop it once you write one. Corpora can equally arrive mid-session —
`/load examples/fs` takes a folder as happily as a file.

No corpus, no problem — `/godmode` lets you author a fact and a rule right at
the prompt, then `/usermode` to go back to talking normally:

```
$ python -m harneskills
harneskills> /godmode
  authoring directly -- /usermode to go back
harneskills[god]> fact +water(kettle)
  (1 ticks, ended quiescent)
harneskills[god]> rule <boil> +water($w) no boiling($w) -> +boiling($w)
  (2 ticks, ended quiescent)
harneskills[god]> /usermode
  back to talking on the `user` channel
harneskills> boiling(kettle)
  + arrived(user, boiling(kettle))
  + says(user, boiling(kettle))
  + trusted(boiling(kettle))
  (3 ticks, ended quiescent)
```

(That last line is a *question*, answered by asking it and watching what
sticks: typing `boiling(kettle)` in user mode says it, `<trust-user>` believes
you unconditionally, and the `+`/`-` lines are the machine settling — nothing
retracted here, so it was already true.)

Got a `.ugm` file already? Load it on the command line, or mid-session with
`/load` — this repo ships no corpus of its own (see Scope, below), so `PATH`
is wherever your domain's rules live, e.g. `../ugm/ugm/rules/delay.ugm`:

```
python -m harneskills PATH/TO/corpus.ugm
harneskills> /load PATH/TO/another.ugm
```

Typing the same paths every session gets old. `~/.config/harneskills/config`
names the folders your corpora live in, one per line, and every `*.ugm`
directly inside each one is loaded at startup:

```
# ~/.config/harneskills/config -- standing corpora, loaded in this order
~/projects/Universal-Graph-Machine/ugm/rules
~/corpora/kitchen
```

Blank lines and lines starting with `#` are ignored; `~` and `$VARS` expand;
a relative folder is relative to the config file, not to your working
directory (the thing most likely to read this file is a service). The sweep
is **one level deep** on purpose — `ugm/rules/` and `ugm/rules/fs/` are
different corpora that happen to nest, and quietly pulling in the second
because you asked for the first would be choosing your rules for you. List
the subfolder if you want it.

Standing corpora load first, then anything named on the command line — so a
file you name now can answer one that was already there. A folder in the
config that has gone missing costs you that folder (`! config: ... no such
folder`, on stderr) and not the session, and neither does a corpus that
fails to parse — it is named on stderr and skipped.

A domain is often not only `.ugm`. The fs corpus below leans on three tools,
five computators and an approval prompt, all Python, and a rule mentioning
`<approve>` is a *parse error* until something has registered an answerer by
that name. A `tools:` line names that half — `module:callable`, called as
`callable(loader)`:

```
# ~/.config/harneskills/config
tools: harneskills.examples.fs:register
~/corpora/fs
```

`tools:` lines run **before any corpus loads**, wherever they sit in the
file — they have to, or the corpus that needs them cannot parse. With those
two lines, `python -m harneskills` drives the file tools directly; nothing
about the fs domain is in the harness, which imports what the config names
exactly as it opens the folders the config names, and ships neither. A spec
that doesn't import, doesn't resolve, isn't callable, or raises is a
`! config: ...` on stderr and not a dead session.

```
$ python -m harneskills
loaded: ~/corpora/fs/circuit_breaker.ugm, ~/corpora/fs/fs_demo.ugm
harneskills> /godmode
harneskills[god]> fact +want(list("/tmp/hk-fs"))
  + ls(/tmp/hk-fs)
  + file(/tmp/hk-fs, alpha.txt)
  + size(/tmp/hk-fs, alpha.txt, 0)
  + created(/tmp/hk-fs, alpha.txt, 1787583736)
```

```
--config PATH   read that file instead of the default
--no-config     skip the file entirely, for the session where the standing
                corpus is the thing you're debugging
```

Starts in **user mode**: a bare line is heard as something you're *saying*,
wrapped as `say user: <line>` and believed only because `<trust-user>` (an
ordinary rule, loaded at start) trusts the channel unconditionally. A line
that parses as neither a proposition nor `.ugm` syntax is heard as a sentence
instead of refused (`"show files"` → `sentence(show, files)`), left for
whatever `intake` rule a loaded corpus gives it, or unbelieved if none does.
A misspelled relation name — against whatever the loaded rules already use —
gets autocorrected and echoed (`~ typed -> fixed`), never silently. See
`harneskills/repl.py`'s docstring for the full account — it's UGM's own, not
rewritten here.

```
/show      what is believed right now
/load PATH load another .ugm file into this session
/godmode   author directly -- a line is `.ugm` text (fact, rule, say, ...)
/usermode  back to the default -- a line is what you're SAYING
/reload    start over: re-read the config and every corpus from disk
/reset     the same act, under the name you reach for when the mess is yours
/quit      leave
```

`/reload` is the edit-a-rule loop: change a `.ugm` file in another window,
type `/reload`, and it's in. It has to build a **whole new machine** — UGM
won't redeclare a rule into one that already has it, so there is no such
thing as reloading a single rule in place — which is why everything you
typed this session goes with it. It re-reads `~/.config/harneskills/config`
too, so a folder or `tools:` line added mid-session takes effect without
leaving the REPL.

## An example: file tools

Three tools (`ls`, `stat`, `rename`), a corpus that holds a rename for
approval, and a circuit breaker watching it — carved out of `ugm.fs_repl`
the same way `harneskills.repl` was carved out of `ugm.repl`. Its Python
half is one function, `harneskills.examples.fs:register`, nameable from
`--tools` or a config `tools:` line; its corpus is two ordinary `.ugm`
files under `examples/`.

```
$ python -m harneskills --no-config --tools harneskills.examples.fs:register \
      examples/circuit_breaker.ugm examples/fs
harneskills> +want(list("C:\Users\you\Documents"))
  + file(...), size(...), created(...)   -- the `ls` tool, an ordinary rule away

harneskills> cleanup "C:\Users\you\Documents" 7
approve rename(notes.txt -> stale-notes.txt)? [y/N]
```

⚠ There is no `harneskills-fs` command any more. It was a second way to
start a session carrying its own hardcoded corpus list, which meant this
repo's `examples/fs/fs_demo.ugm` and your copy of it could both be live with
nothing to say which one you were talking to. One way in now, and the corpus
is whatever you point it at.

Bare `show files` works too, and lists the directory the session started in
— `fs.py:register` writes that once as `cwd`, and `<intake-show-here>` reads
it. Note the **quotes are required** on a path: unquoted, `show files in
/tmp/x` fails to tokenize (`unexpected character '/'`) before it can even
become a sentence.

Nothing about "listing" or "cleaning up" is built into the REPL or the
tools — typing something that isn't `.ugm` syntax is heard as
`sentence(show, files, in, "...")`, and it means whatever `examples/fs/fs_demo.ugm`
says it means. A rename is held for approval by the same write-time trigger
any corpus could use, not a special case in `fs_tools.py`.

## Layout

```
harneskills/
  repl.py               the REPL loop itself -- carved out of ugm.repl, plus a `commands` seam
  __main__.py           wiring: a Machine, a Loader, the corpora to load, then repl.run
  config.py             which folders and which `tools:` the config names -- strings only, no UGM
  examples/
    fs.py                the file-tools example's Python half: `register(ldr)`, and nothing else
                           -- name it with `--tools` or a config `tools:` line
    fs_tools.py           its three answerers -- carved out of ugm.repl_fs
examples/
  circuit_breaker.ugm    shared infra the fs example loads (any domain might watch a rule)
  fs/fs_demo.ugm         the fs example's own corpus
tests/
  test_config.py         the config file's promises: which folders, which files, what order
```

## Scope

**HarneSkills is a door onto UGM. Nothing else.** The engine — `ugm.core` —
is a pinned external dependency; the harness itself (`harneskills/repl.py`,
`harneskills/__main__.py`, `harneskills/config.py`) bakes in no domain
corpus, tools, or rules — the config file names folders, it does not ship
any, and `config.py` never opens a `.ugm` or imports UGM.
`harneskills/examples/` is different on purpose: worked demonstrations of
wiring a domain onto the harness, each a `register(loader)` the config or
`--tools` can name, never imported by the harness itself unless you ask for
it by name. Planning,
arbitration, norms, procedures, credit assignment and provenance are all
the engine's.

## Status

Freshly carved from `ugm.repl` (2026-08-24) — the previous, bespoke
harness (`runner.py`/`view.py`/`commands.py`/`play.py`/`dungeon.py`, a
Textual TUI, its own corpus, its own tests) is in git history; nothing was
ported from it. Verified end to end: `pip install -e ../ugm && pip install
-e .`, then both transcripts above (the no-corpus `/godmode` session and
the fs example listing a real directory with no config file at all), plus `python -m ugm.selftest`
(183 checks, 0 failing) against the same editable install. ⚠
`universal-graph-machine` is under active redesign — read
`../ugm/docs/HANDOFF.md` before diagnosing an import error.
