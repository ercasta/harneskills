"""The screen: a transcript on the left, the machine on the right, a prompt below.

The layout is the argument. UGM's whole complaint about itself was that
everything it concluded was already in the graph and there was no door -- so the
graph is not behind a command here, it is the other half of the window, and it
updates while the agent thinks. The transcript says what *happened*; the pane
says what *is*. Neither is derivable from the other in a hurry, which is why both
are on screen at once.

Input goes through `harneskills.commands.dispatch`, so this file contains no
verbs of its own. The two exceptions are `/clear` and `/quit`, which are about
the window rather than the machine and have nowhere else to live.
"""

from __future__ import annotations

import time
from pathlib import Path

from rich.markup import escape as markup_escape
from textual import on
from textual.binding import Binding
from textual.containers import Horizontal
from textual.screen import Screen
from textual.widgets import Footer, RichLog, Static

import harneskills as h
from harneskills import RunnerError, dispatch

from .constants import PLACEHOLDER, REFRESH_SECONDS, SESSIONS_DIR, _HELP_TEXT
from .messages import Acted, Answered, Asked, Declared, Drove, Failed, Noted, Ticked
from .panes import GraphPane
from .session import Driver, SessionLog, scan_corpora
from .widgets import CommandInput, CommandSuggestions


def _session_dir() -> Path:
    return SESSIONS_DIR / time.strftime("%Y%m%d_%H%M%S")


