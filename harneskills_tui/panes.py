"""The graph pane: what the machine currently believes, wants and can do.

Three views of one machine, because a reader has three different questions and
one table cannot answer all of them:

    asked for   the goal / plan / subgoal tree -- *is it getting anywhere?*
    graph       every settled proposition in a layer -- *what does it believe?*
    rules       what can come to mind, and what has applied -- *with what?*

All three are re-read from the machine on `refresh_from`; none of them keeps
state of its own beyond the cursor. That is what makes the pane safe to update on
a timer while a run drives: it is a rendering, so a stale one is merely old and
never wrong.

⚠ Reading happens under `runner.lock`, because the driver ticks on a worker
thread. Without it a render can walk the graph half way through a moment and show
a proposition whose entry has not been deposited yet. ⚠⚠ But the lock is taken
**without blocking** — see `refresh_from`, where the reason is the difference
between a stale pane and a dead window.
"""

from __future__ import annotations

from typing import List

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.message import Message
from textual.widgets import DataTable, Static, Tabs, Tab, Tree

import harneskills as h

#: The layers offered in the pane's cycle, world first because that is what the
#: corpus is actually about. `meta` is reachable but last -- it is by far the
#: biggest and by far the least often wanted.
PANE_LAYERS = ("world", "goal", "act", "search", "talk", "meta")

_STATUS_STYLE = {
    "held": "green",
    "denied": "red",
    "unsure": "yellow",
    "unsettled": "magenta",
    "BLOCKED": "bold red",
    "open": "yellow",
}


def _paint(text: str, status: str) -> str:
    style = _STATUS_STYLE.get(status)
    return f"[{style}]{text}[/{style}]" if style else text


