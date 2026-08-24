"""HarneSkills: a plain terminal REPL over a UGM corpus.

    python -m harneskills [--config PATH | --no-config] [corpus.ugm ...]

A thin door onto `harneskills.repl`, itself carved out of `ugm.repl`
unchanged -- see that module's docstring for what typing at the prompt
means. This file contributes nothing beyond wiring: a fresh `Machine`, one
`Loader` for the session, the corpora to load, then a handoff to the REPL
loop. It knows nothing about any particular domain -- a UGM-side corpus
(e.g. `ugm/rules/fs/` upstream, loaded via its own `ugm.fs_repl` entry
point) brings its own tools and rules; HarneSkills is the terminal, not the
domain.

"The corpora to load" is two lists, in this order: the standing ones, from
the folders named in `~/.config/harneskills/config` (see
`harneskills.config`), then whatever is named on the command line. Standing
first because the command line is what you are saying NOW, and it should be
able to answer what was already there. `--no-config` skips the file
entirely -- the escape hatch for the session where the standing corpus is
the thing you are debugging.
"""

import sys

from ugm.core.machine import Machine
from ugm.core.text import ParseError, load

from . import config as cfg
from . import repl


def _split_argv(argv) -> "tuple[list[str], str, bool]":
    """`(paths, where, ok)` -- flags out, corpora left alone.

    `where` is the config file to read, already defaulted, or None for
    `--no-config`. Hand-rolled rather than argparse because the whole
    grammar is two flags and a list of files, and because a `.ugm` path
    beginning with a dash is a thing argparse would take from us.
    """
    paths, named, skip, rest = [], None, False, list(argv)
    while rest:
        arg = rest.pop(0)
        if arg == "--no-config":
            skip = True
        elif arg == "--config":
            if not rest:
                print("! --config needs a path", file=sys.stderr)
                return [], None, False
            named = rest.pop(0)
        elif arg.startswith("--config="):
            named = arg[len("--config="):]
        else:
            paths.append(arg)
    if skip and named is not None:
        print("! --config and --no-config say opposite things", file=sys.stderr)
        return [], None, False
    if skip:
        return paths, None, True
    return paths, (named or cfg.config_path()), True


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    paths, where, ok = _split_argv(argv)
    if not ok:
        return 2

    standing = []
    if where is not None:
        standing, problems = cfg.corpus_files(cfg.read_folders(where))
        # A folder named in the config that isn't there is worth saying out
        # loud once, on stderr, and then continuing: the session is fine
        # without it, and a config outliving one of its checkouts is normal.
        for problem in problems:
            print("  ! config: %s" % problem, file=sys.stderr)

    m = Machine()
    ldr = load(m, "", scope="harneskills")
    loaded = []
    for path in standing + paths:
        # A corpus that will not load must not take the session with it.
        # Standing corpora are loaded by a machine nobody is watching --
        # under a service, an exception here is a restart loop, and the one
        # thing you cannot do about it is read the traceback. So: say which
        # file and why, on stderr, and go on with the ones that did load.
        # ⚠ `ldr.load` is not transactional. A corpus that fails PART WAY
        # leaves its earlier statements in the machine, and there is no
        # rollback to reach for -- which is why the message says `partly
        # loaded` rather than pretending the file was skipped whole.
        try:
            with open(path, "r", encoding="utf-8") as fh:
                ldr.load(fh.read())
        except OSError as e:
            print("  ! %s: %s" % (path, e.strerror or e), file=sys.stderr)
            continue
        except ParseError as e:
            print("  ! %s: partly loaded, then: %s" % (path, e), file=sys.stderr)
            continue
        loaded.append(path)
    if loaded:
        print("loaded:", ", ".join(loaded))
    return repl.run(m, ldr)


if __name__ == "__main__":
    raise SystemExit(main())
