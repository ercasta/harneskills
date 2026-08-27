# HarneSkills

**An entity-component world, a loop that runs systems over it, and a
prompt onto both.**

Only one dependency, and it is the engine underneath this: `ugm`, embedded
here under `./engine` (its distribution root -- `import ugm` either way)
as its own package. An *entity* is an identity with no data — `#7`. A
*component* is data with no identity — `Size(bytes=4300)`. A *system* is
a Python function that asks for the entities carrying a set of components
and walks them. The *loop* calls every system, in order, over and over,
until a whole pass changes nothing — and that is when the world has
something to say. Everything else here is arranged around that loop, not
underneath it:

```
engine/ugm/world.py     entities, components, and the queries systems ask.
engine/ugm/loop.py      call every system, in order, until nothing changes.
engine/ugm/engine.py    ONE thread that runs the loop; any number of channels
                          attached to it -- a terminal, several WebSockets.
engine/ugm/save.py      the world on disk, so a restart is not an amnesia.

harneskills/repl.py     a terminal channel -- stdin in, prose out.
harneskills/serve.py    a WebSocket channel -- JSON in, JSON out.
harneskills/client.py   a small program that speaks to a served engine.
```

A **domain** is one callable — `install(loop)` — that registers systems
and spawns what they read. The harness ships none; you name the one you
want. `harneskills.examples.fs` is the worked example: listing, ageing and
renaming real files, with every rename an automation proposes held for
approval — asked as an ordinary reply, on whichever channel answers it,
because nothing here may stop the world to wait for one person's keypress
(see "Many doors, one world", below).

## Try it

```bash
pip install -e ./engine -e .
python -m harneskills --no-config harneskills.examples.fs:install
```

```
installed: harneskills.examples.fs:install
harneskills> show file
archive/
draft.txt (6 bytes)
old.md (4 bytes)
scan.pdf (4300 bytes)
todo.txt (17 bytes)
5 item(s) in /tmp/notes
harneskills> show big
scan.pdf (4300 bytes)
harneskills> shwo file in /tmp/notes/archive
  ~ shwo -> show
0 item(s) in /tmp/notes/archive
```

`show big` answers about the folder you last *looked* at — list `/tmp/a`,
list `/tmp/b`, ask, and you get `/tmp/b`. That is one component, `Focus`,
which exactly one folder entity carries at a time. Nothing fades and
nothing is ranked.

None of that is lost when the process is. The world is written to
`~/.local/state/harneskills/world.json` every time it settles, so the
next run starts knowing the folder, the entries, which of them are big or
stale, and which one you were looking at:

```
$ python -m harneskills harneskills.examples.fs:install
restored 7 entities from ~/.local/state/harneskills/world.json
installed: harneskills.examples.fs:install
harneskills> show big
scan.pdf (4300 bytes)
```

— answered without going near the disk. See **Persistence**, below.

Ageing files, and the approval that guards them:

```
harneskills> stale after 7 days
2 of 5 older than 7 day(s) in /tmp/notes
approve rename draft.txt -> stale-draft.txt in /tmp/notes? [y/N] y
renamed draft.txt -> stale-draft.txt
approve rename old.md -> stale-old.md in /tmp/notes? [y/N] n
left old.md alone
```

One question per tick, and what happened to the last answer is on screen
before the next question is asked. Type the rename yourself and nobody
asks you anything:

```
harneskills> rename huge.bin to enormous.bin
renamed huge.bin -> enormous.bin
```

That difference is not a feature — it is one component. `propose_rename`
attaches `NeedsApproval` because an *automation* proposed it; typing it
yourself spawns the same `RenameWish` without the tag, and the system that
acts asks for exactly that:

```python
w.each(RenameWish, NeedsApproval)             # ask about these
w.each(RenameWish, without=NeedsApproval)     # do these
```

Approving is `detach(entity, NeedsApproval)`, one delta a system returns
— the same wish, no longer waiting. Nothing is copied from a held queue
to a live one. Holding your own renames too would be one more `attach`,
not a different design.

