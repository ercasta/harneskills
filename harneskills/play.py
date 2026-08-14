"""Playing: stopping the machine at the moments a person should speak into it.

The harness already had one way to consult a human -- the `ask` tool, where the
*agent* decides it wants to know something. This is the other way round, and a
game is what makes it necessary: nobody in the corpus asks the player anything.
The fight simply reaches a state -- *it is the hero's turn and nothing has been
declared* -- at which a person's word is owed, and if none arrives a standing
rule acts on their behalf.

So a **cue** is a state worth stopping at, and the whole mechanism is:

    after each tick, does any cue's `detect` return a context?
    if so, stop, ask the person, and `say` their answer on a channel.

⚠ The engine is not modified and neither is the corpus. A cue reads the graph
between ticks and speaks on an ordinary channel, which is exactly what a player
is: a channel the corpus decided to trust. `dungeon.ugm`'s `<trust-player>` turns
the utterance into an intention, and deleting that rule leaves the declarations
on the record believed by nobody -- which is the corpus's business, not ours.

⚠⚠ **Timing is the thing that had to be measured, not reasoned about.** The
declaration is injected between ticks and takes three of them to become an
intention (`arrived` → `says` → `intends`), while `<hero-holds>` -- the standing
policy that acts when the player has said nothing -- is a candidate the whole
time. Whether the declaration lands before the policy fires is a question about
authored order and per-step precedence, and the answer is *yes*: measured over a
whole fight, declaring `attack(goblin1)` every round leaves goblin1 dead and
goblin2 untouched at full hit points, and declaring `attack(goblin2)` does the
exact reverse. `tests/test_play.py` keeps that pair as the check, because it is
the only one that can tell a player apart from a spectator.
"""

from __future__ import annotations

from typing import Callable, Dict, List, NamedTuple, Optional, Sequence

from .runner import Runner


class Cue(NamedTuple):
    """A state at which the machine should stop and let a person speak.

    `detect` reads the graph and returns a context -- whatever the prompt and
    the utterance need -- or `None` for *not now*. It must be cheap: it runs
    after every tick.

    `utterance` turns the person's reply into a term to `say`. Returning `None`
    means the reply was not usable, and `speak` then falls through to `declined`
    -- so something still reaches the channel. Declining is a move, not a
    silence; see `declined` for why the difference is load-bearing.
    """

    name: str
    channel: str
    detect: Callable[[Runner], Optional[Dict[str, str]]]
    prompt: Callable[[Dict[str, str]], str]
    options: Callable[[Runner, Dict[str, str]], List[str]]
    utterance: Callable[[Dict[str, str], str], Optional[str]]
    #: What to say when the person declines, or says something the surface
    #: cannot parse. ⚠⚠⚠ **Something must always be said, and this is why.** A
    #: cue fires on a state; if a decline left the graph unchanged, the state
    #: would still be there on the next check and the person would be asked the
    #: same question for ever. Recording the pass on the channel is also the
    #: honest shape: *I was asked and I said nothing* is a fact about the world,
    #: it belongs on the graph like every other arrival, and what the corpus
    #: makes of it -- usually nothing, leaving a standing rule to act -- is the
    #: corpus's business. Returning `None` here opts out, and then the front end
    #: must guarantee progress some other way.
    declined: Optional[Callable[[Dict[str, str]], Optional[str]]] = None


class Scenario(NamedTuple):
    """Something playable: a corpus, the tools it needs, and where to stop."""

    name: str
    blurb: str
    #: Loads the corpus and registers the answerers. Everything a scenario needs
    #: that a `.ugm` file cannot say lives here, in one function, so that what is
    #: authored and what is wired stays visible at a glance.
    setup: Callable[[Runner, Optional[int]], None]
    cues: Sequence[Cue]
    #: The scoreboard, for the pane. Plain lines, read from the graph.
    status: Callable[[Runner], List[str]]
    #: The verdict, once there is one.
    over: Callable[[Runner], Optional[str]]
    #: The name scope the corpus is loaded under -- cues and status read in it.
    scope: str = "kb"


