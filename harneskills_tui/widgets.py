from __future__ import annotations

from typing import Any

from textual.binding import Binding
from textual.message import Message
from textual.widgets import Static, TextArea

from .constants import SLASH_COMMANDS


class CommandSuggestions(Static):
    """Filterable list of slash-command completions shown above the input bar."""

    _VISIBLE_ROWS = 10

    DEFAULT_CSS = """
    CommandSuggestions {
        display: none;
        height: auto;
        max-height: 12;
        background: $surface;
        border-top: solid $accent;
        padding: 0 1;
    }
    CommandSuggestions.active { display: block; }
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__("", markup=True, **kwargs)
        self._matches: list[tuple[str, str]] = []
        self._idx: int = 0
        self._query_mode: bool = False

    def filter(
        self,
        text: str,
        extra_items: list[tuple[str, str]] | None = None,
    ) -> None:
        if text.startswith("?"):
            prefix = text[1:]
            self._query_mode = True
            if extra_items is None:
                self._matches = []
            else:
                self._matches = [
                    (name, desc) for name, desc in extra_items
                    if name.startswith(prefix)
                ]
        elif text.startswith("/"):
            self._query_mode = False
            word = text.split()[0] if text.split() else text
            self._matches = [
                (cmd, desc) for cmd, desc in SLASH_COMMANDS.items()
                if cmd.startswith(word)
            ]
        else:
            self._query_mode = False
            self._matches = []

        self._idx = min(self._idx, max(0, len(self._matches) - 1))
        if self._matches:
            self._refresh_suggestions()
            self.add_class("active")
        else:
            self._idx = 0
            self.remove_class("active")
            self.update("")

    def move(self, delta: int) -> None:
        if not self._matches:
            return
        self._idx = (self._idx + delta) % len(self._matches)
        self._refresh_suggestions()

    def selected_command(self) -> str | None:
        """Return the value to insert on Tab (slot name or command string)."""
        if self._matches and 0 <= self._idx < len(self._matches):
            return self._matches[self._idx][0]
        return None

    def is_query_mode(self) -> bool:
        return self._query_mode

    def has_suggestions(self) -> bool:
        return bool(self._matches)

    def _refresh_suggestions(self) -> None:
        total = len(self._matches)
        start = max(0, min(self._idx - self._VISIBLE_ROWS + 1, total - self._VISIBLE_ROWS))
        end = min(start + self._VISIBLE_ROWS, total)
        parts: list[str] = []
        if start > 0:
            parts.append(f"  [dim]▲ {start} more[/dim]")
        for i in range(start, end):
            cmd, desc = self._matches[i]
            if i == self._idx:
                parts.append(f"[bold reverse] {cmd:<24}[/bold reverse] [dim]{desc}[/dim]")
            else:
                parts.append(f"  [cyan]{cmd:<24}[/cyan] [dim]{desc}[/dim]")
        remaining = total - end
        if remaining > 0:
            parts.append(f"  [dim]▼ {remaining} more[/dim]")
        self.update("\n".join(parts))


class CommandInput(TextArea):
    """Multiline command input with history, autocomplete, and Ctrl+T multiline toggle."""

    BINDINGS = [
        Binding("up", "history_prev", show=False),
        Binding("down", "history_next", show=False),
        Binding("pageup", "history_pageup", show=False),
        Binding("pagedown", "history_pagedown", show=False),
    ]

    class Submitted(Message):
        def __init__(self, widget: CommandInput, value: str) -> None:
            self.widget = widget
            self.value = value
            super().__init__()

    class ModeToggled(Message):
        def __init__(self, widget: CommandInput, multiline: bool) -> None:
            self.widget = widget
            self.multiline = multiline
            super().__init__()

    def __init__(self, placeholder: str = "", **kwargs: Any) -> None:
        super().__init__(
            show_line_numbers=False,
            soft_wrap=True,
            tab_behavior="focus",
            highlight_cursor_line=False,
            placeholder=placeholder,
            compact=True,
            **kwargs,
        )
        self._history: list[str] = []
        self._history_idx: int = -1
        self._history_draft: str = ""
        self._multiline_mode: bool = False

    def add_to_history(self, text: str) -> None:
        if text and (not self._history or self._history[-1] != text):
            self._history.append(text)
        self._history_idx = -1
        self._history_draft = ""

    def _set_text(self, text: str) -> None:
        self.load_text(text)
        lines = text.split("\n")
        self.cursor_location = (len(lines) - 1, len(lines[-1]))

    async def _on_key(self, event: Any) -> None:
        suggestions: CommandSuggestions | None = None
        try:
            suggestions = self.screen.query_one(CommandSuggestions)
        except Exception:
            pass

        if suggestions is not None and suggestions.has_suggestions():
            if event.key == "up":
                suggestions.move(-1)
                event.prevent_default(); event.stop(); return
            if event.key == "down":
                suggestions.move(1)
                event.prevent_default(); event.stop(); return
            if event.key == "tab":
                cmd = suggestions.selected_command()
                if cmd:
                    if suggestions.is_query_mode():
                        # Replace ?prefix with the bare slot name
                        self._set_text(cmd)
                        suggestions.filter("")
                    else:
                        self._set_text(cmd + " ")
                        suggestions.filter(cmd + " ")
                event.prevent_default(); event.stop(); return
            if event.key == "escape":
                suggestions.filter("")
                event.prevent_default(); event.stop(); return

        if event.key == "ctrl+t":
            self._multiline_mode = not self._multiline_mode
            self.post_message(self.ModeToggled(self, self._multiline_mode))
            event.prevent_default(); event.stop(); return

        if event.key == "ctrl+s" or (event.key == "enter" and not self._multiline_mode):
            text = self.text.strip()
            self.clear()
            self.post_message(self.Submitted(self, text))
            event.prevent_default(); event.stop(); return

        await super()._on_key(event)

    def action_history_prev(self) -> None:
        if "\n" not in self.text:
            if self._history:
                if self._history_idx == -1:
                    self._history_draft = self.text
                    self._history_idx = len(self._history) - 1
                elif self._history_idx > 0:
                    self._history_idx -= 1
                self._set_text(self._history[self._history_idx])
        else:
            self.action_cursor_up()

    def action_history_next(self) -> None:
        if "\n" not in self.text:
            if self._history_idx != -1:
                if self._history_idx < len(self._history) - 1:
                    self._history_idx += 1
                    self._set_text(self._history[self._history_idx])
                else:
                    self._history_idx = -1
                    self._set_text(self._history_draft)
        else:
            self.action_cursor_down()

    def action_history_pageup(self) -> None:
        if self._history:
            if self._history_idx == -1:
                self._history_draft = self.text
                self._history_idx = len(self._history) - 1
            elif self._history_idx > 0:
                self._history_idx -= 1
            self._set_text(self._history[self._history_idx])

    def action_history_pagedown(self) -> None:
        if self._history_idx != -1:
            if self._history_idx < len(self._history) - 1:
                self._history_idx += 1
                self._set_text(self._history[self._history_idx])
            else:
                self._history_idx = -1
                self._set_text(self._history_draft)