class CLIScreen(Screen):
    BINDINGS = [
        Binding("ctrl+r", "drive", "Run"),
        Binding("ctrl+n", "one_tick", "Tick"),
        Binding("ctrl+x", "stop", "Stop"),
        Binding("ctrl+g", "cycle_layer", "Layer"),
        Binding("ctrl+p", "focus_pane", "Pane"),
        Binding("ctrl+l", "focus_input", "Prompt", show=False),
        Binding("ctrl+q", "quit", "Quit"),
    ]

    DEFAULT_CSS = """
    CLIScreen { layout: vertical; }
    #body { height: 1fr; }
    /* 3:2 against the pane's 2fr — the transcript is the wider half because a
       line of provenance is long and a proposition is short. */
    #transcript { width: 3fr; padding: 0 1; }
    #prompt-row { height: auto; max-height: 8; }
    #prompt-label { width: 2; color: $accent; }
    CommandInput { height: auto; max-height: 8; }
    #status-bar { height: 1; background: $panel; color: $text-muted; padding: 0 1; }
    """

    def __init__(self) -> None:
        super().__init__()
        self.driver = Driver(self)
        self.log_file = SessionLog(_session_dir())
        self._driving = False

    # -- layout -------------------------------------------------------------

    def compose(self):
        with Horizontal(id="body"):
            yield RichLog(id="transcript", markup=True, wrap=True, highlight=False)
            yield GraphPane(self.driver.runner, id="pane")
        yield CommandSuggestions(id="suggestions")
        with Horizontal(id="prompt-row"):
            yield Static("> ", id="prompt-label", markup=False)
            yield CommandInput(placeholder=PLACEHOLDER, id="command-input")
        yield Static("", id="status-bar", markup=False)
        yield Footer()

    def on_mount(self) -> None:
        self.say("[bold]harneskills[/bold] — a door onto a UGM machine")
        corpora = scan_corpora(Path.cwd())
        if corpora:
            self.say("[dim]corpora here:[/dim] "
                     + "  ".join(f"[cyan]{p.as_posix()}[/cyan]" for p in corpora))
            self.say(f"[dim]try:[/dim] /load {corpora[0].as_posix()}   [dim]then[/dim] /run")
        self.say("[dim]/help for the verbs. `fact` / `rule` / `say` lines author directly.[/dim]")
        self.say("")
        self.set_interval(REFRESH_SECONDS, self._refresh_pane)
        self._status()
        self.query_one(CommandInput).focus()

    # -- transcript ---------------------------------------------------------

    def say(self, line: str, log: bool = True) -> None:
        self.query_one("#transcript", RichLog).write(line)
        if log:
            self.log_file.write(_plain(line))

    def say_all(self, lines, prefix: str = "  ", style: str = "") -> None:
        for line in lines:
            body = markup_escape(line)
            self.say(f"{prefix}[{style}]{body}[/{style}]" if style else f"{prefix}{body}")

    def _status(self) -> None:
        r = self.driver.runner
        bits = [
            f"scope {r.scope}",
            f"ticks {len(r.steps)}",
            r.state,
            f"layer {self.query_one('#pane', GraphPane).current_layer}",
        ]
        if self.driver.step_mode:
            bits.append("STEP MODE")
        if self._driving:
            bits.append("running…")
        if self.driver.waiting:
            bits.append("WAITING FOR YOU")
        self.query_one("#status-bar", Static).update("  ·  ".join(bits))

    def _refresh_pane(self) -> None:
        try:
            self.query_one("#pane", GraphPane).refresh_from()
        except Exception:
            # A pane that cannot render must not take the session with it; the
            # transcript is the record of last resort and it is unaffected.
            pass
        self._status()

    # -- input --------------------------------------------------------------

    @on(CommandInput.Submitted)
    def _submitted(self, event: CommandInput.Submitted) -> None:
        text = event.value.strip()
        event.widget.add_to_history(text)
        self.query_one(CommandSuggestions).filter("")
        if not text:
            return

        # An outstanding question owns the prompt. Anything typed answers it --
        # including a slash command, which is refused rather than run, because
        # the agent is blocked and quietly running something else while it waits
        # would be the harness deciding to ignore the consultation.
        if self.driver.waiting:
            self.say(f"[bold yellow]>[/bold yellow] {markup_escape(text)}")
            self.driver.answer(text)
            return

        self.say(f"[bold]>[/bold] {markup_escape(text)}")
        low = text.lower()
        if low in ("/quit", "/exit"):
            self.app.exit()
            return
        if low == "/clear":
            self.query_one("#transcript", RichLog).clear()
            return
        if low == "/help":
            self.say(_HELP_TEXT)
            return
        if low == "/step-mode":
            self.driver.step_mode = not self.driver.step_mode
            self.say(f"[dim]step mode {'on' if self.driver.step_mode else 'off'}[/dim]")
            self._status()
            return
        if low == "/stop":
            self.action_stop()
            return
        self._dispatch(text)

    def _dispatch(self, text: str) -> None:
        try:
            resp = dispatch(self.driver.runner, text)
        except RunnerError as exc:
            self.say_all([str(exc)], prefix="! ", style="red")
            return
        except Exception as exc:
            self.say_all([f"{type(exc).__name__}: {exc}"], prefix="! ", style="red")
            return
        self.say_all(resp.lines, style="" if resp.ok else "red",
                     prefix="  " if resp.ok else "! ")
        for what in self.driver.runner.new_emissions():
            self.say(f"  [bold magenta]>> {markup_escape(what)}[/bold magenta]")
        if resp.ok and text.split(None, 1)[0] == "/play" and self.driver.runner.scenario:
            self.query_one("#pane", GraphPane).show_play()
        if resp.drive is not None:
            self._start_drive(resp.drive)
        elif resp.changed:
            self._refresh_pane()

    @on(CommandInput.Changed)
    def _changed(self, event: CommandInput.Changed) -> None:
        self.query_one(CommandSuggestions).filter(event.text_area.text)

    @on(CommandInput.ModeToggled)
    def _mode(self, event: CommandInput.ModeToggled) -> None:
        self.query_one("#prompt-label", Static).update(
            "…" if event.multiline else "> "
        )

    # -- driving ------------------------------------------------------------

    def _start_drive(self, limit: int) -> None:
        if self._driving:
            self.say("[dim]already running — ctrl+x to stop[/dim]")
            return
        self._driving = True
        self._status()
        self.run_worker(
            lambda: self.driver.drive(limit),
            thread=True, exclusive=True, name="drive",
        )

    @on(Ticked)
    def _ticked(self, event: Ticked) -> None:
        head, *rest = event.lines
        self.say(f"  [dim]{event.index:>4}[/dim] {markup_escape(head)}")
        self.say_all(rest, prefix="       ", style="dim")

    @on(Drove)
    def _drove(self, event: Drove) -> None:
        self._driving = False
        tail = " (stopped)" if event.stopped_early else ""
        self.say(f"  [bold]— {event.ticks} ticks, ended {event.state}{tail}[/bold]")
        self._refresh_pane()

    @on(Acted)
    def _acted(self, event: Acted) -> None:
        self.say(f"  [bold magenta]>> {markup_escape(event.what)}[/bold magenta]")

    @on(Asked)
    def _asked(self, event: Asked) -> None:
        self.say(f"  [bold yellow]? {markup_escape(event.question)}[/bold yellow]")
        if event.options:
            self.say("  [dim]e.g. "
                     + "  ".join(f"[cyan]{markup_escape(o)}[/cyan]" for o in event.options)
                     + "[/dim]")
        self.say("  [dim]answer with a term, or blank to decline[/dim]")
        self._status()
        self.query_one(CommandInput).focus()

    @on(Declared)
    def _declared(self, event: Declared) -> None:
        if event.said is None:
            self.say("  [dim]nothing declared — the corpus's standing policy acts[/dim]")
        else:
            self.say(f"  [green]said:[/green] {markup_escape(event.said)}")

    @on(Answered)
    def _answered(self, event: Answered) -> None:
        if event.reply is None:
            self.say("  [dim]declined — the agent carries on without an answer[/dim]")
        self._status()

    @on(Failed)
    def _failed(self, event: Failed) -> None:
        self.say(f"[red]! {markup_escape(event.error)}[/red]")

    @on(Noted)
    def _noted(self, event: Noted) -> None:
        self.say_all(event.lines, style="" if event.ok else "red")

    @on(GraphPane.Explain)
    def _explain(self, event: GraphPane.Explain) -> None:
        # ⚠ Resolving a term MINTS atoms, so it is a write to the graph and must
        # not happen on the UI thread while the driver is mid-tick. When the
        # agent is blocked on a question the driver holds the lock indefinitely,
        # so this would hang the window rather than merely race.
        if self.driver.waiting:
            self.say("[dim]it is waiting for your answer — explain after[/dim]")
            return
        self.say(f"[bold]why[/bold] {markup_escape(event.term)}")
        try:
            self.say_all(h.why(self.driver.runner.machine,
                               self.driver.runner.term(event.term)), style="dim")
        except RunnerError as exc:
            self.say_all([str(exc)], prefix="! ", style="red")

    # -- actions ------------------------------------------------------------

    def action_drive(self) -> None:
        self._dispatch("/run")

    def action_one_tick(self) -> None:
        if self.driver.step_mode and self._driving:
            self.driver.advance()
            return
        self._dispatch("/step")

    def action_stop(self) -> None:
        if not self._driving:
            self.say("[dim]nothing is running[/dim]")
            return
        self.driver.stop()
        self.say("[dim]stopping…[/dim]")

    def action_cycle_layer(self) -> None:
        layer = self.query_one("#pane", GraphPane).cycle_layer()
        self.say(f"[dim]pane layer: {layer} — {h.LAYER_HELP[layer]}[/dim]")
        self._status()

    def action_focus_pane(self) -> None:
        self.query_one("#pane", GraphPane).focus()

    def action_focus_input(self) -> None:
        self.query_one(CommandInput).focus()

    def action_quit(self) -> None:
        self.app.exit()

    def on_unmount(self) -> None:
        """⚠ Release the driver on the way out.

        It may be parked on `_answered.wait()` — mid-drive in step mode, or
        blocked on a question nobody is going to answer now — and that wait only
        ends when `stop_requested` is set. Without this the worker thread
        outlives the window and the process does not exit.
        """
        self.driver.stop()


def _plain(text: str) -> str:
    """Markup off, for the on-disk log. The transcript is styled; the file is
    something you can grep a week later."""
    out, depth = [], 0
    for ch in text:
        if ch == "[":
            depth += 1
        elif ch == "]":
            depth = max(0, depth - 1)
        elif depth == 0:
            out.append(ch)
    return "".join(out)