## How a turn works

You type `show file`. The REPL spawns one entity carrying one component —
`Said(user, "show file")` — and runs the loop:

| tick | system | what changed |
|------|--------|--------------|
| 1 | `hear` | destroys the `Said` entity, spawns one carrying `ListWanted(#4)` |
| 1 | `list_dir` | destroys the goal, calls `ls` — an entity per entry, each with `Entry`/`Size`/`Modified` — moves `Focus`, spawns `Listed(#4, 5)` |
| 1 | `reply_listing` | destroys the `Listed`, spawns six `Reply` entities |
| 2 | *(everything)* | nothing changes — settled |

Then the prompt prints the replies and destroys them. Every arrow there is
an entity spawned by one system and destroyed by another; nothing is a
call from one system into the next, so inserting a system between any two
of them is just registering it in between.

**System order is the whole of arbitration.** No attention, no scoring, no
ranking of who most deserves a turn. Systems run in the order they were
installed, every tick, and the same input produces the same output in the
same order every time. If a listing should report entries and *then* count
them, register the entry system first.

**A system fires by changing something.** The loop reads `world.revision`
before and after; a system that re-attached a component equal to the one
already there did not fire. That is what "settled" is measured in — and
why `World.attach` comparing before it stores is load-bearing rather than
a convenience.

**A system loops.** `flag_big` walks every entry in the folder in a `for`,
in one call, and destroys the goal entity that let it run. It cannot fire
twice on the same goal because the goal is gone — so there is no per-file
bookkeeping to write, and none to get wrong.

**A budget is the circuit breaker.** Two systems can feed each other
forever. The loop counts ticks, stops at 200, and names the systems still
firing:

```
  ! gave up after 200 ticks, still firing: kitchen.ping, kitchen.pong
```

A system is named for its module and its function, because two domains
installed at once will both have one called `hear`.

## The world

`World`'s own four writing methods -- what `ugm.engine` and a domain's
own `install()` call directly, outside any system's turn:

```python
entry = w.spawn(Entry(folder, "notes.txt"), Size(2048))   # a new entity
w.attach(entry, Stale())                                  # now it is also stale
w.detach(entry, Stale)                                    # now it is not
w.each(Entry, Size, without=IsDir)                        # [(entity, entry, size), ...]
w.destroy(entity)                                         # finished with it
```

A SYSTEM never calls these four -- see "Writing a domain", below, for
what it calls instead.

**A component is a value.** `Size(17) == Size(17)`, so re-attaching one
that is already there changes nothing and the world still settles. It also
means a component is *replaced*, not edited: `attach(e, Size(4300))`,
never `size.bytes = 4300` — a component mutated in place is a change
nothing can see.

**A tag is a component with no fields.** `Stale()`, `IsDir()`,
`NeedsApproval()`. Every instance equals every other, so attaching one is
exactly "this entity is in that set" and detaching it is "no longer".

**A relationship is an entity in a component.** `Entry(folder=#1,
name='todo.txt')` — no object graph, no back references to keep in step.
Renaming makes the point: the entity is the same afterwards, still in its
folder, still carrying whatever any system concluded about it. Only its
`Entry` component is replaced.

**A query is an intersection**, walked from the rarest component asked
for, oldest entity first. `each` hands back the entity and then the
components in the order asked for.

**Destroying is what makes a system fire once** per thing asked of it.
Goals and occasions are destroyed by whoever acts on them; standing
entities — a folder, an entry, the session — are not.

## Writing a domain

```python
from ugm.delta import attach, destroy, detach, spawn
from ugm.world import Component, Reply, Said

class Kettle(Component):
    def __init__(self, name): self.name = name

class WantBoiled(Component): pass      # a tag: asked for, not yet done
class Boiling(Component): pass

def install(loop):
    loop.system(hear)
    loop.system(boil)
    loop.world.spawn(Kettle("kettle"))       # install() itself may touch the
    loop.world.learn("kettle", "boil")       # world directly -- it runs once,
                                              # before any system's own turn.

def hear(w):
    deltas = []
    for entity, said in w.each(Said):
        if said.text == "boil the kettle":
            deltas.append(destroy(entity))
            for kettle, _ in w.each(Kettle):
                deltas.append(attach(kettle, WantBoiled()))
    return deltas

def boil(w):
    deltas = []
    for entity, kettle, _ in w.each(Kettle, WantBoiled):
        deltas.append(detach(entity, WantBoiled))
        deltas.append(attach(entity, Boiling()))
        deltas.append(spawn(Reply("user", "the %s is boiling" % kettle.name)))
    return deltas
```

