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
harneskills> show file
N item(s) in /your/cwd
harneskills> show files
  ~ files -> file
```

The prompt only ever prints what the corpus REPLIES (`reply(user, "...")`,
see below) — `show files` the second time is the same sentence, already
heard, so it stays quiet; `/show` still lists every `file(...)`/`size(...)`
`ls` found, on demand.

`--no-config` is only there to keep a config you may already have out of the
way; drop it once you write one. Corpora can equally arrive mid-session —
`/load examples/fs` takes a folder as happily as a file.

No corpus, no problem — `/godmode` lets you author a rule right at the
prompt, then `/usermode` to go back to talking normally:

```
$ python -m harneskills
harneskills> /godmode
  authoring directly -- /usermode to go back
harneskills[god]> rule <boil> = implies({ +water($w), no boiling($w) }, { +boiling($w), +reply(user, "the kettle is boiling") })
harneskills[god]> /usermode
  back to talking on the `user` channel
harneskills> water(kettle)
the kettle is boiling
```

The rule loads first, on purpose. A loaded `fact` carries no attention of
its own — UGM's own choice: attending is *taking care of something*, and a
fact loaded cold is background, never news (`../ugm/docs/HANDOFF.md`). The
last line is what still starts things: typing `water(kettle)` in user mode
is a *saying*, wrapped as `say user: water(kettle)` and delivered as an
arrival, which UGM does attend — that's what wakes `<boil>` up to conclude
`boiling(kettle)`, not `<trust-user>` believing you (which only ever
believes exactly what you typed). A bare `fact +water(kettle)` typed in
`/godmode` would sit there believed and inert, the same as one loaded from
a file — say it instead, or pair it with your own `attend(...)`. And the
one line the prompt prints, `the kettle is boiling`, is not a diff of
belief — `<boil>` said so itself, concluding `+reply(user, "...")`; see
"The output boundary is a channel too", further down.

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
eight computators and an approval prompt, all Python, and a rule mentioning
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
harneskills> +want(list("/tmp/hk-fs"))
1 item(s) in /tmp/hk-fs
```

Said at the ordinary prompt, not `/godmode` — the point being made here is
tools compounding over a real graph, not authoring, and a plain line is an
arrival (attended) the moment `<trust-user>` believes it, which is what
gets `<list>` a turn at all.

```
--config PATH   read that file instead of the default
--no-config     skip the file entirely, for the session where the standing
                corpus is the thing you're debugging
```

Starts in **user mode**: a bare line is heard as something you're *saying*,
wrapped as `say user: <line>` and believed only because `<trust-user>` (an
ordinary rule, loaded at start) trusts the channel unconditionally. A line
that parses as neither a proposition nor `.ugm` syntax is heard as a sentence
instead of refused (`"show files"` → `sentence(show, file)`, the plural
autocorrected first), left for
whatever `intake` rule a loaded corpus gives it, or unbelieved if none does.
A misspelled relation name — against whatever the loaded rules already use —
gets autocorrected and echoed (`~ typed -> fixed`), never silently. See
`harneskills/repl.py`'s docstring for the full account — it's UGM's own, not
rewritten here.

The prompt itself stays QUIET beyond that: it prints exactly one shape,
a freshly concluded `reply(user, "...")` — one line, no `+`, not a diff
of belief. `<deliver>` (loaded alongside `<trust-user>`) is the output
half of the same idiom, marking `delivered(user, "...")` so a corpus's
own rule can guard against saying the same thing twice, the same brake
every intake rule already needs. A corpus with no `reply(...)` rule of
its own is silent here, same as it always was about anything a bare
belief diff couldn't say on its own — `/show` is still the whole belief
state, any time, nothing hidden.

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
12 item(s) in C:\Users\you\Documents   -- the `ls` tool, an ordinary rule away

