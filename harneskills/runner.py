"""The harness: one `ugm.Machine`, driven a tick at a time, with a door open.

This is the only module that holds engine state. Everything above it (the TUI,
the plain REPL, tests) talks to a `Runner` and never to a `Machine`, so that the
one place that knows how to keep a corpus, a name scope and a channel consistent
is here rather than in each caller.

**Why a persistent `Loader` per scope**, rather than `ugm.text.load` per
document. A `Loader` *is* the name scope for questions: `runner.term("kettle")`
has to resolve to the same node the corpus wrote, and rule names (`<boil>`) live
on the loader itself rather than in the machine's shared scope table -- so a
second `load()` call cannot write `overrides(<boil>, <cool>)`, and a REPL where
each line is its own document could never refer to anything it had already said.
Keeping the loader is what makes an interactive session a single document that
happens to arrive slowly. `_authoring_source` is set around each feed exactly as
`ugm.text.load` does it, so provenance still records which domain a line came
from.

**Why the machine is not run automatically.** UGM's own `replay` runs to
quiescence after each block, which is right for a batch. A harness wants the
other thing: the human decides when to think, so that a corpus can be inspected
before it has drawn any conclusions, and a single tick can be watched. `feed`
therefore writes and stops; `step` and `run` are separate verbs.
"""

from __future__ import annotations

import threading
from typing import Callable, Dict, List, NamedTuple, Optional

import ugm
from ugm.text import Loader, ParseError

#: The scope every document gets unless one is named. It is `kb` because that is
#: the channel an unscoped UGM document is already stamped with, so choosing a
#: default here changes provenance for nobody.
DEFAULT_SCOPE = "kb"


class Said(NamedTuple):
    """One thing the world told the agent, as the harness recorded it."""

    channel: str
    text: str
    sign: str


class RunnerError(Exception):
    """Anything the harness can explain to the user rather than crash on."""