A system READS the world (`w.each`, `w.get`, `w.has`, `w.first`, `w.the`)
and RETURNS what should change, as a list of deltas from `ugm.delta` --
it never calls `w.spawn`/`w.attach`/`w.detach`/`w.destroy` itself.
`Loop.tick` applies one system's own deltas right after calling it,
before the next system runs, so `boil` still sees what `hear` just did,
in the same tick, exactly as if `hear` had mutated directly.

```
$ python -m harneskills --no-config mykitchen:install
harneskills> boil the kettle
the kettle is boiling
```

Three conventions, and the harness enforces none of them:

- **`Said(user, "...")`** is what a typed line arrives as. A line no
  system claims is still there when the world settles, and the prompt says
  so (`(nothing understood: ...)`) instead of guessing.
- **`Reply(channel, "...")`** is the only thing printed unasked — one
  line, bare, then the entity destroyed, because a thing said is over and
  saying it again is a new act. A reply to a channel other than `user` is
  prefixed (`[gauge] ...`).
- **`w.learn(...)`** registers words. A typed word close to exactly *one*
  of them is corrected and echoed (`~ shwo -> show`), never silently.
  Close means one edit for a short word and two for a long one, with a
  swapped pair counting as one — so `shwo` reaches `show`, and `for` stays
  two edits from `to` and is left alone. A tie is left alone too.
  Correction stops at the first word that looks like a path and never
  resumes: `show file in /etc/rc.d` reaches the systems with `rc.d` intact,
  and a folder called `Documnets` is not a typo this prompt has an opinion
  about.

## Standing domains

Typing the same specs every session gets old.
`~/.config/harneskills/config` names them, one `module:callable` per line,
installed in the order written:

```
# ~/.config/harneskills/config
harneskills.examples.fs:install
mykitchen:install
```

On Windows that file is `%APPDATA%\harneskills\config` — roaming, because
which domains you install is worth following you to another machine, where
a world full of absolute paths to this machine's disk is not.

Blank lines and lines starting with `#` are ignored; the same spec twice
is installed once. Standing domains install first, then anything named on
the command line — so a domain you name now sees a world the standing ones
already set up. A spec that doesn't import, doesn't resolve, isn't
callable, or raises is a `! ...` on stderr and not a dead session.

```
--config PATH   read that file instead of the default
--no-config     skip the file entirely, for the session where the standing
                domain is the thing you're debugging
--state PATH    keep the world somewhere else
--no-state      don't restore and don't write -- every run from nothing
```

## Many doors, one world

`python -m harneskills` attaches ONE `harneskills.repl.Terminal` to the
engine and hands the whole process over to it -- which is all the story
there has ever been to type at this prompt. `--serve` attaches a SECOND
door alongside it, a `harneskills.serve.Listener`, without touching the
first:

```bash
python -m harneskills --serve harneskills.examples.fs:install
```

```
installed: harneskills.examples.fs:install
serving on 127.0.0.1:8765 -- details in ~/.local/state/harneskills/server.json
harneskills> show file
```

Now, from anywhere else on the same machine (or over `ssh` to it) --
another terminal, a cron job, a browser tab:

```bash
python -m harneskills.client
```

```
  connected as ch3
harneskills> show file
a.txt (3 bytes)
1 item(s) in /tmp/notes
```

