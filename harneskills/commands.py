"""The command vocabulary, as data, and the dispatcher over it.

UI-agnostic on purpose: the TUI, the plain REPL and the tests all go through
`dispatch`, so there is one place where a verb is defined and one place where it
is refused. The completion list, the help text and the dispatcher are all
rendered from `COMMANDS` -- so a verb cannot exist without help, and help cannot
describe a verb that is gone.

**The input language is the corpus language.** A line beginning `rule`, `fact` or
`say` is fed straight to the loader, unchanged. That is not a shortcut; it is the
point. UGM's surface already has exactly one grammar for authoring knowledge, and
a harness that invented a second one for typing it interactively would be a
second grammar to keep in sync and a second thing to be wrong about. So an
interactive session is one document that happens to arrive slowly, and anything
you can type you can paste into a `.ugm` file and vice versa.

Anything else that is not a slash command is read as a *term to ask about* --
`boiling(kettle)` -- because that is what a bare noun phrase means when a person
types it at a reasoner.
"""

from __future__ import annotations

from typing import Callable, Dict, List, NamedTuple, Optional, Sequence

from . import view
from .runner import RunnerError

#: Statement keywords the loader owns. A line starting with one of these is
#: corpus text, not a command.
CORPUS_KEYWORDS = ("rule", "fact", "say")


class Response(NamedTuple):
    """What a command produced, for whatever is displaying it."""

    lines: List[str]
    ok: bool = True
    #: The graph changed, so a viewer should re-read its projections. Set by
    #: anything that writes or thinks, and by nothing that only looks.
    changed: bool = False
    #: A long-running drive the UI should run on a worker rather than inline.
    drive: Optional[int] = None   # tick budget, or None


class Command(NamedTuple):
    name: str
    args: str
    help: str
    fn: Callable[..., Response]


def _ok(*lines: str, changed: bool = False) -> Response:
    return Response(list(lines), True, changed)


def _err(*lines: str) -> Response:
    return Response(list(lines), False, False)


# -- authoring --------------------------------------------------------------


def cmd_load(r, rest: str) -> Response:
    parts = rest.split()
    if not parts:
        return _err("/load needs a path to a .ugm corpus")
    path, scope = parts[0], (parts[1] if len(parts) > 1 else None)
    try:
        n = r.feed_file(path, scope)
    except FileNotFoundError:
        return _err(f"no such corpus: {path}")
    except RunnerError as exc:
        return _err(str(exc))
    return _ok(f"loaded {path}: {n} statements"
               + (f" into scope {scope}" if scope else ""), changed=True)


def cmd_scope(r, rest: str) -> Response:
    name = rest.strip()
    if not name:
        return _ok(f"scope is {r.scope}; known: " + ", ".join(sorted(r._loaders)) or r.scope)
    r.scope = name
    r.loader(name)
    return _ok(f"scope is now {name}", changed=True)


def corpus_line(r, line: str) -> Response:
    """A `rule` / `fact` / `say` statement, straight to the loader."""
    try:
        n = r.feed(line, label="typed")
    except RunnerError as exc:
        return _err(str(exc))
    return _ok(f"wrote {n} statement" + ("s" if n != 1 else ""), changed=True)


def cmd_say(r, rest: str) -> Response:
    """`/say user: +raining(here)` -- the same thing the `say` keyword does, kept
    as a verb because a person reaching for a slash command should find it."""
    return corpus_line(r, "say " + rest)


# -- thinking ---------------------------------------------------------------


def cmd_step(r, rest: str) -> Response:
    try:
        n = int(rest) if rest.strip() else 1
    except ValueError:
        return _err("/step takes a number of ticks")
    lines: List[str] = []
    for _ in range(max(1, n)):
        s = r.step()
        lines.extend(view.step_lines(r.machine, s))
        if s.state in ("quiescent", "stopped"):
            break
    return Response(lines, True, changed=True)


def cmd_run(r, rest: str) -> Response:
    try:
        limit = int(rest) if rest.strip() else r.limit
    except ValueError:
        return _err("/run takes a tick limit")
    return Response([], True, changed=True, drive=limit)


# -- looking ----------------------------------------------------------------


def cmd_report(r, rest: str) -> Response:
    lines = r.report()
    return _ok(*(lines or ["nothing was asked for, so there is nothing to report"]))


