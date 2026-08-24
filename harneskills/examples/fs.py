"""The filesystem example's Python half.

    python -m harneskills --tools harneskills.examples.fs:register examples/fs

`register` binds `fs_tools`'s three answerers, the five computators the
shipped corpus reads, an `approve` tool that asks at the terminal, and the
`now`/`cwd` facts the corpus reads. Carved out of `ugm.fs_repl` with the
imports repointed at `ugm` as an ordinary dependency, and the two corpora
(`circuit_breaker.ugm`, `fs/fs_demo.ugm`) copied into this repo's own
`examples/` rather than read from ugm's package data -- an example should
not reach into another package's internal `rules/` layout, which is that
package's own implementation detail, not a public path.

⚠ There is no `harneskills-fs` entry point any more, and no `build()` that
loads `examples/` behind your back. It was a second way to start a session,
with its own hardcoded corpus list, and it meant this repo's copy of
`fs_demo.ugm` and yours could drift with nothing to say which was running.
Now there is one way in -- `python -m harneskills` -- and the corpus is
whatever you point it at, on the command line, with `/load`, or from
`~/.config/harneskills/config`. `circuit_breaker.ugm` is shared
infrastructure (any domain might watch a rule) and sorts before
`fs_demo.ugm`, which is the order a folder load gives them anyway.
"""

import os
import time

from ugm.core.text import Loader

from . import fs_tools


def _computators(ldr: Loader) -> None:
    def age_days(now, created):
        return (int(now) - int(created)) // 86400

    def at_least(age, days):
        return "yes" if int(age) >= int(days) else None

    def prefixed(name):
        return f"stale-{name}"

    def plus(a, b):
        return int(a) + int(b)

    def minus(a, b):
        return max(0, int(a) - int(b))

    ldr.computator("age_days", age_days)
    ldr.computator("at_least", at_least)
    ldr.computator("prefixed", prefixed)
    ldr.computator("plus", plus)
    ldr.computator("minus", minus)


def register(ldr: Loader, ask=input) -> None:
    """Everything `examples/fs/` leans on that is Python, onto any loader.

    Three tools, five computators, the `approve` prompt, and two facts --
    `now`, because the corpus reads `+now($t)` to age a file, and `cwd`,
    because it reads `+cwd($dir)` to know where a bare `show files` means.
    A machine that never wrote them simply never fires those rules.

    Split out of `build` so that a config file can name it:

        tools: harneskills.examples.fs:register

    which is called as `register(loader)` -- `ask` defaulting to `input`,
    the terminal being where a standing session lives. Nothing here is
    fs-specific apparatus; it is the ordinary shape of a domain's Python
    half, and any other domain's would be a function of the same signature.
    """
    fs_tools.register(ldr)
    _computators(ldr)

    def approve(mach, prop):
        said = ask(f"approve {mach.g.show(prop)}? [y/N] ").strip().lower()
        return ldr.atom("yes" if said in ("y", "yes") else "no")

    ldr.answerer("approve", "pending", approve)

    m = ldr.m
    # Read once, at registration, and never again: a session that has been
    # open an hour should age files against the clock it started with, and
    # `show files` should mean the directory you launched in even after a
    # tool has walked somewhere else.
    for head, value in (("now", str(int(time.time()))), ("cwd", os.getcwd())):
        node = m.g.rel(ldr.atom(head), ldr.atom(value))
        if not m.pad.holds(node):
            m.gate.write(node)
