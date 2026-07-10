from __future__ import annotations

from pathlib import Path

from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import RichLog, Static


class LogViewModal(ModalScreen[None]):
    """Scrollable view of a plain-text session log file."""

    BINDINGS = [Binding("escape", "dismiss", "Close")]

    DEFAULT_CSS = """
    LogViewModal { align: center middle; }
    #lv-box {
        width: 95%; height: 90%;
        border: thick $accent;
        background: $surface;
        padding: 1 2;
    }
    #lv-hint { color: $text-muted; height: 1; margin-bottom: 1; }
    #lv-log  { height: 1fr; }
    """

    def __init__(self, log_path: Path) -> None:
        super().__init__()
        self._log_path = log_path

    def compose(self):
        with Vertical(id="lv-box"):
            yield Static(
                f"[bold]Session log[/bold] — {self._log_path.parent.name}  —  Escape to close",
                markup=True, id="lv-hint",
            )
            yield RichLog(id="lv-log", markup=False, wrap=True)

    def on_mount(self) -> None:
        log_widget = self.query_one("#lv-log", RichLog)
        try:
            text = self._log_path.read_text(encoding="utf-8")
            log_widget.write(text)
        except OSError:
            log_widget.write("Could not read log file.")
