"""HarneSkills: a prompt over an entity-component world and the systems
that change it.

    python -m harneskills [--config PATH | --no-config] [module:callable ...]

A thin door onto `harneskills.repl`. This file contributes nothing beyond
wiring: a fresh `Loop` (which brings its own empty `World`), the domains to
install, then a handoff to the REPL.

"The domains to install" is two lists, in this order: the standing ones,
from `~/.config/harneskills/config` (see `harneskills.config`), then
whatever is named on the command line. Standing first because systems run
in installation order, and a domain you are naming NOW should get to see a
world the standing ones have already set up. `--no-config` skips the file
entirely -- the escape hatch for the session where the standing domain is
the thing you are debugging.

Every positional argument is a domain: `module:callable`, imported and
called as `callable(loop)`. There is no other kind of argument, because
there is no other kind of thing to load. Nothing about any domain is in
here -- `harneskills.examples.fs` is imported when, and only when,
something names it.

`build` is separate from `main` because `/reload` runs it again: a system
is a Python function, so picking up an edit means re-importing the module
AND starting the world over -- systems already registered cannot be
un-registered, and every component in the world was put there by the old
ones. The REPL loop swaps to the new `Loop`. `/reset` is the same act under the name
people reach for when the mess is theirs rather than the module's.
"""

from __future__ import annotations

import importlib
import sys

from . import config as cfg
from . import repl
from .loop import Loop


def _split_argv(argv) -> "tuple[list[str], str, bool]":
    """`(specs, where, ok)` -- flags out, domain specs left alone.

    `where` is the config file to read, already defaulted, or None for
    `--no-config`. Hand-rolled rather than argparse because the whole
    grammar is two flags and a list of specs.
    """
    specs, named, skip, rest = [], None, False, list(argv)
    while rest:
        arg = rest.pop(0)
        if arg == "--no-config":
            skip = True
        elif arg == "--config":
            if not rest:
                print("! --config needs an argument", file=sys.stderr)
                return [], None, False
            named = rest.pop(0)
        elif arg.startswith("--config="):
            named = arg[len("--config="):]
        elif arg.startswith("-"):
            print("! no such option: %s" % arg, file=sys.stderr)
            return [], None, False
        else:
            specs.append(arg)
    if skip and named is not None:
        print("! --config and --no-config say opposite things", file=sys.stderr)
        return [], None, False
    return specs, (None if skip else (named or cfg.config_path())), True


def install(loop, specs) -> "list[str]":
    """Import each `module:callable` and hand it the loop. Returns problems.

    ⚠ The bare `except` around the call is deliberate and is NOT laziness.
    What is being called is arbitrary code named by a text file -- there is
    no exception type it is entitled to raise and none it is forbidden to.
    The choice is between naming the spec and going on, or a service that
    restart-loops on somebody's typo with the traceback going nowhere
    anyone can read it. A domain that failed to install is a prompt that
    understands nothing you type, and this message is what says why.
    """
    problems = []
    for spec in specs:
        module_name, sep, attr = spec.partition(":")
        module_name, attr = module_name.strip(), attr.strip()
        if not sep or not module_name or not attr:
            problems.append("%s: expected module:callable" % spec)
            continue
        # `/reload` means "I edited that file" more often than not, and a
        # module already in `sys.modules` would otherwise be handed back
        # exactly as it was at startup -- a reload that reliably changed
        # nothing is worse than no reload at all. First time through,
        # importing IS reading it from disk, so there is nothing to redo.
        cached = module_name in sys.modules
        try:
            module = importlib.import_module(module_name)
            if cached:
                module = importlib.reload(module)
        except ImportError as e:
            problems.append("%s: %s" % (spec, e))
            continue
        fn = getattr(module, attr, None)
        if fn is None:
            problems.append("%s: no %s in %s" % (spec, attr, module_name))
            continue
        if not callable(fn):
            problems.append("%s: %s is not callable" % (spec, attr))
            continue
        try:
            loop.install(fn)
        except Exception as e:  # noqa: BLE001 -- see the note above
            problems.append("%s: %s: %s" % (spec, type(e).__name__, e))
    return problems


def build(where, specs) -> Loop:
    """A loop with every standing domain installed, then every named one.

    Called once at startup and again for every `/reload` -- which is why it
    re-reads the config file rather than closing over what it said the
    first time. Add a line to `~/.config/harneskills/config`, type
    `/reload`, and that domain is in the session without leaving it.
    """
    standing = cfg.read_domains(where) if where is not None else []
    loop = Loop()
    wanted = standing + [s for s in specs if s not in standing]
    problems = install(loop, wanted)
    for problem in problems:
        print("  ! %s" % problem, file=sys.stderr)
    installed = [s for s in wanted if not any(p.startswith(s + ":") for p in problems)]
    if installed:
        print("installed:", ", ".join(installed))
    else:
        print("no domains installed -- nothing will understand what you type;"
              " try `python -m harneskills harneskills.examples.fs:install`")
    return loop


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    specs, where, ok = _split_argv(argv)
    if not ok:
        return 2

    def reload_(arg):
        """start over: re-import every domain and empty the world"""
        print("  reloading -- everything this session learned is gone")
        return build(where, specs)

    loop = build(where, specs)
    # Two names for one act, because both are things people mean by it: you
    # edited a rule and want it in, or you made a mess and want it out.
    # Either way the answer is the same -- a new loop over a new world,
    # built from the same sources.
    return repl.run(loop, commands={"/reload": reload_, "/reset": reload_})


if __name__ == "__main__":
    raise SystemExit(main())