harneskills> +want(stale_after("C:\Users\you\Documents", 7))
approve pending(rename(C:\Users\you\Documents, notes.txt, stale-notes.txt))? [y/N]
```

⚠ There is no `harneskills-fs` command any more. It was a second way to
start a session carrying its own hardcoded corpus list, which meant this
repo's `examples/fs/fs_demo.ugm` and your copy of it could both be live with
nothing to say which one you were talking to. One way in now, and the corpus
is whatever you point it at.

Bare `show file` works too, and lists the directory the session started in
— `fs.py:register` writes that once as `cwd`, and `<intake-show-here>` reads
it.

**One spelling, singular, everywhere.** `file` is already the vocabulary —
`ls` writes `file($dir, $name)` — so the plural is one edit away from a word
the machine knows and autocorrect turns `show files` into the same rule for
free, echoing `~ files -> file`. Spell the intake plural instead and you get
the opposite: `files` becomes the only place the word occurs, `file` is a
different word that happens to be a relation, and nothing relates them. Pick
one and near misses fall towards it. What this does *not* buy is `show fi`:
`_autocorrect` never considers a span of two characters or fewer, whatever
the distance, because at that length everything is near everything — a guard
in `harneskills/repl.py` that no corpus can spell its way out of.

Note the **quotes are required** on a path: unquoted, `show file in /tmp/x`
fails to tokenize (`unexpected character '/'`) before it can even become a
sentence.

Once a folder is listed, `show big` reports the large files **in that
folder** — the one you just looked at, not every folder listed this session:

```
harneskills> show file in "/tmp/a"
harneskills> show file in "/tmp/b"
harneskills> show big
huge.bin (2048000 bytes)
```

Listing a folder *attends* it (`=> attend($dir, 5)` on the intake rules),
which is UGM's own attention rather than a fact this corpus keeps: a claim
that fades on its own clock and is restored whenever a move touches the
folder again. `attentioned($dir)` says only that a folder is in the pool at
all — both are — so what picks `/tmp/b` is that the engine ranks a rule's
own applications by attention, newest first, and `<focus-big>` spends the
`want` that let it match, so exactly one binding takes.

Nothing about "listing" or "cleaning up" is built into the REPL or the
tools — typing something that isn't `.ugm` syntax is heard as
`sentence(show, file, in, "...")`, and it means whatever `examples/fs/fs_demo.ugm`
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
(203 checks, 0 failing) against the same editable install. ⚠
`universal-graph-machine` is under active redesign — read
`../ugm/docs/HANDOFF.md` before diagnosing an import error.

**Re-verified 2026-08-25** against the session that stopped attending a
loaded `fact` and stopped interning. Three fixes, all on this side of the
dependency, none in `ugm.core` itself:

- `fs_tools.py`'s own dedup check compared exact NODES (`m.pad.holds`),
  which `never intern` made a check that could never once catch a repeat
  — every `show file` on a directory already listed piled up a fresh twin
  of every fact `ls` had already written. `m.holds` (the shape check) is
  what a caller holding a freshly built node, rather than one it matched,
  needs.
- `<trust-user>`'s own `=> brush(says(user, $p))` quietly stopped working
  for the identical reason UGM's own `delay.ugm` `<care>` did (see the
  HANDOFF): `brush(...)` REBUILDS its argument by substitution, which
  mints a twin now rather than re-attending the believed occasion. Fixed
  the way UGM fixed it — `after <trust-user> { $sp = says(user, $p) } =>
  attend($sp, 5, 1, 1)`, a QUERY against belief, never a rebuild.
- `examples/fs/fs_demo.ugm`'s `<intake-show-big>`/`<rearm-big>` called
  `attentioned(sentence(show, big))` with the literal spelled out. A
  PREDICATE's ground argument is never resolved against belief the way an
  ordinary member is (`core/rules.py`'s match loop `walk()`s it and hands
  it over unchanged) — so that argument was always the rule's OWN
  load-time copy, never the node the channel actually delivered and the
  engine actually attended. Fixed by binding it first, `<focus-big>`'s own
  working idiom: `+says(user, sentence(show, big)) as $s, attentioned($s)`.

None of the three raised an error or a test failure on their own — `show
big` just never answered, and a re-listed directory just quietly grew
duplicate facts. This repo's own test suite (`pytest`) does not reach
`examples/`; the fs corpus is exercised only by hand and by this README,
which is what let the second and third sit unnoticed until this pass.

On top of the fixes: a **reply channel**, symmetric to the intake one --
see `harneskills/repl.py`'s docstring, "The output boundary is a channel
too". The prompt no longer prints a raw belief diff; a corpus concludes
`+reply(user, "...")` to speak, and three new rules in `fs_demo.ugm`
(`<reply-listed>`, `<reply-big>`, `<reply-renamed>`) are what make the fs
example say anything at this prompt at all now.
