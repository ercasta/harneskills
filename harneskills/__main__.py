"""HarneSkills: a plain terminal REPL over a UGM corpus.

    python -m harneskills [--config PATH | --no-config]
                          [--tools MODULE:CALLABLE ...] [corpus.ugm | folder ...]

A thin door onto `harneskills.repl`, itself carved out of `ugm.repl` and
kept close to it -- see that module's docstring for what typing at the
prompt means. This file contributes nothing beyond wiring: a fresh `Machine`, one
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

`build` is separate from `main` because `/reload` runs it again: a rule you
have just edited cannot be loaded over the one already in the machine, so
re-reading a corpus means a whole new machine, and the REPL loop swaps to
it. `/reset` is the same act under the name people reach for when the mess
is theirs rather than the corpus's.

Before either list, the `tools:` lines: `module:callable`, imported and
called as `callable(loader)`. A domain whose rules lean on Python -- an
answerer, a computator -- gets to bring that half along, because a rule
mentioning `<approve>` will not parse until something has registered it.
This is still not the harness knowing a domain: it imports what the config
names, the same way it opens the folders the config names, and it ships
neither.
"""

import importlib
import os
import sys

from ugm.core.machine import Machine
from ugm.core.text import Loader, ParseError, load

from . import config as cfg
from . import repl


def _split_argv(argv) -> "tuple[list[str], str, list[str], bool]":
    """`(paths, where, tools, ok)` -- flags out, corpora left alone.

    `where` is the config file to read, already defaulted, or None for
    `--no-config`. `--tools` is the config's `tools:` line spelled on the
    command line, repeatable, and it is what makes `--no-config` usable at
    all: a domain's Python half has to come from somewhere, and someone who
    has just cloned this repo should not have to write a config file in
    their home directory to try the thing out.

    Hand-rolled rather than argparse because the whole grammar is three
    flags and a list of paths, and because a `.ugm` path beginning with a
    dash is a thing argparse would take from us.
    """
    paths, tools, named, skip, rest = [], [], None, False, list(argv)
    while rest:
        arg = rest.pop(0)
        if arg == "--no-config":
            skip = True
        elif arg in ("--config", "--tools"):
            if not rest:
                print("! %s needs an argument" % arg, file=sys.stderr)
                return [], None, [], False
            if arg == "--config":
                named = rest.pop(0)
            else:
                tools.append(rest.pop(0))
        elif arg.startswith("--config="):
            named = arg[len("--config="):]
        elif arg.startswith("--tools="):
            tools.append(arg[len("--tools="):])
        else:
            paths.append(arg)
    if skip and named is not None:
        print("! --config and --no-config say opposite things", file=sys.stderr)
        return [], None, [], False
    return paths, (None if skip else (named or cfg.config_path())), tools, True


def _register_tools(ldr, specs) -> "list[str]":
    """Import each `module:callable` and hand it the loader. Returns problems.

    ⚠ The bare `except` around the call is deliberate and is NOT laziness.
    What is being called is arbitrary code named by a text file -- there is
    no exception type it is entitled to raise and no type it is forbidden
    to. The choice is between naming the spec and going on, or a service
    that restart-loops on somebody's typo with the traceback going nowhere
    anyone can read it. A domain that failed to register is a corpus that
    will fail to parse a moment later, and that message names the file.
    """
    problems = []
    for spec in specs:
        module_name, sep, attr = spec.partition(":")
        module_name, attr = module_name.strip(), attr.strip()
        if not sep or not module_name or not attr:
            problems.append("%s: expected module:callable" % spec)
            continue
        try:
            fn = getattr(importlib.import_module(module_name), attr)
        except ImportError as e:
            problems.append("%s: %s" % (spec, e))
            continue
        except AttributeError:
            problems.append("%s: no %s in %s" % (spec, attr, module_name))
            continue
        if not callable(fn):
            problems.append("%s: %s is not callable" % (spec, attr))
            continue
        try:
            fn(ldr)
        except Exception as e:  # noqa: BLE001 -- see the note above
            problems.append("%s: %s: %s" % (spec, type(e).__name__, e))
    return problems


def build(where, paths, cli_tools=()) -> "tuple[Machine, Loader]":
    """A machine with the config's tools registered and every corpus loaded.

    Called once at startup and again for every `/reload` -- which is why it
    re-reads the config file rather than closing over what it said the first
    time. Edit `~/.config/harneskills/config`, type `/reload`, and the new
    folder is in the session without leaving it.
    """
    standing, tools, problems = [], [], []
    if where is not None:
        folders, tools = cfg.read_config(where)
        # A folder named in the config that isn't there is worth saying out
        # loud once, on stderr, and then continuing: the session is fine
        # without it, and a config outliving one of its checkouts is normal.
        standing, problems = cfg.corpus_files(folders)
    tools = tools + list(cli_tools)

    # A path on the command line may be a folder too, read the same one
    # level deep -- so `examples/fs` means what `/load examples/fs` means.
    named_paths, named_problems = [], []
    for path in paths:
        if os.path.isdir(path):
            found, trouble = cfg.corpus_files([path])
            named_paths += found
            named_problems += trouble
        else:
            named_paths.append(path)
    problems += named_problems

    m = Machine()
    ldr = load(m, "", scope="harneskills")
    # Tools first, and before ANY corpus: a `.ugm` rule referring to an
    # answerer that does not exist yet is a parse error, not a late binding.
    problems += _register_tools(ldr, tools)
    for problem in problems:
        print("  ! config: %s" % problem, file=sys.stderr)

    loaded = []
    for path in standing + named_paths:
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
    return m, ldr


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    paths, where, tools, ok = _split_argv(argv)
    if not ok:
        return 2

    def reload_(arg):
        """start over: re-read the config and every corpus from disk"""
        print("  reloading -- everything typed this session is gone")
        return build(where, paths, tools)

    m, ldr = build(where, paths, tools)
    # Two names for one act, because both are things people mean by it: you
    # edited a rule and want it in, or you made a mess and want it out. UGM
    # gives no way to tell them apart -- a rule cannot be redeclared into a
    # machine that has it, so either way the answer is a new machine built
    # from the same sources.
    return repl.run(m, ldr, commands={"/reload": reload_, "/reset": reload_})


if __name__ == "__main__":
    raise SystemExit(main())
