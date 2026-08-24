"""The filesystem REPL example.

    harneskills-fs [corpus.ugm ...]

Wires `fs_tools`'s answerers, the four computators the shipped corpus reads,
and an `approve` tool that asks at the terminal, then hands off to
`harneskills.repl`. Carved out of `ugm.fs_repl`, unmodified beyond: imports
repointed at the `ugm` package as an ordinary dependency, and the two
corpora (`circuit_breaker.ugm`, `fs/fs_demo.ugm`) copied into this repo's
own `examples/` rather than read from ugm's package data -- an example
should not reach into another package's internal `rules/` layout, which is
that package's own implementation detail, not a public path. `circuit_breaker.ugm`
is shared infrastructure (any domain might watch a rule) and loads first,
always; everything under `examples/fs/` is THIS domain's own corpus and
loads next, whatever is there -- drop a `.ugm` file in that folder (a rename
policy of your own overriding `<hold-rename>`, a rule that reads
`<flag-stale>`'s facts) and it is picked up on the next run, no path to edit
here. Extra corpus paths on the command line load last, for a one-off
addition that is not meant to live in the folder.
"""

import os
import sys
import time
from pathlib import Path

from ugm.core.machine import Machine
from ugm.core.text import Loader, load

from .. import repl
from . import fs_tools

# `examples/` lives at the repo root, a sibling of the `harneskills` package
# -- not inside it -- because it is dev-time content for THIS checkout, not
# something a wheel install of `harneskills` promises to ship (see the
# top-level README's "Scope": HarneSkills bakes no domain into the package).
_EXAMPLES_DIR = Path(__file__).resolve().parent.parent.parent / "examples"


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


def build(ask=input) -> "tuple[Machine, Loader]":
    """A machine with the fs tools, the approval tool, `circuit_breaker.ugm`
    and everything under `examples/fs/` loaded, ready for
    `harneskills.repl.run`. `ask` is the approval prompt -- a function from a
    message to a line of text -- swappable for a test."""
    m = Machine()
    ldr = load(m, "", scope="fs")
    register(ldr, ask)

    with open(_EXAMPLES_DIR / "circuit_breaker.ugm", "r", encoding="utf-8") as fh:
        ldr.load(fh.read())
    loaded = []
    for corpus_path in sorted((_EXAMPLES_DIR / "fs").glob("*.ugm")):
        with open(corpus_path, "r", encoding="utf-8") as fh:
            ldr.load(fh.read())
        loaded.append(str(corpus_path))
    if loaded:
        print("loaded:", ", ".join(loaded))
    return m, ldr


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)

    def session() -> "tuple[Machine, Loader]":
        m, ldr = build()
        for path in argv:
            with open(path, "r", encoding="utf-8") as fh:
                ldr.load(fh.read())
        return m, ldr

    def reload_(arg):
        """start over: re-read every corpus from disk"""
        print("  reloading -- everything typed this session is gone")
        return session()

    m, ldr = session()
    return repl.run(m, ldr, commands={"/reload": reload_, "/reset": reload_})


if __name__ == "__main__":
    raise SystemExit(main())
