from __future__ import annotations

from textual.app import App
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import Static

from .screen import CLIScreen


class SplashScreen(Screen):
    DEFAULT_CSS = """
    SplashScreen {
        align: center middle;
        background: $surface;
    }
    #splash-box {
        width: 52;
        height: auto;
        border: double $primary;
        padding: 1 3;
        background: $surface;
    }
    #splash-title {
        text-align: center;
        color: $primary;
        text-style: bold;
    }
    #splash-subtitle {
        text-align: center;
        color: $text-muted;
    }
    #splash-loading {
        text-align: center;
        color: $warning;
        padding: 1 0;
    }
    """

    _LOADING_FRAMES = ["loading   ", "loading.  ", "loading.. ", "loading..."]

    def compose(self):
        with Vertical(id="splash-box"):
            yield Static("harneskills", id="splash-title", markup=False)
            yield Static("KB-driven harness engine", id="splash-subtitle", markup=False)
            yield Static(self._LOADING_FRAMES[0], id="splash-loading", markup=False)

    def on_mount(self) -> None:
        self._anim_frame: int = 0
        self.set_interval(0.1, self._tick_anim)
        self.set_timer(1.0, self._auto_dismiss)

    async def _auto_dismiss(self) -> None:
        self.dismiss()

    def _tick_anim(self) -> None:
        self._anim_frame += 1
        self.query_one("#splash-loading", Static).update(
            self._LOADING_FRAMES[self._anim_frame % len(self._LOADING_FRAMES)]
        )


class HarneskillsTUI(App):
    TITLE = "harneskills"
    SUB_TITLE = "KB-driven harness engine"

    BINDINGS = [Binding("ctrl+q", "quit", "Quit")]

    def on_mount(self) -> None:
        self.push_screen(SplashScreen(), callback=lambda _: self.push_screen(CLIScreen()))


def main() -> None:
    HarneskillsTUI().run()
