from __future__ import annotations

import os as _os
import threading
import time
from pathlib import Path
from typing import Any

from rich.markup import escape as markup_escape
from textual import on
from textual.binding import Binding
from textual.containers import Horizontal
from textual.events import Blur, Focus  # noqa: F401 – used in on_focus/on_blur signatures
from textual.screen import Screen
from textual.widgets import Footer, RichLog, Static, TextArea

from .constants import DEFAULT_CONFIG, _HELP_TEXT, SLASH_COMMANDS
from .messages import (
    ErrorEvent,
    GoalReachedEvent,
    ImpasseEvent,
    StatusEvent,
    StepEvent,
)
from .modals import LogViewModal
from .profiles import _load_profiles, _save_profiles
from ugm.world_model import WorldModel
from .session import HarnessRunner, SessionLog, parse_goal_text, parse_value, scan_corpus_kbs
from .widgets import CommandInput, CommandSuggestions


def _make_session_dir() -> Path:
    base = Path.home() / ".harneskills" / "sessions"
    ts = time.strftime("%Y%m%d_%H%M%S")
    d = base / ts
    d.mkdir(parents=True, exist_ok=True)
    return d


class CLIScreen(Screen):
    """Single-screen CLI-style interface: scrolling log | autocomplete | input bar."""

    _MODE_NORMAL = "normal"
    _MODE_STEP   = "step"     # paused between steps, waiting for Enter

    BINDINGS = [
        Binding("ctrl+q", "quit", "Quit"),
        Binding("ctrl+s", "submit_input", "Send", show=True),
        Binding("ctrl+t", "toggle_multiline", "Multiline", show=True),
        Binding("ctrl+v", "cycle_verbose", "Verbose"),
        Binding("ctrl+l", "focus_log", "Select log", show=False),
        Binding("ctrl+c", "copy_selection", "Copy", show=False),
        Binding("escape", "focus_input", "Back to input", show=False),
    ]

    DEFAULT_CSS = """
    CLIScreen { layout: vertical; }

    #output-log { height: 1fr; }

    #computing-indicator {
        display: none;
        height: 1;
        padding: 0 1;
    }
    #computing-indicator.running { display: block; }

    #input-bar {
        height: auto;
        min-height: 3;
        max-height: 10;
        background: $surface;
        border-top: solid $surface-lighten-2;
        padding: 0 1;
        align: left top;
    }

    #prompt-label {
        width: auto;
        padding: 0 1 0 0;
        color: $text-muted;
        height: auto;
    }

    #cmd-input {
        width: 1fr;
        border: none;
        background: transparent;
        padding: 0;
        height: auto;
        max-height: 8;
    }
    #cmd-input > .text-area--cursor-line { background: transparent; }

    #status-bar {
        height: 1;
        background: $surface-darken-1;
        padding: 0 1;
        color: $text-muted;
    }
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._config: dict[str, Any] = dict(DEFAULT_CONFIG)
        self._mode: str = self._MODE_NORMAL
        self._running: bool = False
        self._verbosity: int = 1
        self._step_count: int = 0
        self._multiline_input: bool = False
        self._spinner_idx: int = 0
        self._status_text: str = ""
        self._session_log: SessionLog | None = None
        self._step_mode: bool = True
        self._step_paused: bool = False
        self._spinner_timer: Any = None
        self._runner: HarnessRunner | None = None

    _SPINNER_FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
    _COMPUTING_COLORS = ["cyan", "bright_cyan", "bright_white", "bright_cyan"]

    def compose(self):
        yield RichLog(id="output-log", markup=True, wrap=True, highlight=False)
        yield Static("", id="computing-indicator", markup=True)
        yield CommandSuggestions(id="suggestions")
        with Horizontal(id="input-bar"):
            yield Static("> ", id="prompt-label", markup=False)
            yield CommandInput(
                placeholder="/help for commands · ? to explore slots · Ctrl+T multiline",
                id="cmd-input",
            )
        yield Static("", id="status-bar", markup=False)
        yield Footer()

    def on_mount(self) -> None:
        profiles = _load_profiles()
        if "default" in profiles:
            profile_data = dict(profiles["default"])
            self._verbosity = profile_data.pop("verbosity", 1)
            self._config = {**DEFAULT_CONFIG, **profile_data}
        self._set_mode(self._MODE_NORMAL)
        self.query_one("#cmd-input", CommandInput).focus()
        self._spinner_timer = self.set_interval(0.15, self._tick_spinner, pause=True)
        self._log_welcome()

    # ------------------------------------------------------------------
    # Logging / status helpers
    # ------------------------------------------------------------------

    def _log(self, msg: str) -> None:
        self.query_one("#output-log", RichLog).write(msg)

    def _set_status(self, text: str) -> None:
        self._status_text = text
        self._refresh_status()

    def _refresh_status(self) -> None:
        indicator = self.query_one("#computing-indicator", Static)
        if self._running:
            spinner = self._SPINNER_FRAMES[self._spinner_idx % len(self._SPINNER_FRAMES)]
            color = self._COMPUTING_COLORS[self._spinner_idx % len(self._COMPUTING_COLORS)]
            indicator.update(f"[{color}]{spinner} running…[/{color}]")
            indicator.add_class("running")
            self.query_one("#status-bar", Static).update(f"{spinner} {self._status_text}")
        else:
            indicator.remove_class("running")
            self.query_one("#status-bar", Static).update(self._status_text)

    def _tick_spinner(self) -> None:
        if not self._running:
            return
        self._spinner_idx = (self._spinner_idx + 1) % len(self._SPINNER_FRAMES)
        self._refresh_status()

    def _log_welcome(self) -> None:
        self._log(
            "[bold cyan]harneskills[/bold cyan]"
            " [dim]— KB-driven harness engine[/dim]"
        )
        self._log(
            "[dim][cyan]Ctrl+Q[/cyan] quit  "
            "[cyan]Ctrl+T[/cyan] multiline  "
            "[cyan]Ctrl+S[/cyan] send  "
            "[cyan]Ctrl+L[/cyan] focus log  "
            "[cyan]/help[/cyan] commands[/dim]"
        )
        self._log("")

        # Check for the included coffee demo (cheap path check — no scan needed)
        demo_path = Path.cwd() / "examples" / "coffee_kb.py"
        if demo_path.exists():
            rel = demo_path.relative_to(Path.cwd())
            self._log("[bold]Included demo[/bold] — coffee planning (goal reached, with a replan):")
            self._log(f"  [cyan]/kb {markup_escape(str(rel))}[/cyan]")
            self._log("  [cyan]/goal have_coffee[/cyan]")
            self._log("  [cyan]/run[/cyan]")
            self._log(
                "  [dim]watch it choose fetch_water over deliver_water (cheaper), get beans,"
                " make coffee — and replan after a withheld make_coffee.[/dim]"
            )
            self._log(
                "  [dim]or author the whole problem in CNL:[/dim]"
                "  [cyan]/kb corpus/coffee_kb.cnl[/cyan]  [cyan]/run[/cyan]"
            )
            self._log(
                "  [dim]a mixed KB (operators + goal + a procedure):[/dim]"
                "  [cyan]/kb corpus/barista_kb.cnl[/cyan]  [cyan]/run[/cyan]"
                "  [dim]or[/dim] [cyan]/do morning_service[/cyan]"
            )
            self._log("")
        else:
            self._log("[bold]Quick start:[/bold]")
            self._log("  [cyan]/kb path/to/kb.py[/cyan]     [dim]← exports build() -> Graph (operators + state)[/dim]")
            self._log("  [cyan]/goal have_coffee[/cyan]    [dim]← a goal condition (or several, space-separated)[/dim]")
            self._log("  [cyan]/run[/cyan]                 [dim]← drive goal → plan → act → replan[/dim]")
            self._log("  [dim]a .cnl planning KB (operators/goal in CNL) is coming — see /kb.[/dim]")
            self._log("")

        # Scan for KB modules in the background so the UI is not blocked
        threading.Thread(
            target=self._scan_kbs_background,
            args=(demo_path,),
            daemon=True,
        ).start()

    def _scan_kbs_background(self, demo_path: Path) -> None:
        kbs = [p for p in scan_corpus_kbs(require_registry=True) if p != demo_path]
        if kbs:
            self.app.call_from_thread(self._log_kb_list, kbs[:6])

    def _log_kb_list(self, kbs: list[Path]) -> None:
        self._log("[bold]Runnable KB modules[/bold] (have build_kb + build_registry):")
        for kb_path in kbs:
            rel = kb_path.relative_to(Path.cwd()) if kb_path.is_relative_to(Path.cwd()) else kb_path
            self._log(f"  [cyan]/kb {markup_escape(str(rel))}[/cyan]")
        self._log("")

    # ------------------------------------------------------------------
    # Mode management
    # ------------------------------------------------------------------

    def _set_mode(self, mode: str) -> None:
        self._mode = mode
        label = self.query_one("#prompt-label", Static)
        inp = self.query_one("#cmd-input", CommandInput)
        ml = self._multiline_input
        if mode == self._MODE_STEP:
            label.update("[▶] ")
            inp.placeholder = "Enter = next step  /stop = abort  /step = disable step mode"
        elif ml:
            label.update(">ML ")
            inp.placeholder = "multiline mode — Ctrl+S to submit, Ctrl+T to exit"
        else:
            label.update("> ")
            inp.placeholder = "type /help for commands — Enter to submit, Ctrl+T for multiline"

    # ------------------------------------------------------------------
    # Input events
    # ------------------------------------------------------------------

    def _slot_completions(self) -> list[tuple[str, str]]:
        """Build (slot_name, description) pairs from current DM + KB for ? autocomplete."""
        items: dict[str, str] = {}
        runner = self._runner
        if runner:
            dm = runner.dm
            if dm:
                for key in sorted(dm.keys()):
                    v = dm.get(key)
                    short = repr(v)
                    if len(short) > 50:
                        short = short[:50] + "…"
                    items[key] = short
            kb = runner.kb
            if kb:
                for key in sorted(kb.keys()):
                    if key not in items:
                        items[key] = "[kb]"
        return sorted(items.items())

    @on(TextArea.Changed, "#cmd-input")
    def _on_input_changed(self, event: TextArea.Changed) -> None:
        first_line = event.text_area.text.split("\n")[0]
        suggestions = self.query_one(CommandSuggestions)
        if first_line.startswith("?"):
            suggestions.filter(first_line, extra_items=self._slot_completions())
        elif first_line.startswith("/"):
            suggestions.filter(first_line)
        else:
            suggestions.filter("")

    @on(CommandInput.ModeToggled)
    def _on_mode_toggled(self, event: CommandInput.ModeToggled) -> None:
        self._multiline_input = event.multiline
        self._set_mode(self._mode)

    @on(CommandInput.Submitted)
    def _on_submitted(self, event: CommandInput.Submitted) -> None:
        text = event.value.strip()
        if text:
            event.widget.add_to_history(text)
        self.query_one(CommandSuggestions).filter("")

        # Step mode: blank Enter (or /step /stop) while paused
        if self._step_paused:
            if not text or text.lower() in ("/continue", "/next", "/n"):
                self._resume_step()
                return
            if text.lower() == "/stop":
                self._step_paused = False
                self._cmd_stop()
                return
            if text.lower() == "/step":
                self._cmd_step()
                return
            # anything else: show hint, don't consume
            self._log("[dim]Paused — Enter to continue, /stop to abort, /step to disable step mode[/dim]")
            return

        if not text:
            return
        if text.startswith("/"):
            self._dispatch(text)
        elif "." in text and "=" not in text and " " not in text:
            # bare dotted name → slot value query (e.g. Tab-completed from ?)
            self._cmd_query(text)
        else:
            self._cmd_run(goal_override=text)

    def action_submit_input(self) -> None:
        try:
            inp = self.query_one("#cmd-input", CommandInput)
            text = inp.text.strip()
            inp.clear()
            inp.post_message(CommandInput.Submitted(inp, text))
        except Exception:
            pass

    def action_toggle_multiline(self) -> None:
        try:
            inp = self.query_one("#cmd-input", CommandInput)
            inp._multiline_mode = not inp._multiline_mode
            inp.post_message(CommandInput.ModeToggled(inp, inp._multiline_mode))
        except Exception:
            pass

    def action_focus_log(self) -> None:
        self.query_one("#output-log", RichLog).focus()

    def action_focus_input(self) -> None:
        focused = self.focused
        if focused and focused.id == "output-log":
            self.query_one("#cmd-input", CommandInput).focus()

    def action_copy_selection(self) -> None:
        focused = self.focused
        if focused and focused.id == "output-log":
            text = self.screen.get_selected_text()
            if text:
                self.app.copy_to_clipboard(text)
                self._log(f"[dim]Copied {len(text)} chars to clipboard.[/dim]")

    def on_focus(self, event: Focus) -> None:
        if event.widget.id == "output-log":
            event.widget.auto_scroll = False  # type: ignore[union-attr]

    def on_blur(self, event: Blur) -> None:
        if event.widget.id == "output-log":
            log = self.query_one("#output-log", RichLog)
            log.auto_scroll = True
            log.scroll_end(animate=False)

    def action_quit(self) -> None:
        if self._running:
            self._cmd_stop()
        self.app.exit()
        def _force_exit() -> None:
            time.sleep(0.4)
            _os._exit(0)
        threading.Thread(target=_force_exit, daemon=True).start()

    def action_cycle_verbose(self) -> None:
        self._verbosity = (self._verbosity + 1) % 3
        self._log(f"[dim]Verbosity → {self._verbosity}: {self._verbosity_label()}[/dim]")

    # ------------------------------------------------------------------
    # Command dispatcher
    # ------------------------------------------------------------------

    def _dispatch(self, text: str) -> None:
        parts = text.split(None, 1)
        cmd = parts[0].lower()
        arg = parts[1].strip() if len(parts) > 1 else ""

        handlers: dict[str, Any] = {
            "/help":     lambda: self._log(_HELP_TEXT),
            "/?":        lambda: self._log(_HELP_TEXT),
            "/run":      lambda: self._cmd_run(arg),
            "/do":       lambda: self._cmd_do(arg),
            "/stop":     lambda: self._cmd_stop(),
            "/goal":     lambda: self._cmd_goal(arg),
            "/seed":     lambda: self._cmd_seed(arg),
            "/unseed":   lambda: self._cmd_unseed(arg),
            "/entity":   lambda: self._cmd_entity(arg),
            "/suppose":  lambda: self._cmd_suppose(arg),
            "/kb":       lambda: self._cmd_kb(arg),
            "/steps":    lambda: self._cmd_steps(arg),
            "/step":     lambda: self._cmd_step(),
            "/dm":       lambda: self._cmd_dm(),
            "/explain":  lambda: self._cmd_explain(),
            "/config":   lambda: self._cmd_config(),
            "/verbose":  lambda: self._cmd_verbose(arg),
            "/save":     lambda: self._cmd_save(arg),
            "/profile":  lambda: self._cmd_profile(arg),
            "/profiles": lambda: self._cmd_profiles(),
            "/delete":   lambda: self._cmd_delete(arg),
            "/logs":     lambda: self._cmd_logs(),
            "/log":      lambda: self._cmd_log(arg),
            "/clear":    lambda: self._cmd_clear(),
            "/quit":     lambda: self.action_quit(),
            "/exit":     lambda: self.action_quit(),
        }
        fn = handlers.get(cmd)
        if fn:
            fn()
        else:
            self._log(f"[red]Unknown command: {cmd}[/red] — type [cyan]/help[/cyan]")

    # ------------------------------------------------------------------
    # Command implementations
    # ------------------------------------------------------------------

    def _cmd_run(self, goal_override: str = "") -> None:
        if self._running:
            self._cmd_stop()

        if goal_override:
            self._config["goal"] = goal_override

        kb_path = self._config.get("kb_path", "")
        is_cnl = kb_path.lower().endswith(".cnl")

        if not kb_path:
            self._log(
                "[red]No KB set.[/red]  Use [cyan]/kb path/to/kb.py[/cyan]"
                " or [cyan]/kb path/to/corpus.cnl[/cyan]"
            )
            return

        goal_slots: dict = {}
        if self._config.get("goal"):
            goal_slots = parse_goal_text(self._config["goal"])
            if not goal_slots:
                self._log(
                    f"[red]Cannot parse goal as slot=value pairs:[/red]"
                    f" {markup_escape(self._config['goal'][:80])}\n"
                    f"  Example: [cyan]validation.pytest_clean=True[/cyan]"
                )
                return
        elif not is_cnl:
            self._log(
                "[red]No goal set.[/red]  Use [cyan]/goal slot=value[/cyan]"
                " or type your goal and press Enter."
            )
            return
        # CNL files with no explicit /goal: goal is read from KB (Forms 20/21/22).

        self._config["goal_slots"] = goal_slots
        dm_seed = self._config.get("dm_seed", {})
        max_steps = self._config.get("max_steps", 20)
        suppose_sentences = self._config.get("suppose_sentences", [])

        goal_preview = str(goal_slots)[:100] if goal_slots else "(from KB)"
        self._log(
            f"\n[bold]Starting session[/bold]"
            f"  kb=[cyan]{markup_escape(kb_path)}[/cyan]"
            f"  steps={max_steps}"
        )
        self._log(f"  goal: [italic]{markup_escape(goal_preview)}[/italic]")
        if dm_seed:
            self._log(f"  seed: [dim]{markup_escape(str(dm_seed)[:100])}[/dim]")
        if suppose_sentences:
            self._log(f"  suppose: [dim]{len(suppose_sentences)} sentence(s)[/dim]")
        self._log("")

        self._session_log = SessionLog(_make_session_dir())
        self._session_log.write(f"=== goal: {goal_slots}  kb={kb_path} ===")

        self._running = True
        self._step_count = 0
        if self._spinner_timer:
            self._spinner_timer.resume()
        self._set_status(f"running  ·  step 0/{max_steps}  ·  {goal_preview[:50]}")

        entity_scopes = self._config.get("entity_scopes", {})
        self._step_paused = False
        self._runner = HarnessRunner(self)
        self._runner.start(
            goal_slots, kb_path, dm_seed, max_steps,
            entity_scopes=entity_scopes,
            suppose_sentences=suppose_sentences,
            step_mode=self._step_mode,
        )

    def _cmd_do(self, name: str) -> None:
        """Run a PROCEDURE declared in the KB (a `to NAME s1 then s2` sequence). Distinct from
        /run (which drives a goal): /do executes the named step sequence, the planner gap-filling
        any unmet precondition. Demonstrates the operators+procedures mix in one .cnl KB."""
        if self._running:
            self._cmd_stop()
        if not name:
            self._log("[red]Usage: /do <procedure-name>[/red]  (a procedure declared in the KB)")
            return
        kb_path = self._config.get("kb_path", "")
        if not kb_path:
            self._log("[red]No KB set.[/red]  Use [cyan]/kb path/to/kb.cnl[/cyan] first.")
            return
        if not kb_path.lower().endswith(".cnl"):
            self._log(
                "[yellow]Procedures are declared in a .cnl planning KB.[/yellow]"
                "  Point /kb at a .cnl file."
            )
            return
        max_steps = self._config.get("max_steps", 20)
        dm_seed = self._config.get("dm_seed", {})
        self._log(
            f"\n[bold]Running procedure[/bold] [cyan]{markup_escape(name)}[/cyan]"
            f"  kb=[cyan]{markup_escape(kb_path)}[/cyan]"
        )
        self._log("")
        self._session_log = SessionLog(_make_session_dir())
        self._session_log.write(f"=== procedure: {name}  kb={kb_path} ===")
        self._running = True
        self._step_count = 0
        if self._spinner_timer:
            self._spinner_timer.resume()
        self._set_status(f"running procedure  ·  {name}")
        self._step_paused = False
        self._runner = HarnessRunner(self)
        self._runner.start(
            {}, kb_path, dm_seed, max_steps,
            step_mode=self._step_mode, procedure=name,
        )

    def _cmd_stop(self) -> None:
        if not self._running:
            self._log("[dim]No session is running.[/dim]")
            return
        self._running = False
        self._step_paused = False
        if self._spinner_timer:
            self._spinner_timer.pause()
        if self._runner:
            self._runner.stop()   # also sets the step gate, unblocking if paused
        self._set_mode(self._MODE_NORMAL)
        self._refresh_status()
        self._log("[yellow]Session stopped.[/yellow]")
        self._set_status("Stopped  ·  type a goal or /run")

    def _cmd_goal(self, text: str) -> None:
        if not text:
            slots = self._config.get("goal_slots") or {}
            raw = self._config.get("goal", "(none)")
            self._log(f"[dim]goal text: {markup_escape(raw)}[/dim]")
            if slots:
                self._log(f"[dim]goal slots: {markup_escape(str(slots))}[/dim]")
            return
        self._config["goal"] = text
        self._config["goal_slots"] = parse_goal_text(text)
        self._log(f"[green]Goal:[/green] {markup_escape(text)}")
        if self._config["goal_slots"]:
            self._log(f"  [dim]parsed → {self._config['goal_slots']}[/dim]")
        else:
            self._log(
                "  [yellow]Warning: no slot=value pairs found.[/yellow]"
                "  Expected format: [cyan]slot=value[/cyan]"
            )

    def _cmd_seed(self, text: str) -> None:
        if not text or "=" not in text:
            # Show all current seeds
            session_seeds = self._config.get("dm_seed", {})
            entity_scopes = self._config.get("entity_scopes", {})
            if session_seeds or entity_scopes:
                if session_seeds:
                    self._log("[dim]Session seeds:[/dim]")
                    for k, v in session_seeds.items():
                        self._log(f"  [cyan]{k}[/cyan] = {v!r}")
                for label, slots in entity_scopes.items():
                    self._log(f"[dim]Entity @{label}:[/dim]")
                    for k, v in slots.items():
                        self._log(f"  [cyan]{k}[/cyan] = {v!r}")
            else:
                self._log(
                    "[dim]No seeds set. Usage:[/dim]\n"
                    "  [cyan]/seed slot=value[/cyan]          session-level\n"
                    "  [cyan]/seed @label slot=value[/cyan]   entity-scoped (create entity first)"
                )
            return

        if text.startswith("@"):
            # Entity-scoped seed: /seed @label slot=value
            parts = text[1:].split(None, 1)
            if len(parts) < 2 or "=" not in parts[1]:
                self._log("[red]Usage: /seed @label slot=value[/red]")
                return
            label, rest = parts[0], parts[1]
            if label not in self._config.get("entity_scopes", {}):
                self._log(
                    f"[red]Unknown entity label '{label}'.[/red]"
                    f"  Create it first with [cyan]/entity {label}[/cyan]"
                )
                return
            slot, val_str = rest.split("=", 1)
            slot, val = slot.strip(), parse_value(val_str.strip())
            self._config["entity_scopes"][label][slot] = val
            self._log(f"[green]Seed @{label}:[/green] {slot} = {val!r}")
        else:
            # Session-level seed: /seed slot=value
            slot, val_str = text.split("=", 1)
            slot, val = slot.strip(), parse_value(val_str.strip())
            if "dm_seed" not in self._config:
                self._config["dm_seed"] = {}
            self._config["dm_seed"][slot] = val
            self._log(f"[green]Seed:[/green] {slot} = {val!r}")

    def _cmd_unseed(self, text: str) -> None:
        if not text:
            self._log("[red]Usage: /unseed slot  or  /unseed @label slot[/red]")
            return
        if text.startswith("@"):
            parts = text[1:].split(None, 1)
            if len(parts) < 2:
                self._log("[red]Usage: /unseed @label slot[/red]")
                return
            label, slot = parts[0], parts[1].strip()
            entity_scopes = self._config.get("entity_scopes", {})
            if label not in entity_scopes:
                self._log(f"[dim]Unknown entity label '{label}'.[/dim]")
                return
            if slot not in entity_scopes[label]:
                self._log(f"[dim]{slot} not in @{label} seed.[/dim]")
                return
            del entity_scopes[label][slot]
            self._log(f"[dim]Removed @{label} seed: {slot}[/dim]")
        else:
            slot = text.strip()
            seed = self._config.get("dm_seed", {})
            if slot not in seed:
                self._log(f"[dim]{slot} not in session seed.[/dim]")
                return
            del seed[slot]
            self._log(f"[dim]Removed seed: {slot}[/dim]")

    def _cmd_entity(self, label: str) -> None:
        entity_scopes = self._config.setdefault("entity_scopes", {})
        if not label:
            if entity_scopes:
                self._log("[dim]Entity scopes:[/dim]")
                for lbl, slots in entity_scopes.items():
                    slot_preview = ", ".join(f"{k}={v!r}" for k, v in list(slots.items())[:3])
                    self._log(f"  [cyan]@{lbl}[/cyan]  {slot_preview}")
            else:
                self._log("[dim]No entity scopes. Usage: /entity <label>[/dim]")
            return
        if label in entity_scopes:
            self._log(f"[dim]Entity @{label} already exists.[/dim]")
            return
        entity_scopes[label] = {}
        self._log(
            f"[green]Entity:[/green] @{label} created."
            f"  Add slots with [cyan]/seed @{label} slot=value[/cyan]"
        )

    def _cmd_suppose(self, text: str) -> None:
        if self._running:
            self._log("[red]Cannot add suppose sentences while a session is running.[/red]")
            return
        if not text:
            sentences = self._config.get("suppose_sentences", [])
            if sentences:
                self._log("[dim]Queued suppose sentences:[/dim]")
                for s in sentences:
                    self._log(f"  [dim]{markup_escape(s)}[/dim]")
            else:
                self._log(
                    "[dim]No suppose sentences queued.[/dim]\n"
                    "  Usage: [cyan]/suppose ?alice is_a customer with urgency 0.3[/cyan]\n"
                    "  [dim]Form 14 sentences — applied before /run starts the engine[/dim]"
                )
            return
        sentence = text if text.lower().startswith("suppose ") else f"suppose {text}"
        if "suppose_sentences" not in self._config:
            self._config["suppose_sentences"] = []
        self._config["suppose_sentences"].append(sentence)
        self._log(f"[green]Suppose:[/green] {markup_escape(sentence)}")

    def _cmd_explain(self) -> None:
        runner = self._runner
        if runner is None or runner.last_action is None:
            self._log("[dim]No step has been executed yet.[/dim]")
            return
        # The old step-level explainer belonged to the deleted typed-KB paradigm. Under the
        # current substrate a step's justification lives in the graph's provenance; a rich
        # `/explain` over that is a follow-up. For now surface the last operator + the
        # operator descriptors so the user can see what fired.
        kb = runner.kb
        self._log(f"[bold]Last step:[/bold] [cyan]{markup_escape(str(runner.last_action))}[/cyan]")
        if kb is not None:
            desc = kb.get(str(runner.last_action))
            if desc:
                self._log(f"  [dim]{markup_escape(str(desc))}[/dim]")
        self._log("[dim]/dm shows observed world state.[/dim]")

    def _cmd_kb(self, path: str) -> None:
        if not path:
            self._log(f"[dim]kb_path: {self._config.get('kb_path') or '(none)'}[/dim]")
            return
        self._config["kb_path"] = path
        self._log(f"[green]KB:[/green] {markup_escape(path)}")

    def _cmd_steps(self, n: str) -> None:
        if not n:
            self._log(f"[dim]max_steps = {self._config.get('max_steps', 20)}[/dim]")
            return
        try:
            val = int(n)
            self._config["max_steps"] = val
            self._log(f"[dim]max_steps → {val}[/dim]")
        except ValueError:
            self._log("[red]Usage: /steps <integer>[/red]")

    def _cmd_dm(self) -> None:
        runner = self._runner
        dm = runner.dm if runner else None
        if dm is None:
            self._log("[dim]No domain model — start a session first.[/dim]")
            return

        # Build reverse map: scope_id → label (from runner's entity_label_to_scope)
        scope_to_label: dict[str, str] = {}
        if runner:
            for lbl, sc in runner.entity_label_to_scope.items():
                scope_to_label[sc] = lbl

        self._log("\n[bold]Domain model:[/bold]")

        # Session-level slots
        session_keys = sorted(dm.keys())
        if session_keys:
            self._log("  [dim]session[/dim]")
            for k in session_keys:
                v = dm.get(k)
                self._log(f"    [cyan]{k:<38}[/cyan] {markup_escape(repr(v)[:80])}")
        else:
            self._log("  [dim]session: (empty)[/dim]")

        # Entity scopes
        for scope in dm.entity_scopes():
            label = scope_to_label.get(scope, "")
            header = f"@{label}" if label else scope
            self._log(f"  [dim]{header}[/dim]  [dim]{scope[:16]}…[/dim]")
            for k in sorted(WorldModel.keys(dm, scope)):
                v = WorldModel.get(dm, scope, k)
                self._log(f"    [cyan]{k:<38}[/cyan] {markup_escape(repr(v)[:80])}")

        self._log("")

    def _cmd_config(self) -> None:
        self._log("\n[bold]Current configuration:[/bold]")
        self._log(f"  [cyan]{'goal':<22}[/cyan] {self._config.get('goal') or '(none)'}")
        slots = self._config.get("goal_slots") or {}
        if slots:
            self._log(f"  [cyan]{'goal_slots':<22}[/cyan] {slots}")
        self._log(f"  [cyan]{'kb_path':<22}[/cyan] {self._config.get('kb_path') or '(none)'}")
        self._log(f"  [cyan]{'max_steps':<22}[/cyan] {self._config.get('max_steps', 20)}")
        dm_seed = self._config.get("dm_seed") or {}
        if dm_seed:
            self._log(f"  [cyan]{'dm_seed':<22}[/cyan] {dm_seed}")
        entity_scopes = self._config.get("entity_scopes") or {}
        if entity_scopes:
            self._log(f"  [cyan]{'entity_scopes':<22}[/cyan]")
            for label, slots in entity_scopes.items():
                self._log(f"    [dim]@{label}[/dim] {slots}")
        self._log(f"  [cyan]{'verbosity':<22}[/cyan] {self._verbosity} ({self._verbosity_label()})")
        self._log("")

    def _cmd_step(self) -> None:
        if self._step_paused:
            # Toggle step mode off and immediately resume the waiting runner
            self._step_mode = False
            self._resume_step()
            self._log("[dim]Step mode off — running freely.[/dim]")
        else:
            self._step_mode = not self._step_mode
            state = "on" if self._step_mode else "off"
            self._log(
                f"[dim]Step mode {state}."
                + (" Pauses after each step — Enter to advance." if self._step_mode else "")
                + "[/dim]"
            )

    def _resume_step(self) -> None:
        """Release the step gate and restore normal mode."""
        self._step_paused = False
        self._set_mode(self._MODE_NORMAL)
        self.query_one("#cmd-input", CommandInput).focus()
        if self._runner:
            self._runner.continue_step()

    def _cmd_query(self, slot: str) -> None:
        """Show the current DM or KB value for a slot name."""
        runner = self._runner
        dm = runner.dm if runner else None
        kb = runner.kb if runner else None
        found = False
        if dm and slot in dm.keys():
            v = dm.get(slot)
            self._log(
                f"[cyan]{markup_escape(slot)}[/cyan]"
                f" = {markup_escape(repr(v)[:300])}"
            )
            found = True
        if kb and slot in kb.keys():
            v = kb.get(slot)
            if not found:
                self._log(
                    f"[dim][kb][/dim] [cyan]{markup_escape(slot)}[/cyan]"
                    f" = {markup_escape(repr(v)[:300])}"
                )
            found = True
        if not found:
            self._log(f"[dim]{markup_escape(slot)}: not in DM or KB[/dim]")

    def _cmd_verbose(self, arg: str) -> None:
        if arg in ("0", "1", "2"):
            self._verbosity = int(arg)
        else:
            self._verbosity = (self._verbosity + 1) % 3
        self._log(f"[dim]Verbosity {self._verbosity}: {self._verbosity_label()}[/dim]")

    def _cmd_save(self, name: str) -> None:
        if not name:
            self._log("[red]Usage: /save <name>[/red]")
            return
        profiles = _load_profiles()
        profile_data = {
            k: v for k, v in self._config.items()
            if k not in ("goal", "goal_slots")  # goal is per-session, not saved
        }
        profile_data["verbosity"] = self._verbosity
        profiles[name] = profile_data
        _save_profiles(profiles)
        self._log(f"[green]Saved profile:[/green] {name}")

    def _cmd_profile(self, name: str) -> None:
        if not name:
            self._log("[red]Usage: /profile <name>[/red]")
            return
        profiles = _load_profiles()
        if name not in profiles:
            self._log(f"[red]Profile '{name}' not found — try [cyan]/profiles[/cyan][/red]")
            return
        profile_data = dict(profiles[name])
        self._verbosity = profile_data.pop("verbosity", 1)
        self._config = {**DEFAULT_CONFIG, **profile_data}
        self._log(f"[green]Loaded profile:[/green] {name}")

    def _cmd_profiles(self) -> None:
        profiles = _load_profiles()
        if not profiles:
            self._log("[dim]No saved profiles.[/dim]")
            return
        self._log("\n[bold]Saved profiles:[/bold]")
        for name, cfg in sorted(profiles.items()):
            kb = cfg.get("kb_path", "")
            self._log(f"  [cyan]{name:<18}[/cyan] kb={markup_escape(str(kb)[:50])}")
        self._log("")

    def _cmd_delete(self, name: str) -> None:
        if not name:
            self._log("[red]Usage: /delete <name>[/red]")
            return
        profiles = _load_profiles()
        if name not in profiles:
            self._log(f"[red]Profile '{name}' not found.[/red]")
            return
        del profiles[name]
        _save_profiles(profiles)
        self._log(f"[green]Deleted profile:[/green] {name}")

    def _cmd_clear(self) -> None:
        if self._running:
            self._cmd_stop()
        self.query_one("#output-log", RichLog).clear()

    def _cmd_logs(self) -> None:
        sessions_base = Path.home() / ".harneskills" / "sessions"
        if not sessions_base.exists():
            self._log("[dim]No session logs found.[/dim]")
            return
        dirs = sorted(
            [d for d in sessions_base.iterdir()
             if d.is_dir() and (d / "session.log").exists()],
            key=lambda d: d.stat().st_mtime, reverse=True,
        )
        if not dirs:
            self._log("[dim]No session logs found.[/dim]")
            return
        self._log(f"\n[bold]Session logs[/bold] ({sessions_base})")
        for n, d in enumerate(dirs[:20], 1):
            size = (d / "session.log").stat().st_size
            self._log(f"  [cyan]{n:2}.[/cyan] {d.name}  [dim]{size} B[/dim]")
        if len(dirs) > 20:
            self._log(f"  [dim]… {len(dirs) - 20} more[/dim]")
        self._log("[dim]Use [cyan]/log <n>[/cyan] to open.  [cyan]/log[/cyan] = most recent.[/dim]\n")

    def _cmd_log(self, arg: str) -> None:
        sessions_base = Path.home() / ".harneskills" / "sessions"
        dirs = sorted(
            [d for d in sessions_base.iterdir()
             if d.is_dir() and (d / "session.log").exists()],
            key=lambda d: d.stat().st_mtime, reverse=True,
        ) if sessions_base.exists() else []
        if not dirs:
            self._log("[dim]No session logs found.[/dim]")
            return
        if arg.isdigit():
            idx = int(arg) - 1
            if not (0 <= idx < len(dirs)):
                self._log(f"[red]No session #{arg}[/red]")
                return
            target = dirs[idx]
        else:
            target = dirs[0]
        self.app.push_screen(LogViewModal(target / "session.log"))

    # ------------------------------------------------------------------
    # Engine event handlers
    # ------------------------------------------------------------------

    def on_step_event(self, event: StepEvent) -> None:
        self._step_count = event.step_num
        max_steps = self._config.get("max_steps", 20)

        if self._session_log:
            self._session_log.write(
                f"[step {event.step_num}] tool={event.tool_id}"
                f" rule={event.rule_line}"
                f" slots={event.slots_committed}"
                f" residuals={event.residuals}"
            )

        # Step header + condensed rule line (always shown)
        self._log(
            f"[bold][{event.step_num}/{max_steps}][/bold]"
            f"  [cyan]{markup_escape(event.tool_id)}[/cyan]"
        )
        if event.pre_values or event.post_values:
            for slot, val in event.pre_values.items():
                self._log(
                    f"    [dim]{markup_escape(slot)}[/dim]"
                    f" = [white]{markup_escape(val)}[/white]"
                )
            if event.pre_values and event.post_values:
                self._log("    [dim]↓[/dim]")
            for slot, val in event.post_values.items():
                self._log(
                    f"    [dim]{markup_escape(slot)}[/dim]"
                    f" = [green]{markup_escape(val)}[/green]"
                )
        elif event.rule_line:
            self._log(f"  [dim]{markup_escape(event.rule_line)}[/dim]")

        if self._verbosity >= 1 and event.slots_committed:
            slots_str = "  ".join(
                f"[green]{markup_escape(s)}[/green]" for s in event.slots_committed
            )
            self._log(f"  ✓ {slots_str}")

        if self._verbosity >= 2 and event.residuals:
            res_str = "  ".join(
                f"[yellow]{markup_escape(r)}[/yellow]" for r in event.residuals
            )
            self._log(f"  ⚠ residuals: {res_str}")

        # Step mode: pause and wait for user to press Enter
        if self._step_mode and self._running:
            self._step_paused = True
            self._set_mode(self._MODE_STEP)
            self._set_status(
                f"paused after step {event.step_num}/{max_steps}"
                f"  ·  Enter = next  /stop = abort  /step = free-run"
            )
            self.query_one("#cmd-input", CommandInput).focus()

    def on_goal_reached_event(self, event: GoalReachedEvent) -> None:
        self._running = False
        self._step_paused = False
        if self._spinner_timer:
            self._spinner_timer.pause()
        self._set_mode(self._MODE_NORMAL)
        self._refresh_status()

        if self._session_log:
            self._session_log.write(f"=== goal_reached in {event.steps_taken} steps ===")

        self._log(
            f"\n[bold green]✓ Goal reached[/bold green]"
            f"  [dim]({event.steps_taken} step{'s' if event.steps_taken != 1 else ''})[/dim]"
        )
        if self._verbosity >= 1 and event.evidence:
            for e in event.evidence[-3:]:
                self._log(f"  [dim]{markup_escape(e[:120])}[/dim]")
        self._log(
            "\n[dim]Type a new goal and press [cyan]Enter[/cyan],"
            " or [cyan]/dm[/cyan] to inspect the domain model.[/dim]"
        )
        self._set_status(
            f"Goal reached  ({event.steps_taken} steps)  ·  type /dm or a new goal"
        )
        self.query_one("#cmd-input", CommandInput).focus()

    def on_impasse_event(self, event: ImpasseEvent) -> None:
        self._running = False
        self._step_paused = False
        if self._spinner_timer:
            self._spinner_timer.pause()
        self._set_mode(self._MODE_NORMAL)
        self._refresh_status()

        if self._session_log:
            self._session_log.write(
                f"=== impasse: {event.reason}  evidence={event.evidence} ==="
            )

        self._log(f"\n[bold yellow]⚠ Impasse:[/bold yellow] {markup_escape(event.reason)}")
        if event.evidence:
            for e in event.evidence:
                self._log(f"  [dim]{markup_escape(e[:120])}[/dim]")
        self._log(
            "\n[dim]Use [cyan]/dm[/cyan] to inspect state."
            "  Consider seeding more slots with [cyan]/seed[/cyan].[/dim]"
        )
        self._set_status("Impasse  ·  see evidence above  ·  /dm for state")
        self.query_one("#cmd-input", CommandInput).focus()

    def on_status_event(self, event: StatusEvent) -> None:
        max_steps = self._config.get("max_steps", 20)
        goal_preview = self._config.get("goal", "")[:40]
        self._set_status(
            f"step {event.step}/{max_steps}"
            f"  ·  {goal_preview}"
        )

    def on_error_event(self, event: ErrorEvent) -> None:
        self._running = False
        self._step_paused = False
        if self._spinner_timer:
            self._spinner_timer.pause()
        self._set_mode(self._MODE_NORMAL)
        self._refresh_status()
        if self._session_log:
            self._session_log.write(f"=== ERROR: {event.error[:400]} ===")
        self._log(f"\n[bold red]✗ Error[/bold red]\n{markup_escape(event.error[:600])}")
        self._set_status("Error — session stopped.")
        self.query_one("#cmd-input", CommandInput).focus()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _verbosity_label(self) -> str:
        return [
            "steps only",
            "steps + committed slots",
            "steps + slots + residuals",
        ][self._verbosity]
