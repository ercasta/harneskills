"""HarneSkills: a plain terminal REPL over a UGM corpus.

    python -m harneskills [corpus.ugm ...]

A thin door onto `harneskills.repl`, itself carved out of `ugm.repl`
unchanged -- see that module's docstring for what typing at the prompt
means. This file contributes nothing beyond wiring: a fresh `Machine`, one
`Loader` for the session, whatever corpora are named on the command line
loaded in order, then a handoff to the REPL loop. It knows nothing about
any particular domain -- a UGM-side corpus (e.g. `ugm/rules/fs/` upstream,
loaded via its own `ugm.fs_repl` entry point) brings its own tools and
rules; HarneSkills is the terminal, not the domain.
"""

import sys

from ugm.core.machine import Machine
from ugm.core.text import load

from . import repl


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    m = Machine()
    ldr = load(m, "", scope="harneskills")
    loaded = []
    for path in argv:
        with open(path, "r", encoding="utf-8") as fh:
            ldr.load(fh.read())
        loaded.append(path)
    if loaded:
        print("loaded:", ", ".join(loaded))
    return repl.run(m, ldr)


if __name__ == "__main__":
    raise SystemExit(main())