class Runner:
    """A machine, its corpora, and the ways a person drives it."""

    def __init__(self, limit: int = 400) -> None:
        self.machine = ugm.Machine()
        self.limit = limit
        self._loaders: Dict[str, Loader] = {}
        self.scope = DEFAULT_SCOPE
        self.loaded: List[str] = []          # what has been fed, for the header
        self.said: List[Said] = []           # what the world has told it
        self.steps: List[ugm.Step] = []      # every tick, oldest first
        self._emitted_seen = 0
        self._oracle: Optional[Callable[[str], Optional[str]]] = None
        # What is being played, if anything (`harneskills.play.Scenario`). Held
        # here because a scenario is session state -- the corpus, its tools and
        # its name scope are all this runner's -- and because both front ends
        # and the command layer need to see it. Nothing in the engine knows.
        self.scenario = None
        # The machine is driven from a worker thread in the TUI while the UI
        # thread reads projections off it. Ticks are serialised so a render
        # never sees a half-written moment.
        self.lock = threading.RLock()

    # -- scopes and loading -------------------------------------------------

    def loader(self, scope: Optional[str] = None) -> Loader:
        """The loader for a scope, made once and kept.

        Two documents under one scope share a name table, so they can be about
        the same kettle; different scopes stay apart, which is what a fresh
        corpus wants. The domain is the scope, which is UGM's own default and
        means provenance answers *which document is this from* with nothing new.
        """
        name = scope or self.scope
        ldr = self._loaders.get(name)
        if ldr is None:
            ldr = Loader(self.machine, name, name)
            self._loaders[name] = ldr
        return ldr

    def feed(self, src: str, scope: Optional[str] = None, label: str = "") -> int:
        """Load statements. Returns how many were written. Does not think.

        A `ParseError` is re-raised as a `RunnerError` with the engine's own
        message, which already names the line and says what it expected -- the
        harness has nothing to add and inventing a second wording would make two
        vocabularies for one refusal.
        """
        ldr = self.loader(scope)
        with self.lock:
            self.machine._authoring_source = ldr.source
            try:
                statements = ldr.load(src)
            except ParseError as exc:
                raise RunnerError(str(exc)) from exc
            finally:
                self.machine._authoring_source = None
        self.loaded.append(label or f"{len(statements)} statements")
        return len(statements)

    def feed_file(self, path: str, scope: Optional[str] = None) -> int:
        with open(path, "r", encoding="utf-8") as fh:
            src = fh.read()
        return self.feed(src, scope, label=path)

    # -- the world speaking -------------------------------------------------

    def say(self, channel: str, text: str, sign: str = "+",
            scope: Optional[str] = None) -> int:
        """Deliver an arrival on a channel, in this session's name scope.

        What arrives is that the channel *said so*; whether that becomes a claim
        about the world is a rule the corpus can be asked about (`<trust_user>`
        in the worked example). The harness does not shortcut it -- an interface
        that believed its user directly would be deciding something the corpus
        is entitled to argue with.

        ⚠ No grade argument. Saying something *weakly* is now saying a weaker
        thing -- `say user: +likely(raining(here))` -- because modality became a
        proposition rather than an annotation on the entry.
        """
        ldr = self.loader(scope)
        with self.lock:
            try:
                prop = ldr.say(channel, text, sign)
            except ParseError as exc:
                raise RunnerError(str(exc)) from exc
        self.said.append(Said(channel, text, sign))
        return prop

    def term(self, text: str, scope: Optional[str] = None) -> int:
        """Resolve a written term to its node, for asking questions about it.

        ⚠ Locked, because this is a *write*: a name the corpus has not used yet
        is minted, so asking about `boiling(kettle)` before anything mentions it
        adds nodes. Harmless in itself -- an unclaimed proposition holds nothing
        -- but it must not happen half way through a tick.
        """
        with self.lock:
            try:
                return self.loader(scope).term(text)
            except ParseError as exc:
                raise RunnerError(str(exc)) from exc

    # -- thinking -----------------------------------------------------------

    def step(self) -> ugm.Step:
        """One tick. The unit a person can actually watch."""
        with self.lock:
            s = self.machine.tick()
        self.steps.append(s)
        return s

    def run(self, limit: Optional[int] = None,
            on_step: Optional[Callable[[ugm.Step], bool]] = None) -> List[ugm.Step]:
        """Think until there is nothing left, or until `limit` ticks.

        ⚠ Not `Machine.run`. The engine's loop is the right one but it returns
        only at the end, and a harness that showed a spinner for six seconds and
        then a wall of conclusions would have hidden exactly what it exists to
        show. So the loop is here, one `tick` at a time, and `on_step` is called
        with each -- returning `False` from it stops, which is how the UI's stop
        button and step-mode pause work without a second control path.

        The terminal states are the engine's: `quiescent` (nothing left to do)
        and `stopped` (it judged there was nothing more worth doing). Both mean
        this returns; neither is an error.
        """
        cap = self.limit if limit is None else limit
        out: List[ugm.Step] = []
        for _ in range(cap):
            s = self.step()
            out.append(s)
            if on_step is not None and on_step(s) is False:
                break
            if s.state in ("quiescent", "stopped"):
                break
        return out

    # -- what it did --------------------------------------------------------

    def new_emissions(self) -> List[str]:
        """Whatever left the agent since this was last asked.

        Read off `Machine.emitted`, which is where the outbound boundary appends.
        ⚠ A resumed session correctly does not act again, so this is empty on a
        replay while `did(...)` is still in the graph -- *what did you do* is a
        question for the report, not for this.
        """
        with self.lock:
            items = self.machine.emitted[self._emitted_seen:]
            self._emitted_seen = len(self.machine.emitted)
            return [self.machine.g.show(n) for n in items]

    # -- tools --------------------------------------------------------------

    def set_oracle(self, fn: Optional[Callable[[str], Optional[str]]],
                   request: str = "ask") -> None:
        """Register the human as a tool the agent may consult.

        This is the harness's reason to exist. The corpus concludes `+ask(q)`;
        the machinery routes it here; `fn` is called with the question and
        returns a term to believe, or `None` for *I have nothing to say* -- which
        is a real answer and not a failure, because a tool that must answer
        everything is a tool nothing can decline.

        ⚠ `fn` is called on whichever thread is ticking, and is expected to
        block until the person answers. That is correct: the agent asked, and
        reasoning past an unanswered question would be reasoning past the
        question.

        ⚠⚠ Registered through the **loader**, never through `Machine.answerer`.
        `ask` is not reserved vocabulary, so a bare string mints a *second* `ask`
        beside the one the corpus writes, and the tool then sits waiting for a
        request nobody can make -- silently, because a request with no answerer
        is an ordinary unanswered request. Anything that binds a name has to go
        through the table that resolves it. Registered here also means registered
        before any later `feed`, so a rule may name `<human>`.
        """
        self._oracle = fn
        if fn is None:
            return
        if any(a.name == "human" for a in self.machine.answerers):
            return

        def answer(mach, frame, entry):
            if self._oracle is None:
                return None
            members = mach.g.members(entry.proposition)
            question = mach.g.show(members[0]) if members else mach.g.show(entry.proposition)
            reply = self._oracle(question)
            if not reply:
                return None
            try:
                return self.loader().term(reply)
            except ParseError:
                # An unparseable answer is *nothing to say*, not a crash. The
                # person typed prose at a term prompt; the agent carries on
                # without an answer, which is a state it already handles.
                return None

        with self.lock:
            try:
                self.loader().answerer("human", request, answer)
            except ParseError as exc:
                raise RunnerError(str(exc)) from exc

    # -- sessions -----------------------------------------------------------

    def save(self, path: str) -> None:
        """Write the session as what it was told, rendered from the graph."""
        with self.lock:
            self.machine.save(path)

    def resume(self, path: str) -> int:
        """Re-live a saved session without re-doing it.

        ⚠ This replaces the machine. A resume is *this session was that one*,
        not *and also that one*: replaying into a machine that already knows
        things would stamp the replayed claims into a history they were not made
        in. Tools have to be re-registered by the caller, which UGM's own note
        on `save` says plainly -- an answerer is a Python function and no file
        carries it.
        """
        import json

        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        session = data["session"]
        with self.lock:
            self.machine = ugm.Machine()
            self._loaders.clear()
            self._emitted_seen = 0
            self.steps.clear()
            self.said.clear()
            self.loaded = [f"{path} (resumed)"]
            self.machine.replay(session, limit=self.limit)
        if self._oracle is not None:
            self.set_oracle(self._oracle)
        return len(session)

    # -- convenience --------------------------------------------------------

    @property
    def state(self) -> str:
        """The last tick's state, or `unstarted` before anything has been run."""
        return self.steps[-1].state if self.steps else "unstarted"

    def report(self) -> List[str]:
        with self.lock:
            return self.machine.report()

    def why(self, text: str, scope: Optional[str] = None) -> List[str]:
        from . import view

        with self.lock:
            return view.why(self.machine, self.term(text, scope))

    def holds(self, text: str, scope: Optional[str] = None) -> Optional[str]:
        with self.lock:
            return self.machine.holds(self.term(text, scope))
