"""The event vocabulary between the driver thread and the screen.

The screen never touches the machine on a worker thread and the worker never
touches a widget: everything crosses on these. Keeping the list short is
deliberate -- each one is a thing the UI has to be able to render, and a driver
that needed a ninth event would be doing something the transcript cannot show.
"""

from __future__ import annotations

from typing import List, Optional

from textual.message import Message


class Ticked(Message):
    """One tick happened. `lines` is already rendered for the transcript."""

    def __init__(self, index: int, state: str, lines: List[str]) -> None:
        super().__init__()
        self.index = index
        self.state = state
        self.lines = lines


class Drove(Message):
    """A `/run` finished: how many ticks, and which silence it ended in."""

    def __init__(self, ticks: int, state: str, stopped_early: bool) -> None:
        super().__init__()
        self.ticks = ticks
        self.state = state
        self.stopped_early = stopped_early


class Acted(Message):
    """Something crossed the outbound boundary -- the agent did it."""

    def __init__(self, what: str) -> None:
        super().__init__()
        self.what = what


class Asked(Message):
    """A person's word is owed, and the driver is blocked until it comes.

    Two things raise this and they are deliberately one message: the `ask` tool,
    where the agent wanted to know something, and a cue, where the machine
    reached a state a player speaks into. `options` is what the scenario thinks
    are reasonable answers — a hint, never a menu, because the input language is
    still the corpus language.
    """

    def __init__(self, question: str, options: Optional[List[str]] = None) -> None:
        super().__init__()
        self.question = question
        self.options = list(options or ())


class Declared(Message):
    """A cue was answered and something was said on the scenario's channel."""

    def __init__(self, said: Optional[str]) -> None:
        super().__init__()
        self.said = said


class Answered(Message):
    """...and it was answered (or declined, when `reply` is None)."""

    def __init__(self, reply: Optional[str]) -> None:
        super().__init__()
        self.reply = reply


class Noted(Message):
    """Plain output from a command, already formatted."""

    def __init__(self, lines: List[str], ok: bool = True) -> None:
        super().__init__()
        self.lines = lines
        self.ok = ok


class Failed(Message):
    """The driver raised. Shown, never swallowed -- a harness that hides an
    engine error is the one thing worse than an engine error."""

    def __init__(self, error: str) -> None:
        super().__init__()
        self.error = error