class GraphPane(Vertical):
    """A live look at the machine, beside the transcript."""

    DEFAULT_CSS = """
    /* ⚠ A fraction, not a percentage. A percentage width resolves against the
       container rather than against what is left of it, so `1fr` beside `45%`
       asked for 145% of the row -- the transcript kept its full width and the
       pane was drawn on top of it. Two fractions always sum to the row. */
    GraphPane {
        width: 2fr;
        min-width: 34;
        border-left: solid $accent;
        padding: 0 1;
    }
    GraphPane #pane-head { height: 1; color: $text-muted; }
    GraphPane Tabs { height: 2; }
    GraphPane #pane-tree { height: 1fr; }
    GraphPane #pane-table { height: 1fr; }
    GraphPane #pane-rules { height: 1fr; overflow-y: auto; }
    """

    class Explain(Message):
        """A row was chosen: show its provenance in the transcript."""

        def __init__(self, term: str) -> None:
            super().__init__()
            self.term = term

    def __init__(self, runner, **kwargs) -> None:
        super().__init__(**kwargs)
        self.runner = runner
        self.layer_index = 0
        self._view = "asked for"
        self._terms: List[str] = []   # row index -> term, for Explain

    # -- layout -------------------------------------------------------------

    def compose(self) -> ComposeResult:
        yield Static("", id="pane-head", markup=True)
        # ⚠ `play` is always present rather than added when a scenario loads.
        # Textual can add a tab at runtime, but a tab strip that changes shape
        # under the cursor moves whatever the reader was looking at; an empty
        # view that says why it is empty costs one line and never surprises.
        yield Tabs(
            Tab("asked for", id="tab-goals"),
            Tab("graph", id="tab-graph"),
            Tab("rules", id="tab-rules"),
            Tab("play", id="tab-play"),
        )
        yield Tree("asked for", id="pane-tree")
        table = DataTable(id="pane-table", cursor_type="row", zebra_stripes=True)
        table.display = False
        yield table
        rules = Static("", id="pane-rules", markup=True)
        rules.display = False
        yield rules
        board = Static("", id="pane-play", markup=True)
        board.display = False
        yield board

    def on_mount(self) -> None:
        table = self.query_one("#pane-table", DataTable)
        table.add_columns("", "proposition", "at", "via")
        self.query_one("#pane-tree", Tree).show_root = False
        self.refresh_from()

    # -- switching ----------------------------------------------------------

    def on_tabs_tab_activated(self, event: Tabs.TabActivated) -> None:
        self._view = str(event.tab.label)
        self._apply_view()
        self.refresh_from()

    def _apply_view(self) -> None:
        self.query_one("#pane-tree", Tree).display = self._view == "asked for"
        self.query_one("#pane-table", DataTable).display = self._view == "graph"
        self.query_one("#pane-rules", Static).display = self._view == "rules"
        self.query_one("#pane-play", Static).display = self._view == "play"

    def show_play(self) -> None:
        """Switch to the scoreboard — called when a scenario is loaded, because
        that is unambiguously what the reader now wants to look at."""
        self._view = "play"
        self.query_one(Tabs).active = "tab-play"
        self._apply_view()
        self.refresh_from()

    def cycle_layer(self) -> str:
        """Next layer for the `graph` view, switching to it if elsewhere."""
        self.layer_index = (self.layer_index + 1) % len(PANE_LAYERS)
        if self._view != "graph":
            self._view = "graph"
            self.query_one(Tabs).active = "tab-graph"
            self._apply_view()
        self.refresh_from()
        return PANE_LAYERS[self.layer_index]

    @property
    def current_layer(self) -> str:
        """⚠⚠ NOT `layer`. `Widget.layer` is Textual's own -- the compositor reads
        it to decide which CSS layer to place a widget in -- and shadowing it
        with a property returning `"world"` put every widget in a layer that
        does not exist, so the transcript and this pane were both arranged at
        x=0 at full width and drawn on top of each other. The symptom looks like
        a sizing bug and is not one; the name is the bug."""
        return PANE_LAYERS[self.layer_index]

    # -- rendering ----------------------------------------------------------

    def refresh_from(self) -> None:
        """Re-read the machine. Cheap enough to call on a timer, and idempotent.

        ⚠⚠⚠ **The lock is taken without blocking, and skipping is the correct
        outcome.** The driver holds it for the whole of a tick -- and a tick that
        consults the human tool holds it until the person answers. A blocking
        acquire here therefore deadlocks the session outright: the UI thread
        waits for the driver, the driver waits for the UI thread to deliver the
        answer, and the window is dead with the question on screen.

        A skipped refresh costs nothing, because this is a rendering and a stale
        rendering is merely old. The timer comes back in 200ms.
        """
        if not self.runner.lock.acquire(blocking=False):
            return
        try:
            m = self.runner.machine
            if self._view == "asked for":
                self._fill_tree(m)
            elif self._view == "graph":
                self._fill_table(m)
            elif self._view == "play":
                self._fill_play()
            else:
                self._fill_rules(m)
            self._fill_head(m)
        finally:
            self.runner.lock.release()

    def _fill_head(self, m) -> None:
        counts = h.counts(m)
        state = self.runner.state
        bits = " ".join(
            f"[dim]{name}[/dim] {counts.get(name, 0)}"
            for name in ("world", "goal", "act")
        )
        tail = f"[dim]layer[/dim] {self.current_layer}" if self._view == "graph" else ""
        self.query_one("#pane-head", Static).update(
            f"{bits}   [dim]ticks[/dim] {len(self.runner.steps)} [dim]{state}[/dim]   {tail}"
        )

    def _fill_tree(self, m) -> None:
        tree = self.query_one("#pane-tree", Tree)
        tree.clear()
        rows = h.goal_tree(m)
        if not rows:
            tree.root.add_leaf("nothing was asked for")
            return
        # `report()` hands back indentation; rebuild the nesting from it by
        # remembering the last node seen at each depth. Nothing is inferred --
        # the depths are the engine's own and this only re-hangs them. A section
        # header resets the map, because `did:` starts a fresh subtree rather
        # than continuing the goal tree above it.
        at_depth = {0: tree.root}
        for row in rows:
            if row.kind == "section":
                at_depth = {0: tree.root.add(f"[bold]{row.text}[/bold]", expand=True)}
                continue
            parent = at_depth.get(row.depth - 1) or at_depth[0]
            label = _paint(row.text, row.status) if row.status else row.text
            at_depth[row.depth] = parent.add(label, expand=True)

    def _fill_table(self, m) -> None:
        table = self.query_one("#pane-table", DataTable)
        table.clear()
        self._terms = []
        rows = h.propositions(m, [self.current_layer],
                             generic=self.current_layer == "goal")
        for p in rows:
            self._terms.append(p.text)
            table.add_row(
                _paint(p.sign or "?", p.status),
                _paint(p.text, p.status),
                f"M{p.moment}",
                p.source or "",
            )
        if not rows:
            self._terms.append("")
            table.add_row("", "[dim]nothing in this layer yet[/dim]", "", "")

    def _fill_play(self) -> None:
        """The scenario's own scoreboard, whatever it says it is.

        The pane knows nothing about hit points. A scenario hands back lines and
        this colours the two words every game has -- who is up, and how it
        ended -- which is as much domain knowledge as a viewer should hold.
        """
        scenario = self.runner.scenario
        if scenario is None:
            self.query_one("#pane-play", Static).update(
                "[dim]nothing is being played[/dim]\n\n"
                "  [cyan]/scenarios[/cyan]  what there is\n"
                "  [cyan]/play dungeon 7[/cyan]  a seeded fight"
            )
            return
        out = [f"[bold]{scenario.name}[/bold]", ""]
        for line in scenario.status(self.runner):
            if line.startswith(">"):
                out.append(f"[bold yellow]{line}[/bold yellow]")
            elif line.startswith("the fight is over") or line.startswith("over"):
                out.append(f"[bold green]{line}[/bold green]")
            elif " down" in line or line.endswith("down"):
                out.append(f"[dim]{line}[/dim]")
            else:
                out.append(line)
        self.query_one("#pane-play", Static).update("\n".join(out))

    def _fill_rules(self, m) -> None:
        rows = h.rules(m)
        out: List[str] = []
        for r in rows:
            mark = "[green]*[/green]" if r.exercised else " "
            out.append(f"{mark} [bold cyan]<{r.name}>[/bold cyan] [dim]{r.connective}[/dim]")
            out.append(f"    [dim]when[/dim]  {', '.join(r.antecedent) or '-'}")
            out.append(f"    [dim]then[/dim]  {', '.join(r.consequent) or '-'}")
        if not rows:
            out = ["[dim]no rules authored yet[/dim]"]
        else:
            out.append("")
            out.append("[dim]* = it has applied at least once[/dim]")
        tools = h.tools(m)
        authored = [t for t in tools if t[0] == "human"]
        if authored:
            out.append("")
            out.append("[bold]tools[/bold]")
            for name, req, trusted in authored:
                out.append(f"  [cyan]<{name}>[/cyan] answers {req}"
                           + ("" if trusted else " [dim](retired)[/dim]"))
        self.query_one("#pane-rules", Static).update("\n".join(out))

    # -- explaining ---------------------------------------------------------

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        if 0 <= event.cursor_row < len(self._terms) and self._terms[event.cursor_row]:
            self.post_message(self.Explain(self._terms[event.cursor_row]))

    def on_tree_node_selected(self, event: Tree.NodeSelected) -> None:
        label = str(event.node.label)
        term = _strip_markup(label).split("  [")[0].split("  via ")[0].strip()
        if term and not term.endswith(":"):
            self.post_message(self.Explain(term))


def _strip_markup(text: str) -> str:
    """Rich markup back off a label, so a chosen row yields a term the loader can
    parse. Cheap and sufficient: the only markup this pane emits is colour."""
    out, depth = [], 0
    for ch in text:
        if ch == "[":
            depth += 1
        elif ch == "]":
            depth = max(0, depth - 1)
        elif depth == 0:
            out.append(ch)
    return "".join(out)
