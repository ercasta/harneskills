from __future__ import annotations

import sys
from typing import List, Optional, Sequence

from textual.app import App
from textual.binding import Binding

from .screen import CLIScreen


class HarneskillsTUI(App):
    TITLE = "harneskills"
    SUB_TITLE = "a door onto a UGM machine"

    BINDINGS = [Binding("ctrl+q", "quit", "Quit")]

    def __init__(self, corpora: Optional[Sequence[str]] = None,
                 resume: Optional[str] = None) -> None:
        super().__init__()
        self._corpora = list(corpora or ())
        self._resume = resume

    def on_mount(self) -> None:
        # No splash. It was a second of animation in front of a tool whose whole
        # complaint about its engine was that you could not see what it was
        # doing; the corpus list the screen prints instead is the same second
        # spent saying something true.
        screen = CLIScreen()
        self.push_screen(screen, callback=None)
        if self._resume:
            self.call_later(screen._dispatch, f"/resume {self._resume}")
        for path in self._corpora:
            self.call_later(screen._dispatch, f"/load {path}")


def main(argv: Optional[Sequence[str]] = None) -> int:
    """    harneskills [corpus.ugm ...] [--resume session.json]"""
    args: List[str] = list(sys.argv[1:] if argv is None else argv)
    resume = None
    if "--resume" in args:
        i = args.index("--resume")
        if i + 1 >= len(args):
            print("--resume needs a session file")
            return 2
        resume = args[i + 1]
        args = args[:i] + args[i + 2:]
    if args and args[0] in ("-h", "--help"):
        print(main.__doc__)
        return 0
    HarneskillsTUI(args, resume).run()
    return 0