def cmd_why(r, rest: str) -> Response:
    if not rest.strip():
        return _err("/why needs a term, e.g. /why boiling(kettle)")
    try:
        return _ok(*r.why(rest.strip()))
    except RunnerError as exc:
        return _err(str(exc))


def cmd_holds(r, rest: str) -> Response:
    term = rest.strip()
    if not term:
        return _err("/holds needs a term")
    try:
        sign = r.holds(term)
    except RunnerError as exc:
        return _err(str(exc))
    if sign is None:
        return _ok(f"{term}: nothing settles it")
    return _ok(f"{term}: {view.STATUS_WORDS.get(sign, sign)} ({sign})")


def cmd_graph(r, rest: str) -> Response:
    """The propositions, filtered by layer. `/graph` alone shows the world."""
    args = rest.split()
    generic = "--generic" in args or "-g" in args
    layers = [a for a in args if not a.startswith("-")]
    bad = [a for a in layers if a not in view.LAYERS]
    if bad:
        return _err(f"unknown layer(s): {', '.join(bad)}",
                    "layers: " + ", ".join(view.LAYERS))
    rows = view.propositions(r.machine, layers or ["world"], generic=generic)
    if not rows:
        return _ok("nothing there yet")
    out = [f"{p.sign}{p.text}"
           + f"   [{p.status}, {p.layer}, M{p.moment}"
           + (f", via {p.source}" if p.source else "")
           + "]"
           for p in rows]
    return _ok(*out)


def cmd_rules(r, rest: str) -> Response:
    bundled = "--all" in rest
    rows = view.rules(r.machine, bundled=bundled)
    if not rows:
        return _ok("no rules authored yet (try /rules --all for the engine's own)")
    out = []
    for row in rows:
        mark = "*" if row.exercised else " "
        tag = " (bundled)" if row.bundled else ""
        out.append(f"{mark} <{row.name}> = {row.connective}{tag}")
        out.append(f"    when  {', '.join(row.antecedent) or '-'}")
        out.append(f"    then  {', '.join(row.consequent) or '-'}")
    out.append("")
    out.append("* = it has applied at least once")
    return _ok(*out)


def cmd_tools(r, rest: str) -> Response:
    rows = view.tools(r.machine)
    if not rows:
        return _ok("no tools registered")
    return _ok(*[f"<{n}> answers {req}" + ("" if trusted else "   (retired)")
                 for n, req, trusted in rows])


def cmd_channels(r, rest: str) -> Response:
    rows = view.channels(r.machine)
    return _ok(*[f"{name}: {n} arrival" + ("s" if n != 1 else "") for name, n in rows])


def cmd_credit(r, rest: str) -> Response:
    c = view.credit(r.machine)
    out: List[str] = []
    out.append("earned its keep:")
    out.extend("  " + l for l in c["review"] or ["  (nothing yet)"])
    out.append("to blame:")
    out.extend("  " + l for l in c["blame"] or ["  (nothing yet)"])
    return _ok(*out)


# -- sessions ---------------------------------------------------------------


def cmd_save(r, rest: str) -> Response:
    path = rest.strip()
    if not path:
        return _err("/save needs a path")
    r.save(path)
    return _ok(f"saved to {path}")


def cmd_resume(r, rest: str) -> Response:
    path = rest.strip()
    if not path:
        return _err("/resume needs a path")
    try:
        n = r.resume(path)
    except FileNotFoundError:
        return _err(f"no such session: {path}")
    return _ok(f"resumed {path}: {n} block(s), replayed without acting again",
               changed=True)


# -- playing ----------------------------------------------------------------


def cmd_scenarios(r, rest: str) -> Response:
    from . import play

    rows = play.available()
    if not rows:
        return _ok("nothing playable is installed")
    return _ok(*[f"{s.name:<10} {s.blurb}" for s in rows])


