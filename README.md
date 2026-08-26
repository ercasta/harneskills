# HarneSkills

**An entity-component world, a loop that runs systems over it, and a
prompt onto both.**

There is no engine. An *entity* is an identity with no data — `#7`. A
*component* is data with no identity — `Size(bytes=4300)`. A *system* is a
Python function that asks for the entities carrying a set of components
and walks them. The *loop* calls every system, in order, over and over,
until a whole pass changes nothing — and that is when you get your prompt
back. Three small modules, no dependencies:

```
harneskills/world.py   entities, components, and the queries systems ask.
harneskills/loop.py    call every system, in order, until nothing changes.
harneskills/repl.py    a line in, a reply out. Knows no domain.
```

A **domain** is one callable — `install(loop)` — that registers systems
and spawns what they read. The harness ships none; you name the one you
want. `harneskills.examples.fs` is the worked example: listing, ageing and
renaming real files, with every rename an automation proposes held for
your approval by one component.

## Try it

```bash
pip install -e .
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

Approving is `w.detach(entity, NeedsApproval)` — the same wish, no longer
waiting. Nothing is copied from a held queue to a live one. Holding your
own renames too would be one more `attach`, not a different design.

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

```python
entry = w.spawn(Entry(folder, "notes.txt"), Size(2048))   # a new entity
w.attach(entry, Stale())                                  # now it is also stale
w.detach(entry, Stale)                                    # now it is not
w.each(Entry, Size, without=IsDir)                        # [(entity, entry, size), ...]
w.destroy(entity)                                         # finished with it
```

**A component is a value.** `Size(17) == Size(17)`, so re-attaching one
that is already there changes nothing and the world still settles. It also
means a component is *replaced*, not edited: `w.attach(e, Size(4300))`,
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
from harneskills.world import Component, Reply, Said

class Kettle(Component):
    def __init__(self, name): self.name = name

class WantBoiled(Component): pass      # a tag: asked for, not yet done
class Boiling(Component): pass

def install(loop):
    loop.system(hear)
    loop.system(boil)
    loop.world.spawn(Kettle("kettle"))
    loop.world.learn("kettle", "boil")     # what autocorrect aims at

def hear(w):
    for entity, said in w.each(Said):
        if said.text == "boil the kettle":
            w.destroy(entity)
            for kettle, _ in w.each(Kettle):
                w.attach(kettle, WantBoiled())

def boil(w):
    for entity, kettle, _ in w.each(Kettle, WantBoiled):
        w.detach(entity, WantBoiled)
        w.attach(entity, Boiling())
        w.spawn(Reply("user", "the %s is boiling" % kettle.name))
```

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

Blank lines and lines starting with `#` are ignored; the same spec twice
is installed once. Standing domains install first, then anything named on
the command line — so a domain you name now sees a world the standing ones
already set up. A spec that doesn't import, doesn't resolve, isn't
callable, or raises is a `! ...` on stderr and not a dead session.

```
--config PATH   read that file instead of the default
--no-config     skip the file entirely, for the session where the standing
                domain is the thing you're debugging
```

```
/show      every entity in the world right now, and what it carries
/systems   the systems installed, in the order they run each tick
/reload    start over: re-import every domain and empty the world
/reset     the same act, under the name you reach for when the mess is yours
/quit      leave
```

`/reload` is the edit-a-system loop: change a module in another window,
type `/reload`, and the new function is what runs. It re-imports every
domain (`importlib.reload`) and builds a **new world** — systems already
registered cannot be un-registered, and every component in the world was
put there by the old ones — so everything the session learned goes with it. It re-reads the
config file too, so a domain added mid-session takes effect without
leaving the prompt.

## Layout

```
harneskills/
  world.py              entities, components, and the queries systems ask
  loop.py               every system, in order, until nothing changes
  repl.py               a line in, a reply out -- knows no domain
  __main__.py           wiring: a Loop, the domains to install, then repl.run
  config.py             which domains the config names -- strings only, imports nothing
  examples/
    model.py              the file domain's components: what a thing can BE
    fs.py                 its eleven systems, and what words reach them
    fs_tools.py           ls, stat, rename -- what those words do to a real disk
tests/
  test_world.py         identity, values, and the intersection of the two
  test_loop.py          order, settling, the budget, a system that raises
  test_repl.py          autocorrect, and a scripted session
  test_fs.py            the example end to end: words in, real files out
  test_config.py        which domains, in what order
  test_main.py          a domain named is a domain installed
```

## Scope

**The harness bakes in no domain.** `world.py`, `loop.py`, `repl.py`,
`__main__.py` and `config.py` ship no systems, no components beyond `Said`
and `Reply`, no vocabulary and no knowledge of files; the config file names callables, it does not ship any,
and `config.py` imports nothing it names. `harneskills/examples/` is
different on purpose: worked demonstrations, each an `install(loop)` the
config or the command line can name, never imported unless you ask for it
by name.

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
gap is closed. `pytest` is 99 checks, 0 failing, and every transcript
above was run.

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