That reply is not this second session's own -- it is the SAME reply the
first prompt would print, because both are channels on the SAME engine,
watching the SAME settle. A `Reply(user, "...")` -- what every reply in
this domain is -- reaches every attached channel; type `show file` at
either prompt and both print the listing. This is the ordinary MUD answer
to "several people, one world," not a feature bolted on for it: `Said`
and `Reply` already carried a channel, and `harneskills.engine.Engine` is
what makes that channel a REAL one, addressable, rather than the one
implicit terminal there used to only ever be.

**One thread ever touches the world.** A channel's own thread only ever
calls `engine.post(...)` -- never `world.spawn`, never `loop.run` -- and
the engine's own thread is the only one that acts on it. That is the
whole of why several people typing at once does not need a lock around
anything: there is exactly one tick running at a time, always, and a
channel is a mailbox into it, not a second cook in the kitchen.

**Nothing may block the world for everyone else.** The old `fs.approve`
called `input(prompt)` and waited, which was fine when the terminal was
the only channel there was -- and wrong the moment a second one could be
attached, since it would freeze every channel's world, not just the one
that asked. The fix was not a workaround, it was the thing this whole
domain already does for every goal that has to wait: suspend as a
component. `approve` spawns the question as an ordinary `Reply` and marks
the wish `Asked`; `hear_answer` reads "y" or "n" off whichever channel it
arrives on. There is no callback sitting anywhere waiting to be called --
the suspension IS the state, in the world, same as everything else here.

**How a client finds the engine.** `harneskills.serve.Listener` binds
loopback TCP only -- there are no filesystem permissions to borrow the
way a Unix socket would lend, so any local process could open the port,
and the first message on a fresh connection must be `{"hello": "<token>"}`
if a token was set. `--serve` (with no explicit `--token`) makes one up
(`os.urandom`) and writes it, with the host and port actually bound, to
`harneskills.config.server_path()` (`~/.local/state/harneskills/server.json`,
`0600` where the platform supports it) -- which is also the file
`harneskills.client` reads when you do not name a server on its own
command line. A client on the same machine, run by the same account (an
`ssh` session included), finds it and connects with no further ceremony;
nothing here is TLS, so do not bind this past loopback.

```
--serve[=HOST:PORT]   open a WebSocket door too (default 127.0.0.1:8765)
--token TOKEN          require this token rather than a generated one
--headless             no terminal at all -- the process IS the server
```

`--headless` is for the case where nobody is meant to be sitting at this
process's own stdin -- a server with no console session, driven entirely
by whoever connects. Running it under `tmux` (as the standing service
does) rather than headless costs nothing and keeps the option of typing
at it directly, the same way you always could.

## Persistence