#: Registered scenarios, by name. A module adds itself by calling `register`,
#: which keeps the registry from importing every scenario at start-up.
SCENARIOS: Dict[str, Scenario] = {}


def register(scenario: Scenario) -> Scenario:
    SCENARIOS[scenario.name] = scenario
    return scenario


def available() -> List[Scenario]:
    """Every scenario that can actually be played right now.

    Importing is what decides it: a scenario whose corpus ships with an engine
    that is not installed simply does not register, and the list is short rather
    than wrong.
    """
    import importlib

    # Imported for its side effect: a scenario module registers itself. Done
    # here rather than at package import so that a broken or absent scenario
    # costs nothing until somebody asks what there is to play.
    for name in ("dungeon",):
        try:
            importlib.import_module(f"{__package__}.{name}")
        except ImportError:
            continue
    return [SCENARIOS[k] for k in sorted(SCENARIOS)]


def find(name: str) -> Optional[Scenario]:
    available()
    return SCENARIOS.get(name)


# -- the pause ---------------------------------------------------------------


def pending(r: Runner) -> Optional[tuple]:
    """`(cue, context)` if the machine has reached a state a person owes a word
    to, else `None`. Called between ticks by every front end.

    ⚠ Between ticks, deliberately -- not inside one. The `ask` tool consults a
    person from *within* a tick and therefore holds the runner lock for as long
    as they take; a cue holds nothing, because the machine is simply not running
    while it waits. That is the safer of the two shapes and it is available here
    only because a cue is the harness's idea rather than the corpus's.
    """
    scenario = getattr(r, "scenario", None)
    if scenario is None:
        return None
    for cue in scenario.cues:
        ctx = cue.detect(r)
        if ctx is not None:
            return cue, ctx
    return None


def speak(r: Runner, cue: Cue, ctx: Dict[str, str], reply: str) -> Optional[str]:
    """Turn a person's reply into an utterance on the cue's channel.

    Returns what was said. ⚠ A reply the surface cannot parse is not an error --
    the person typed prose at a term prompt -- and it is not silence either: it
    falls through to the cue's `declined` utterance, so the graph records that
    they were asked and the machine can move on. See `Cue.declined` for why
    silence is the one outcome a cue must never produce.
    """
    from .runner import RunnerError

    scope = getattr(r.scenario, "scope", None)
    term = cue.utterance(ctx, reply) if reply.strip() else None
    if term:
        try:
            r.say(cue.channel, term, scope=scope)
            return term
        except RunnerError:
            pass                       # unparseable: treat it as declining
    if cue.declined is None:
        return None
    term = cue.declined(ctx)
    if not term:
        return None
    try:
        r.say(cue.channel, term, scope=scope)
    except RunnerError:
        return None
    return term


# -- reading the graph, for cues and scoreboards -----------------------------
#
# Three helpers, because every scenario needs them and each is a place to get
# the read subtly wrong. They are here rather than in `view` because they answer
# *what is the state of play* rather than *what is on screen*.


def held(r: Runner, relation: str, scope: Optional[str] = None) -> List[int]:
    """Every ground instance of a relation that currently holds.

    ⚠ Ground only. A pattern like `hp(?x, ?n)` is a description and not a
    claim about anyone, and a scoreboard that counted them would report the
    corpus's variables as combatants.
    """
    m = r.machine
    rel = r.loader(scope).atom(relation)
    return [n for n in m.g.instances_of(rel)
            if not m.g.has_var(n) and m.holds(n) == "+"]


def members_of(r: Runner, node: int) -> List[str]:
    """A relation instance's arguments, as they would be written."""
    return [r.machine.g.show(x) for x in r.machine.g.members(node)]


def first_arg_match(r: Runner, relation: str, index: int, value: str,
                    scope: Optional[str] = None) -> Optional[List[str]]:
    """The arguments of the first holding instance whose `index`th is `value`."""
    for n in held(r, relation, scope):
        args = members_of(r, n)
        if index < len(args) and args[index] == value:
            return args
    return None
