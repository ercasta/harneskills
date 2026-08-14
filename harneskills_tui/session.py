"""The driver: everything that touches the machine off the UI thread.

Two things happen here and nothing else does. A `/run` is driven tick by tick so
the transcript fills as it goes rather than arriving in one block at the end --
which is the whole reason `Runner.run` takes a per-step callback instead of just
returning a list. And the human-as-a-tool question is carried across the thread
boundary: the agent asks on the driver thread, the question is posted to the
screen, and the driver **blocks** until an answer comes back.

That blocking is not a compromise. The agent consulted a tool; reasoning past an
unanswered consultation would be reasoning past the question. What the harness
owes the person is a visible prompt and a way to decline -- both of which are
here -- not a way to carry on regardless.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import List, Optional

import harneskills as h
from harneskills import Runner, play

from .messages import Acted, Answered, Asked, Declared, Drove, Failed, Ticked


class SessionLog:
    """A plain-text transcript on disk, so a session outlives its window."""

    def __init__(self, session_dir: Path) -> None:
        session_dir.mkdir(parents=True, exist_ok=True)
        self._path = session_dir / "session.log"
        self._lock = threading.Lock()
        self._t0 = time.time()

    @property
    def path(self) -> Path:
        return self._path

    def write(self, line: str) -> None:
        elapsed = time.time() - self._t0
        with self._lock:
            with self._path.open("a", encoding="utf-8") as fh:
                fh.write(f"[+{elapsed:7.1f}s] {line}\n")


class Driver:
    """Drives one `Runner` on behalf of one screen."""

    def __init__(self, screen, runner: Optional[Runner] = None) -> None:
        self.screen = screen
        self.runner = runner or Runner()
        self.stop_requested = threading.Event()
        self.step_mode = False
        # The pending question, and the door the answer comes back through.
        self._answer: Optional[str] = None
        self._answered = threading.Event()
        self.question: Optional[str] = None
        self._cue_paused = False
        self.runner.set_oracle(self._ask)

    # -- consulting the person ----------------------------------------------

    def _consult(self, question: str, options: Optional[List[str]] = None) -> Optional[str]:
        """Ask, and block the driver thread until the screen answers.

        One door for both kinds of consultation -- the `ask` tool, where the
        agent wants to know something, and a cue, where the machine has reached
        a state a person owes a word to. They differ in *who* wanted the answer
        and in what happens if none comes; they do not differ in how a person
        gives one, so they do not get two prompts.
        """
        self.question = question
        self._answer = None
        self._answered.clear()
        self.screen.post_message(Asked(question, list(options or ())))
        while not self._answered.wait(timeout=0.1):
            if self.stop_requested.is_set():
                # Stopping is a decline, not a crash: *I have nothing to say* is
                # an answer both the engine and a corpus carry on from.
                self.question = None
                return None
        self.question = None
        return self._answer

    def _ask(self, question: str) -> Optional[str]:
        """The `ask` tool's door. ⚠ Called from *inside* a tick, so the runner
        lock is held for as long as the person takes -- which is why nothing on
        the UI thread may block on that lock (see `GraphPane.refresh_from`)."""
        return self._consult(question)

    def answer(self, reply: Optional[str]) -> None:
        """Called on the UI thread when the person types their answer."""
        self._answer = (reply or "").strip() or None
        self._answered.set()
        self.screen.post_message(Answered(self._answer))

    @property
    def waiting(self) -> bool:
        return self.question is not None

    # -- cues ---------------------------------------------------------------

    def _serve_cue(self) -> bool:
        """If a cue is pending, consult the person and say what they answer.

        Returns whether one was served. ⚠ This blocks the driver thread, and
        unlike the `ask` tool it holds no lock while it does -- a cue fires
        *between* ticks, so the machine is simply not running while it waits.
        """
        found = play.pending(self.runner)
        if found is None:
            return False
        cue, ctx = found
        options = cue.options(self.runner, ctx)
        reply = self._consult(cue.prompt(ctx), options)
        if self.stop_requested.is_set():
            return False
        said = play.speak(self.runner, cue, ctx, reply or "")
        self.screen.post_message(Declared(said))
        return True

    # -- driving ------------------------------------------------------------

    def drive(self, limit: int) -> None:
        """Run to quiescence, posting each tick. Called on a worker thread.

        The loop exists because a cue interrupts a drive and then the drive has
        to carry on: serve whatever is pending, run until something else is
        pending or there is nothing left, and go round. `Runner.run` is stopped
        from `on_step` rather than by counting, so a cue that becomes pending in
        the middle of a fight is noticed on the tick it appears.
        """
        self.stop_requested.clear()
        seen_before = len(self.runner.steps)
        try:
            total = 0
            while total < limit and not self.stop_requested.is_set():
                self._serve_cue()
                if self.stop_requested.is_set():
                    break
                self._cue_paused = False
                steps = self.runner.run(limit - total, on_step=self._on_step)
                total += len(steps)
                if not self._cue_paused:
                    break
            self.screen.post_message(
                Drove(total, self.runner.state, self.stop_requested.is_set())
            )
        except Exception as exc:  # the engine's errors belong on screen
            self.screen.post_message(
                Failed(f"{type(exc).__name__}: {exc}")
            )
            self.screen.post_message(
                Drove(len(self.runner.steps) - seen_before, self.runner.state, True)
            )

    def _on_step(self, step) -> bool:
        index = len(self.runner.steps)
        self.screen.post_message(
            Ticked(index, step.state, h.step_lines(self.runner.machine, step))
        )
        for what in self.runner.new_emissions():
            self.screen.post_message(Acted(what))
        if self.stop_requested.is_set():
            return False
        if play.pending(self.runner) is not None:
            # Stop the drive so `drive` can serve it. Not served here, because
            # `on_step` is the wrong place to block for a person: it would put
            # the wait inside a loop whose exit condition is the person.
            self._cue_paused = True
            return False
        if self.step_mode:
            # Step mode reuses the answer door rather than adding a second wait:
            # one place where the driver blocks for the person is enough, and
            # two would be two ways to deadlock.
            self._answered.clear()
            while not self._answered.wait(timeout=0.1):
                if self.stop_requested.is_set():
                    return False
        return True

    def stop(self) -> None:
        self.stop_requested.set()
        self._answered.set()   # release anything blocked on the person

    def advance(self) -> None:
        """Let a step-mode pause through."""
        self._answered.set()


def scan_corpora(root: Path) -> List[Path]:
    """Every `.ugm` corpus under `corpus/`, for the completion list and the
    empty-state hint. Sorted, because a directory listing's order is not one."""
    folder = root / "corpus"
    if not folder.is_dir():
        return []
    return sorted(folder.glob("*.ugm"))
