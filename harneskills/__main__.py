"""HarneSkills: an entity-component world, and every door onto it.

    python -m harneskills [--config PATH | --no-config]
                          [--state PATH | --no-state]
                          [--serve[=HOST:PORT]] [--token TOKEN] [--headless]
                          [module:callable ...]

A thin door onto `ugm.engine`. This file contributes nothing
beyond wiring: a fresh `Engine` around a `Loop` (which brings its own
world), the domains to install, a `harneskills.repl.Terminal` attached to
it -- and, if asked, a `harneskills.serve.Listener` attached alongside it,
so a second door opens onto the SAME running world rather than a second
one. Nothing about any domain is in here -- `harneskills.examples.fs` is
imported when, and only when, something names it.

"The domains to install" is two lists, in this order: the standing ones,
from `~/.config/harneskills/config` (see `harneskills.config`), then
whatever is named on the command line. Standing first because systems run
in installation order, and a domain you are naming NOW should get to see a
world the standing ones have already set up. `--no-config` skips the file
entirely -- the escape hatch for the session where the standing domain is
the thing you are debugging.

## One process, several doors

`--serve` attaches a `harneskills.serve.Listener` beside the terminal --
not instead of it. Anyone at a WebSocket and whoever is sitting at this
terminal (tmux or otherwise) are looking at the same world, in the same
tick, and a reply to `user` reaches both. `--headless` is the other half:
no `Terminal` at all, for the case where this process IS the server and a
person drives it entirely through connections -- systemd's own idea of
"a service", not "a REPL somebody happens to be running as one".

`--token` names the token a client must present; without it, one is
generated (`os.urandom`) and written, with the host and port actually
bound, to `harneskills.config.server_path()` -- `harneskills/serve.py`'s
own note on why that file, and not the port alone, is the whole of the
security story.

`build` is separate from `main` because `/reload` runs it again: a system
is a Python function, so picking up an edit means re-importing the module
AND starting the world over -- systems already registered cannot be
un-registered, and every component in the world was put there by the old
ones. `/reload` restores the state file into the fresh world; `/reset` is
the same act with that skipped, so the world start EMPTY -- see
`ugm.engine`'s own `_command` for where those two land.
"""

from __future__ import annotations

import importlib
import json
import os
import sys

from ugm import save
from ugm.engine import Engine
from ugm.loop import Loop

from . import config as cfg
from . import repl
from . import serve

FLAGS = {
    "--config": "value", "--no-config": "flag",
    "--state": "value", "--no-state": "flag",
    "--serve": "optional", "--token": "value", "--headless": "flag",
}


def _split_argv(argv):
    """`(specs, options, ok)` -- flags out, domain specs left alone.

    `options` is `{"config": path_or_None, "state": path_or_None,
    "serve": (host, port)_or_None, "token": str_or_None, "headless":
    bool}`. Hand-rolled rather than argparse because a `module:callable`
    spec beginning with a dash is a thing argparse would take from us, and
    because the grammar is still small enough to read in one function.
    """
    specs, rest = [], list(argv)
    raw = {}
    while rest:
        arg = rest.pop(0)
        flag, _, inline = arg.partition("=")
        kind = FLAGS.get(flag)
        if kind is None:
            if arg.startswith("-") and arg not in FLAGS:
                print("! no such option: %s" % arg, file=sys.stderr)
                return [], None, False
            specs.append(arg)
            continue
        if kind == "flag":
            if inline:
                print("! %s takes no argument" % flag, file=sys.stderr)
                return [], None, False
            raw[flag] = True
        elif kind == "value":
            if not inline and not rest:
                print("! %s needs an argument" % flag, file=sys.stderr)
                return [], None, False
            raw[flag] = inline or rest.pop(0)
        else:   # "optional" -- --serve, with or without =HOST:PORT
            # The value, if there is one, may ONLY arrive via `=`. A bare
            # `--serve` followed by a separate token is ambiguous with a
            # domain spec that happens to come next on the command line
            # (`--serve fs:install` -- serve on the default address and
            # then install `fs`, or serve at the address named `fs:install`?
            # -- and there is no reading of the second that makes sense,
            # so only the first is offered. `ls --color[=WHEN]` draws the
            # same line for the same reason.
            raw[flag] = inline or True

    if "--no-config" in raw and "--config" in raw:
        print("! --config and --no-config say opposite things", file=sys.stderr)
        return [], None, False
    if "--no-state" in raw and "--state" in raw:
        print("! --state and --no-state say opposite things", file=sys.stderr)
        return [], None, False

    config = None if "--no-config" in raw else raw.get("--config") or cfg.config_path()
    state = None if "--no-state" in raw else raw.get("--state") or cfg.state_path()
    serve_at = None
    if "--serve" in raw:
        value = raw["--serve"]
        address = "" if value is True else value
        host, _, port = address.partition(":")
        try:
            serve_at = (host or "127.0.0.1", int(port) if port else 8765)
        except ValueError:
            print("! --serve wants HOST:PORT, not %r" % address, file=sys.stderr)
            return [], None, False
    if "--headless" in raw and serve_at is None:
        print("! --headless with no --serve is a process nothing drives",
              file=sys.stderr)
        return [], None, False
    options = {"config": config, "state": state, "serve": serve_at,
              "token": raw.get("--token"), "headless": "--headless" in raw}
    return specs, options, True


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
    session. The order here is load-then-install and it matters -- see
    `ugm.engine`'s own note on it.
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


def _write_server_file(path: str, host: str, port: int, token) -> None:
    """`server.json`, beside the world: how a client on this machine finds
    this process and proves it is allowed to. Written 0600 where the
    platform supports it -- a file only the account running this process
    can read is the whole of the authentication story
    (`harneskills.serve`'s own docstring)."""
    folder = os.path.dirname(path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"host": host, "port": port, "token": token}, fh)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass   # e.g. Windows, where this is not how a file is kept private


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    specs, options, ok = _split_argv(argv)
    if not ok:
        return 2
    where, state = options["config"], options["state"]

    def reload_(engine, arg):
        """re-import every domain; the world comes back with it"""
        print("  reloading -- the code is re-read, the world is restored")
        return build(where, specs, state)

    def reset_(engine, arg):
        """re-import every domain and start the world EMPTY"""
        print("  resetting -- everything this world knew is gone")
        return build(where, specs, None)

    loop = build(where, specs, state)
    engine = Engine(loop, on_settle=_keeper(state),
                    commands={"/reload": reload_, "/reset": reset_})

    if not options["headless"]:
        engine.attach(repl.Terminal())

    if options["serve"] is not None:
        host, port = options["serve"]
        token = options["token"] or os.urandom(18).hex()
        server_path = cfg.server_path()

        def announce(bound_host, bound_port, token_) -> None:
            _write_server_file(server_path, bound_host, bound_port, token_)
            print("serving on %s:%d -- details in %s"
                  % (bound_host, bound_port, server_path))

        engine.attach(serve.Listener(host=host, port=port, token=token,
                                     announce=announce))

    return engine.run()


if __name__ == "__main__":
    raise SystemExit(main())
