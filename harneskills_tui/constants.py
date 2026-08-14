"""Presentation constants, all of them derived rather than restated.

`SLASH_COMMANDS` and the help text are built from `harneskills.COMMANDS`, so a
verb cannot exist without a completion entry and the help cannot describe a verb
that has been removed. The engine makes the same argument about its refusals
rendering from its form table; this is the same discipline one layer up.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict

from harneskills import COMMANDS, LAYER_HELP, LAYERS

SESSIONS_DIR = Path.home() / ".harneskills" / "sessions"

#: How often the graph pane re-reads the machine while a run is driving. Every
#: tick would be correct and unreadable -- a fast corpus produces hundreds a
#: second -- so the pane coalesces and the transcript keeps the detail.
REFRESH_SECONDS = 0.2

#: What the input placeholder says, because the single most useful thing to tell
#: someone at this prompt is that they may type the corpus language at it.
PLACEHOLDER = "fact +water(kettle)   |   /run   |   /why boiling(kettle)   |   /help"

SLASH_COMMANDS: Dict[str, str] = {c.name: c.help for c in COMMANDS}
SLASH_COMMANDS["/clear"] = "clear the transcript"
SLASH_COMMANDS["/quit"] = "quit"

_LAYER_LINES = "\n".join(
    f"  [cyan]{name:<9}[/cyan] [dim]{LAYER_HELP[name]}[/dim]" for name in LAYERS
)

_COMMAND_LINES = "\n".join(
    f"  [cyan]{(c.name + ' ' + c.args).strip():<26}[/cyan] [dim]{c.help}[/dim]"
    for c in COMMANDS
)

_HELP_TEXT = f"""\
[bold]The input language is the corpus language.[/bold]
A line starting [cyan]rule[/cyan] / [cyan]fact[/cyan] / [cyan]say[/cyan] is authored straight into the machine:

  [cyan]fact +water(kettle)[/cyan]
  [cyan]say user: +raining(here)[/cyan]
  [cyan]rule <boil> = causes( {{ +heat(?w) }}, {{ +boiling(?w) }} )[/cyan]

A bare term asks about it: [cyan]boiling(kettle)[/cyan] gives the verdict and the trail.

[bold]Commands[/bold]  (Tab = complete, Up/Down = history, Ctrl+T = multiline)
{_COMMAND_LINES}
  [cyan]/clear[/cyan]                     [dim]clear the transcript[/dim]
  [cyan]/quit[/cyan]                      [dim]quit[/dim]

[bold]Layers[/bold]  (for [cyan]/graph[/cyan], and the tabs on the right)
{_LAYER_LINES}

[bold]Keys[/bold]
  [cyan]Ctrl+R[/cyan]  run      [cyan]Ctrl+N[/cyan]  one tick      [cyan]Ctrl+X[/cyan]  stop
  [cyan]Ctrl+G[/cyan]  cycle the graph pane's layer
  [cyan]Ctrl+P[/cyan]  focus the pane (Enter on a row explains it)"""
