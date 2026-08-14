"""HarneSkills -- a way to watch a UGM agent think.

UGM is an agent that plans, acts, observes and explains itself on one graph
substrate. Everything it does is already in that graph; what it has never had is
a door a person can stand at. This package is that door, and nothing else.

The scope is deliberate and narrow. HarneSkills was carved into an engine and a
harness precisely to separate them, so the test for anything proposed here is one
question -- *is this how a human sees, drives, or authors for UGM?* Planning,
arbitration, norms, procedures and provenance are the engine's, and re-growing
them here would be un-carving the split.

    harneskills.runner    a Machine, its corpora and name scopes, driven a tick
                          at a time; the only module holding engine state
    harneskills.view      read-only projections of a running machine: what holds,
                          what is wanted, what applied, why
    harneskills.commands  the verb vocabulary, as data, shared by every front end
    harneskills.play      cues: where a machine stops so a person can speak into it
    harneskills.dungeon   the engine's fight corpus, made playable
    harneskills.repl      a plain terminal front end, for when a TUI is too much

The TUI lives in `harneskills_tui` and is one more caller of the three above.
"""

from __future__ import annotations

from . import play
from .commands import COMMANDS, Response, dispatch
from .play import Cue, Scenario
from .runner import DEFAULT_SCOPE, Runner, RunnerError, Said
from .view import (
    LAYERS,
    LAYER_HELP,
    STATUS_WORDS,
    Prop,
    RuleRow,
    TreeRow,
    channels,
    counts,
    credit,
    goal_tree,
    propositions,
    rules,
    step_lines,
    tools,
    why,
)

__version__ = "0.1.0"

__all__ = [
    "COMMANDS",
    "Cue",
    "Scenario",
    "play",
    "DEFAULT_SCOPE",
    "LAYERS",
    "LAYER_HELP",
    "Prop",
    "Response",
    "STATUS_WORDS",
    "RuleRow",
    "Runner",
    "RunnerError",
    "Said",
    "TreeRow",
    "channels",
    "counts",
    "credit",
    "dispatch",
    "goal_tree",
    "propositions",
    "rules",
    "step_lines",
    "tools",
    "why",
    "__version__",
]