def cmd_play(r, rest: str) -> Response:
    """Load something playable, and stop. `/run` starts the clock."""
    from . import play

    parts = rest.split()
    if not parts:
        rows = play.available()
        return _err("/play needs a scenario",
                    *[f"  {s.name:<10} {s.blurb}" for s in rows])
    name, seed = parts[0], None
    if len(parts) > 1:
        try:
            seed = int(parts[1])
        except ValueError:
            return _err("the seed must be a whole number, e.g. /play dungeon 7")
    scenario = play.find(name)
    if scenario is None:
        return _err(f"no such scenario: {name}",
                    "known: " + ", ".join(s.name for s in play.available()))
    if r.scenario is not None:
        return _err(f"{r.scenario.name} is already loaded — start a new session for another")
    try:
        scenario.setup(r, seed)
    except FileNotFoundError as exc:
        return _err(str(exc))
    except RunnerError as exc:
        return _err(str(exc))
    r.scenario = scenario
    lines = [f"{scenario.name}: {scenario.blurb}"]
    if seed is not None:
        lines.append(f"seeded {seed} — the same fight every time, and `why` can reach the roll")
    else:
        lines.append("unseeded — a genuinely external die")
    lines.append("")
    lines.extend(scenario.status(r))
    lines.append("")
    lines.append("/run to start the clock; it will stop when it needs your word.")
    return Response(lines, True, changed=True)


def cmd_state(r, rest: str) -> Response:
    if r.scenario is None:
        return _err("nothing is being played — /scenarios lists what there is")
    return _ok(*r.scenario.status(r))


def cmd_help(r, rest: str) -> Response:
    out = ["Type `rule` / `fact` / `say` statements directly -- the input",
           "language is the corpus language. A bare term asks whether it holds.",
           ""]
    width = max(len(c.name) + len(c.args) + 1 for c in COMMANDS)
    for c in COMMANDS:
        sig = f"{c.name} {c.args}".rstrip()
        out.append(f"  {sig:<{width + 2}} {c.help}")
    out.append("")
    out.append("layers for /graph:")
    for name in view.LAYERS:
        out.append(f"  {name:<8} {view.LAYER_HELP[name]}")
    return _ok(*out)


COMMANDS: Sequence[Command] = (
    Command("/play", "<scenario> [seed]", "load something playable", cmd_play),
    Command("/scenarios", "", "what there is to play", cmd_scenarios),
    Command("/state", "", "the scoreboard of what is being played", cmd_state),
    Command("/load", "<path> [scope]", "load a .ugm corpus", cmd_load),
    Command("/scope", "[name]", "which name table new statements resolve in", cmd_scope),
    Command("/say", "<channel>: <term>", "the world speaks on a channel", cmd_say),
    Command("/step", "[n]", "think for one tick (or n)", cmd_step),
    Command("/run", "[limit]", "think until there is nothing left", cmd_run),
    Command("/report", "", "what became of what was asked for", cmd_report),
    Command("/why", "<term>", "why it believes that, and on whose word", cmd_why),
    Command("/holds", "<term>", "whether a term is held, denied or unsettled", cmd_holds),
    Command("/graph", "[layer...] [-g]", "the propositions, by layer", cmd_graph),
    Command("/rules", "[--all]", "the rules, and which have applied", cmd_rules),
    Command("/tools", "", "registered answerers, and which are trusted", cmd_tools),
    Command("/channels", "", "channels, and what has arrived on them", cmd_channels),
    Command("/credit", "", "which rules earned their keep, and which are to blame", cmd_credit),
    Command("/save", "<path>", "write the session as what it was told", cmd_save),
    Command("/resume", "<path>", "re-live a saved session without re-doing it", cmd_resume),
    Command("/help", "", "this", cmd_help),
)

_BY_NAME: Dict[str, Command] = {c.name: c for c in COMMANDS}


def dispatch(r, line: str) -> Response:
    """Read one line of input and do what it says."""
    text = line.strip()
    if not text:
        return _ok()
    if text.startswith("#"):
        return _ok()
    head = text.split(None, 1)[0]
    if head in CORPUS_KEYWORDS:
        return corpus_line(r, text)
    if text.startswith("/"):
        cmd = _BY_NAME.get(head)
        if cmd is None:
            near = [c.name for c in COMMANDS if c.name.startswith(head[:3])]
            return _err(f"no such command: {head}",
                        *( [f"did you mean {', '.join(near)}?"] if near else
                           ["/help lists them"] ))
        rest = text[len(head):].strip()
        return cmd.fn(r, rest)
    # A bare term is a question about it. Answer with the verdict AND the trail,
    # because *is it true* and *why do you say so* are one question when a
    # person types a proposition at a reasoner.
    verdict = cmd_holds(r, text)
    if not verdict.ok:
        return verdict
    trail = r.why(text)
    return _ok(*verdict.lines, *("  " + l for l in trail))