The world is written to `~/.local/state/harneskills/world.json`
(`$HARNESKILLS_STATE`, or `$XDG_STATE_HOME`; `%LOCALAPPDATA%\harneskills\`
on Windows) **every time it settles** — not on the way out. A prompt living in a service is killed, not quit, and
a save that only ran at `/quit` would be a save that never ran. A settle
that changed nothing writes nothing.

An entity is an integer and a component is a value with named fields, so
the file is just that:

```json
{"version": 1, "next": 23, "entities": [
  {"id": 3, "components": [
     {"type": "harneskills.examples.model:Folder",
      "fields": {"path": "/tmp/notes"}}]}]}
```

Four things worth knowing:

- **A component is rebuilt without its `__init__`.** `Entry(folder, name)`
  takes positional arguments that are not its field names; there is no
  signature a loader could call in general. It comes back as
  `object.__new__(cls)` with its `__dict__` restored, so a domain can
  write any constructor it likes.
- **Ids are preserved, and so is the counter.** Every reference in every
  component is an id, so `{"$entity": 3}` has to come back as `#3` — and a
  world that resumed counting at 1 would hand a new entity an id something
  is still pointing at.
- **A field may hold** `None`, `bool`, `int`, `float`, `str`, `list`,
  `tuple`, `dict` with string keys, and an `Entity`, nested however deep.
  Anything else — a set, an open file — is refused *by name* when saving
  rather than written as something it is not.
- **The restore happens before any domain installs**, and reconciling that
  is the domain's own business: nothing in the harness can tell a
  `Session` a domain just spawned from one restored out of a file.
  `fs.install` is the worked answer — it `attach`es a fresh `Session` to
  the entity that already carries one, so the clock and the working
  directory belong to the process now running while every folder and entry
  stays where it was.

The file is the same bytes on every platform, and one directory is one
`Folder` entity however it was spelled — `notes`, `./notes`, `notes/` and
`/home/you/notes` are one place, matched through `os.path.normcase` so
that `C:\Notes` and `c:\notes` are too. What is stored is the spelling
you typed, because normalising for comparison and normalising for display
are different jobs. Symlinks are deliberately *not* resolved: asking
about `/var/log` is not the same act as asking about wherever it points.

A file that isn't there is a first run, not an error. A corrupt one costs
you the world and not the session (`! state: ...`, and the file is left
alone to look at). A component whose class no longer exists — a domain
renamed, a version behind — is skipped and named; the entity keeps
everything else it carried.

```
/show      every entity in the world right now, and what it carries
/systems   the systems installed, in the order they run each tick
/reload    re-import every domain; the world comes back with it
/reset     re-import every domain and start the world EMPTY
/quit      leave
```

`/reload` is the edit-a-system loop: change a module in another window,
type `/reload`, and the new function is what runs. It re-imports every
domain (`importlib.reload`) and builds a **new world** — systems already
registered cannot be un-registered — and then restores the state file
into it, so the code is new and the world is the one you had. It re-reads
the config file too, so a domain added mid-session takes effect without
leaving the prompt.

`/reset` is the same act with the restore skipped: an empty world, and
since the next settle writes, it empties the file too. That is the
difference between "I edited a system" and "I made a mess" — with
`--no-state` there is nothing to bring back and the two are one act
again.

## Layout

```
engine/                  the ugm engine, its own package (see engine/README.md).
                          Not "ugm/" -- a bare directory of that name here
                          would shadow the installed package for anyone
                          running python -m harneskills from this root; see
                          the note in this repo's own pyproject.toml.
  pyproject.toml
  ugm/
    world.py              entities, components, and the queries systems ask
    loop.py                every system, in order, until nothing changes
    engine.py             one thread, the world, and the channels attached to it
    save.py                 the world as JSON: entities are ints, components are values
  tests/
    test_world.py         identity, values, and the intersection of the two
    test_loop.py           order, settling, the budget, a system that raises
    test_engine.py        one world, several channels, a broadcast reply
    test_save.py            the same world, ids and all, next time

harneskills/             doors onto a ugm world, and the domain worked over one
  repl.py                a Terminal channel -- stdin in, prose out
  ws.py                  the WebSocket handshake and frame codec, both directions
  serve.py               a Listener channel -- spawns a Connection per socket
  client.py              a plain WebSocket+JSON speaker; holds no world of its own
  __main__.py            wiring: restore, install, attach channels, engine.run
  config.py              which domains, and where the world/server files live
  examples/
    model.py              the file domain's components: what a thing can BE
    fs.py                 its thirteen systems, and what words reach them
    fs_tools.py           ls, stat, rename -- what those words do to a real disk
tests/
  test_repl.py           autocorrect, and a scripted session over the engine
  test_ws.py             the codec, both ends, over real sockets
  test_serve.py          a real Listener: the token gate, two connections, a drop
  test_client.py         rendering, and a session against a served engine
  test_fs.py             the example end to end: words in, real files out
  test_config.py         which domains, in what order
  test_main.py           a domain named is a domain installed
```

## Scope

**The engine bakes in no domain.** `engine/ugm/world.py`, `loop.py`,
`engine.py` and `save.py` ship no systems, no components beyond `Said`
and `Reply`, no vocabulary and no knowledge of files -- and no channel,
no transport, no config-file format either; those are `harneskills`'s to
define, on top of an engine that has never heard of any of them.
`config.py` names callables, it does not ship any, and imports nothing it
names. `harneskills/examples/` is different on purpose: worked
demonstrations, each an `install(loop)` the config or the command line
can name, never imported unless you ask for it by name.

**The harness bakes in no transport either.** A domain's systems read and
write the `World`; whether that world is reached by one terminal, by a
terminal and three WebSocket clients, or headless with no terminal at
all, is a decision `harneskills/__main__.py` makes from the command line,
not something `fs.py`, any other domain, or `ugm` itself has to know
about or plan for.

## Status

**Rewritten 2026-08-26.** The UGM dependency is gone, and with it the
`.ugm` corpus format, the loader, the graph, attention, arbitration and
the two `examples/*.ugm` files — all in git history. What replaced the
engine is `loop.py`: 43 lines of code that call functions until nothing
changes, over `world.py`'s entity-component store.

The filesystem example is the same demo it always was — listing, ageing,
proposing, approving, renaming — reimplemented as eleven systems over
three tools, and it is now covered by tests (`tests/test_fs.py`) rather
than by hand. The previous README noted that the suite never reached
`examples/` and that two bugs had sat there unnoticed as a result; that
gap is closed. `pytest` is 149 checks, 0 failing, and every transcript
above was run.

**Persistence, 2026-08-26.** The world is written down every time it
settles and restored before any domain installs, so a restart is not an
amnesia -- see **Persistence**, above. It cost `save.py` and one method
on `World`, which is the entity-component split paying for itself again:
entities are integers, components are values with named fields, and there
is nothing else in a world to write. `/reload` and `/reset` finally mean
different things because of it.

Three things the old design needed and this one does not:

- **Guard facts.** `considered(...)`, `weighed(...)`, `replied(...)`,
  `heard(...)` existed because a pattern rule re-matched what was still
  believed every tick. A system that destroys its goal and loops over the
  work in Python cannot fire twice on the same goal.
- **Attention.** "The folder you are looking at" was a claim that faded on
  a clock, restored whenever a move touched it, ranked against every other
  claim. It is now `Focus`, a tag exactly one folder entity carries.
- **Interning care.** Facts were graph nodes, and whether two identical
  shapes were the same node decided whether a check worked. Here identity
  and data are simply different things: an entity is the identity, a
  component is the data, and `Size(17) == Size(17)` without either of them
  being the same file.

What the entity-component split buys over the tuple store it replaced,
found while porting rather than argued for in advance:

- A rename is one `attach`. The entity does not change, so `Stale`,
  `Big`, and everything else a system had concluded about that file stays
  attached to it — where the tuple version had to rewrite four facts keyed
  by the old name and hope nothing else referred to it.
- The approval gate stopped being a second queue. `NeedsApproval` is a tag
  on the wish, `w.each(RenameWish, without=NeedsApproval)` is the system
  that acts, and approving detaches it.
- `/show` became worth reading: one line per entity, every component it
  carries, `Big()` and `IsDir()` visible on the files that have them.

**Many doors, 2026-08-26.** `harneskills.engine.Engine` split the loop
away from the terminal that used to own it -- see **Many doors, one
world**, above. `repl.py` is now one `Terminal` channel rather than the
loop's driver; `ws.py`, `serve.py` and `client.py` are new, hand-rolled
(no dependency) against the subset of RFC 6455 this needs. `fs.approve`
stopped blocking on `input()`, which the new engine's contract forbids
outright -- fixed the same way every other suspended goal in this domain
already was, as a component (`Asked`) rather than a call stack sitting on
a keypress.

One correctness bug came out of writing `ws.py` against itself, both
directions, over a real socket rather than a mock of one: `socket.timeout`
has been a subclass of `OSError` since Python 3.10 (it IS `TimeoutError`),
so a bare `except (ConnectionError, OSError)` around a frame read
silently mistook "nothing arrived within a caller's own deadline" for
"the peer hung up." Neither this module's own channels set a read
timeout, so nothing here was outwardly broken by it -- it would have bitten
the first caller that did, silently, and was found only because the test
suite drives the codec against itself rather than trusting one side's
idea of the other's behaviour.

`pytest` is 218 checks, 0 failing -- 68 of them new
(`test_ws.py`, `test_engine.py`, `test_serve.py`, `test_client.py`, and
the parts of `test_repl.py`/`test_fs.py`/`test_config.py` this touched),
including an end-to-end one: a `Terminal` and a `harneskills.client`
connection, attached to the same engine, each seeing the other's
broadcast reply.

**UGM again, 2026-08-27.** `world.py`, `loop.py`, `engine.py` and
`save.py` moved to `./engine` (package name still `ugm`), a package of
its own, one day after the previous entry dropped the OLD `ugm`
dependency. Not a reversal -- the old `universal-graph-machine` was a
graph substrate this repo was a terminal onto; this `ugm` is the
entity-component engine that replaced it, pulled back out now that the
split between "the engine" and "the doors onto it" (see **Many doors**,
above) had already drawn the line: every import already ran one way,
`examples/fs.py` already depended on nothing but `world.py`, and the four
moved files already imported nothing outside themselves. `harneskills`
now depends on `ugm` instead of carrying it -- `pip install -e ./engine
-e .` -- and nothing about a domain's own code changed beyond where
`Component`, `Reply` and `Said` are imported from. `pytest` is 223
checks, 0 failing, split 75 in `engine/tests` and 148 in `tests`.

The directory was `./ugm` for about an hour, until installing it for
real turned up the reason it is not: `python -m harneskills` from this
repo's own root -- its `WorkingDirectory` as a service, and what these
very instructions assume -- puts this repo's root on `sys.path`, and a
BARE directory named `ugm` sitting right there is an empty implicit
namespace package (PEP 420 asks for nothing more than the name matching
and no `__init__.py`) that Python's ordinary path search finds before
the editable install's own finder -- appended to `sys.meta_path`, so
tried LAST -- ever gets asked. `import ugm` resolved, to nothing:
`ImportError: cannot import name 'Engine' from 'ugm' (unknown
location)`. `pytest` never hit this -- its own `rootpath`/`pythonpath`
machinery does not leave a bare cwd entry on `sys.path` the way `-m` and
`-c` do -- which is exactly why installing for real and smoke-testing it
found what running the test suite could not. Renaming the embedding
directory is the fix that holds regardless of working directory or
invocation; the package inside, and everywhere it is imported from, did
not need to change at all.

**Deltas, 2026-08-27.** `ugm`'s own systems stopped touching the world
and started returning it -- see `engine/README.md`'s own entry on this;
same day, same reason. `harneskills.examples.fs`'s thirteen systems and
`fs_tools.py`'s three tools moved to the new contract with it: every
`w.spawn`/`attach`/`detach`/`destroy` became `ugm.delta.spawn`/`attach`/
`detach`/`destroy`, appended to a list and returned. `Contents.by_name`
-- documented as "the one hand-kept structure in the domain, mutated in
place" -- stopped being that: `fs_tools.ls`/`rename` compute a fresh
`Contents` and `attach` it, the same as every other component, and
`world.changed()` lost its only caller in this repository.

The one place order genuinely mattered rather than merely reading as if
it did: `_understand`'s rename branch used to create-and-immediately-list
a never-before-seen folder within one call, which a system that only
returns deltas cannot do (nothing it describes is real until it returns).
No test exercises "rename as literally the first command of a session,
before any listing" -- every one lists first -- so the branch now reads
the folder only if the world ALREADY has one, which answers exactly the
same as a freshly-created empty folder would: nothing found, "no such
file here". Every other `_listed`-then-act pattern (`flag_stale`,
`flag_big`) needed no such change, because a `Pending` a system spawns
is always resolved to a real entity by the time it finishes its OWN
turn, before the next system runs -- so nothing LATER, even later in the
same tick, ever sees an unresolved one.

`pytest` is 237 checks, 0 failing, 35 of them `test_fs.py`'s -- unchanged
behaviorally, one test helper's one-line signature fixed
(`fs.folder_at` now returns `(deltas, entity)`) and nothing else, which
is the whole of what a change to the mutation mechanism should cost the
domain's own tests.
