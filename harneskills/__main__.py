"""HarneSkills: a prompt over an entity-component world and the systems
that change it.

    python -m harneskills [--config PATH | --no-config]
                          [--state PATH | --no-state] [module:callable ...]

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
from . import save
from .loop import Loop


def _split_argv(argv) -> "tuple[list[str], str, str, bool]":
    """`(specs, config, state, ok)` -- flags out, domain specs left alone.

    `config` is the config file to read and `state` the world to restore,
    each already defaulted, or None for its `--no-` flag. Hand-rolled
    rather than argparse because the whole grammar is four flags and a
    list of specs.
    """
    specs, rest = [], list(argv)
    named = {"--config": None, "--state": None}
    skipped = {"--config": False, "--state": False}
    default = {"--config": cfg.config_path, "--state": cfg.state_path}
    while rest:
        arg = rest.pop(0)
        flag, _, inline = arg.partition("=")
        if flag in ("--no-config", "--no-state"):
            if inline:
                print("! %s takes no argument" % flag, file=sys.stderr)
                return [], None, None, False
            skipped["--" + flag[len("--no-"):]] = True
        elif flag in named:
            if not inline and not rest:
                print("! %s needs an argument" % flag, file=sys.stderr)
                return [], None, None, False
            named[flag] = inline or rest.pop(0)
        elif arg.startswith("-"):
            print("! no such option: %s" % arg, file=sys.stderr)
            return [], None, None, False
        else:
            specs.append(arg)
    for flag in named:
        if skipped[flag] and named[flag] is not None:
            print("! %s and --no-%s say opposite things"
                  % (flag, flag[2:]), file=sys.stderr)
            return [], None, None, False
    settled = {flag: None if skipped[flag] else (named[flag] or default[flag]())
               for flag in named}
    return specs, settled["--config"], settled["--state"], True


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


def build(where, specs, state=None) -> Loop:
    """A loop with the world restored, then every domain installed.

    Called once at startup and again for every `/reload` -- which is why
    it re-reads the config file rather than closing over what it said the
    first time. Add a line to `~/.config/harneskills/config`, type
    `/reload`, and that domain is in the session without leaving it.

    `state` is a path to restore from, or None to start empty -- which is
    what `/reset` passes, and what `--no-state` means for the whole
    session. The order here is load-then-install and it matters; see this
    module's docstring.
    """
    standing = cfg.read_domains(where) if where is not None else []
    loop = Loop()
    problems = []
    if state is not None:
        problems += ["state: %s" % p for p in save.read(loop.world, state)]
        if len(loop.world):
            print("restored %d entities from %s" % (len(loop.world), state))
    wanted = standing + [s for s in specs if s not in standing]
    problems += install(loop, wanted)
    for problem in problems:
        print("  ! %s" % problem, file=sys.stderr)
    installed = [s for s in wanted if not any(p.startswith(s + ":") for p in problems)]
    if installed:
        print("installed:", ", ".join(installed))
    else:
        print("no domains installed -- nothing will understand what you type;"
              " try `python -m harneskills harneskills.examples.fs:install`")
    return loop


def _keeper(state):
    """`on_settle(loop)` -- write the world down every time it stops moving.

    Every settle, not on the way out: a prompt living in a service is
    killed, not quit. Skipped when nothing has changed since the last
    write, so reading `/systems` or typing a line nobody understood costs
    nothing.

    A save that fails is said once per distinct complaint and then the
    session goes on. Losing the world on a full disk is bad; refusing to
    talk to you about it as well is worse.
    """
    written, complained = {}, set()

    def keep(loop):
        world = loop.world
        if state is None or written.get(id(world)) == world.revision:
            return
        try:
            save.write(world, state)
        except (OSError, save.SaveError) as e:
            if str(e) not in complained:
                complained.add(str(e))
                print("  ! state: %s" % e, file=sys.stderr)
            return
        written[id(world)] = world.revision
    return keep


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    specs, where, state, ok = _split_argv(argv)
    if not ok:
        return 2

    def reload_(arg):
        """re-import every domain; the world comes back with it"""
        print("  reloading -- the code is re-read, the world is restored")
        return build(where, specs, state)

    def reset_(arg):
        """re-import every domain and start the world EMPTY"""
        print("  resetting -- everything this world knew is gone")
        return build(where, specs, None)

    loop = build(where, specs, state)
    return repl.run(loop, on_settle=_keeper(state),
                    commands={"/reload": reload_, "/reset": reset_})


if __name__ == "__main__":
    raise SystemExit(main())
