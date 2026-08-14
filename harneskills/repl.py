"""A plain terminal front end. No Textual, no threads, no screen.

It exists for three reasons and each of them is worth the seventy lines: it is
how the command layer gets tested without a UI harness, it is what you use over
ssh or in a pipe, and it is the reference showing that `commands.dispatch` really
is front-end agnostic -- if this file ever needs a special case, the TUI has been
allowed to own something the command layer should.

    python -m harneskills [corpus.ugm ...]
    python -m harneskills --resume session.json
"""

from __future__ import annotations

import sys
from typing import List, Optional, Sequence

from . import play, view
from .commands import dispatch
from .runner import Runner, RunnerError

BANNER = """harneskills -- a door onto a UGM machine
type /help for the verbs, or a `fact` / `rule` / `say` statement to author
/scenarios for something playable
"""


def _serve_cues(runner: Runner) -> bool:
    """Answer whatever the machine is waiting on a person for. Returns whether
    anything was served, so the drive knows to carry on."""
    served = False
    while True:
        found = play.pending(runner)
        if found is None:
            return served
        cue, ctx = found
        options = cue.options(runner, ctx)
        print(f"  ? {cue.prompt(ctx)}")
        if options:
            print("    e.g. " + "   ".join(options))
        try:
            reply = input("    > ").strip()
        except EOFError:
            reply = ""
        said = play.speak(runner, cue, ctx, reply)
        print(f"    said: {said}" if said
              else "    nothing declared -- the standing policy acts")
        served = True


def _show(runner: Runner, resp, quiet: bool = False) -> None:
    for line in resp.lines:
        print(("  " if resp.ok else "! ") + line)
    if resp.drive is not None:
        # `/run` hands back a budget rather than driving itself, so a UI can put
        # it on a worker. Here there is no worker, so drive it inline and print
        # each tick as it happens -- which is the whole reason `Runner.run` takes
        # a per-step callback instead of returning at the end.
        def on_step(s):
            if not quiet:
                for line in view.step_lines(runner.machine, s):
                    print("  " + line)
            # Stop the drive when a person's word is owed, so the loop below can
            # ask for it. Serving it here would put the wait inside a loop whose
            # exit condition is the person.
            return play.pending(runner) is None

        total = 0
        budget = resp.drive
        while total < budget:
            _serve_cues(runner)
            steps = runner.run(budget - total, on_step=on_step)
            total += len(steps)
            if play.pending(runner) is None:
                break
        print(f"  -- {total} ticks, ended {runner.state}")
        if runner.scenario is not None:
            for line in runner.scenario.status(runner):
                print("  " + line)
    for act in runner.new_emissions():
        print(f"  >> {act}")


def main(argv: Optional[Sequence[str]] = None) -> int:
    args: List[str] = list(sys.argv[1:] if argv is None else argv)
    runner = Runner()

    # The human is a tool. `input` blocks, which is exactly right: the agent
    # asked, and reasoning past an unanswered question would be reasoning past
    # the question.
    def ask(question: str) -> Optional[str]:
        try:
            return input(f"  ? {question}  > ").strip() or None
        except EOFError:
            return None

    runner.set_oracle(ask)

    if args and args[0] == "--resume":
        if len(args) < 2:
            print("--resume needs a session file")
            return 2
        _show(runner, dispatch(runner, f"/resume {args[1]}"))
        args = args[2:]
    for path in args:
        _show(runner, dispatch(runner, f"/load {path}"))

    print(BANNER)
    while True:
        try:
            line = input("> ")
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if line.strip() in ("/quit", "/exit", "quit", "exit"):
            return 0
        try:
            _show(runner, dispatch(runner, line))
        except RunnerError as exc:
            print(f"! {exc}")
        except Exception as exc:  # a front end must not die on one bad line
            print(f"! {type(exc).__name__}: {exc}")


if __name__ == "__main__":
    raise SystemExit(main())
