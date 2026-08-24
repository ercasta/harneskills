# HarneSkills

**A door onto a [UGM](https://github.com/ercasta/Universal-Graph-Machine) machine.**

UGM is an agent that plans, acts, observes and explains itself on one graph
substrate. It recently shipped its own REPL (`ugm.repl`) — talk to it, one
`.ugm` line at a time, with typo-correction against the loaded corpus's own
vocabulary and a plain-English fallback for a line that isn't `.ugm` syntax
at all. HarneSkills carves that REPL out and promotes it to be the thing
this repository builds on: `harneskills.repl` *is* `ugm.repl`, ported here
unmodified, wired up by a thin `harneskills.__main__`. The engine itself
(`ugm.core`, and any rules a domain ships) stays where it is — an ordinary
dependency, not code duplicated into this repo.

## Try it

```bash
pip install -e ../ugm      # the engine, editable, from its own checkout
pip install -e .
python -m harneskills [corpus.ugm ...]     # corpus paths are optional
```

No corpus, no problem — `/godmode` lets you author a fact and a rule right at
the prompt, then `/usermode` to go back to talking normally:

```
$ python -m harneskills
harneskills> /godmode
  authoring directly -- /usermode to go back
harneskills[god]> fact +water(kettle)
  (1 ticks, ended quiescent)
harneskills[god]> rule <boil> = implies( { +water($w), no boiling($w) }, { +boiling($w) } )
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
/quit      leave
```

## An example: file tools

```bash
harneskills-fs [corpus.ugm ...]
```

Carved out of `ugm.fs_repl` the same way `harneskills.repl` was carved out of
`ugm.repl`: three tools (`ls`, `stat`, `rename`), a corpus that holds a
rename for approval, and a circuit breaker watching it, all loaded before
handing off to the same REPL loop above.

```
$ harneskills-fs
harneskills> +want(list("C:\Users\you\Documents"))
  + file(...), size(...), created(...)   -- the `ls` tool, an ordinary rule away

harneskills> cleanup "C:\Users\you\Documents" 7
approve rename(notes.txt -> stale-notes.txt)? [y/N]
```

Nothing about "listing" or "cleaning up" is built into the REPL or the
tools — typing something that isn't `.ugm` syntax is heard as
`sentence(show, files, in, "...")`, and it means whatever `examples/fs/fs_demo.ugm`
says it means. A rename is held for approval by the same write-time trigger
any corpus could use, not a special case in `fs_tools.py`.

## Layout

```
harneskills/
  repl.py               the REPL loop itself -- carved out of ugm.repl, unmodified
  __main__.py           wiring: a Machine, a Loader, the corpora named on argv, then repl.run
  examples/
    fs.py                the file-tools example's wiring -- carved out of ugm.fs_repl
    fs_tools.py           its three answerers -- carved out of ugm.repl_fs
examples/
  circuit_breaker.ugm    shared infra the fs example loads (any domain might watch a rule)
  fs/fs_demo.ugm         the fs example's own corpus
```

## Scope

**HarneSkills is a door onto UGM. Nothing else.** The engine — `ugm.core` —
is a pinned external dependency; the harness itself (`harneskills/repl.py`,
`harneskills/__main__.py`) bakes in no domain corpus, tools, or rules.
`harneskills/examples/` is different on purpose: worked demonstrations of
wiring a domain onto the harness, each its own console script
(`harneskills-fs`, so far), never imported by the harness itself. Planning,
arbitration, norms, procedures, credit assignment and provenance are all
the engine's.

## Status

Freshly carved from `ugm.repl` (2026-08-24) — the previous, bespoke
harness (`runner.py`/`view.py`/`commands.py`/`play.py`/`dungeon.py`, a
Textual TUI, its own corpus, its own tests) is in git history; nothing was
ported from it. Verified end to end: `pip install -e ../ugm && pip install
-e .`, then both transcripts above (the no-corpus `/godmode` session and
`harneskills-fs` listing a real directory), plus `python -m ugm.selftest`
(183 checks, 0 failing) against the same editable install. ⚠
`universal-graph-machine` is under active redesign — read
`../ugm/docs/HANDOFF.md` before diagnosing an import error.
