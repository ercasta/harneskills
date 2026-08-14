"""The TUI, driven headlessly through Textual's pilot.

Not a screenshot test. What these assert is that the wiring holds: that the
screen composes, that a typed line reaches the command layer, that the graph pane
re-reads the machine, and -- the one that is genuinely easy to get wrong -- that
the human-as-a-tool question crosses two thread boundaries and comes back.
"""

from __future__ import annotations

import pytest

from harneskills_tui.app import HarneskillsTUI
from harneskills_tui.panes import GraphPane
from harneskills_tui.screen import CLIScreen
from harneskills_tui.widgets import CommandInput

pytestmark = pytest.mark.asyncio

KETTLE = (
    "rule <boiling> = causes( { +doing(heat(?w)), +water(?w) }, { +boiling(?w) } )\n"
    "rule <commit>  = implies( { +goal(doing(?a)) }, { +doing(?a) } )\n"
    "fact +water(kettle)\n"
    "fact +goal(boiling(kettle))\n"
)


async def _type(pilot, text: str) -> None:
    """Put a line in the prompt and submit it the way a person would."""
    screen = pilot.app.screen
    field = screen.query_one(CommandInput)
    field.load_text(text)
    field.post_message(CommandInput.Submitted(field, text))
    await pilot.pause()


async def _settle(pilot, screen, seconds: float = 5.0) -> None:
    """Wait for a drive to finish, pumping the event loop as it goes."""
    for _ in range(int(seconds / 0.05)):
        if not screen._driving:
            return
        await pilot.pause(0.05)
    raise AssertionError("the drive never finished")


async def test_the_screen_composes_with_a_transcript_and_a_pane():
    async with HarneskillsTUI().run_test() as pilot:
        await pilot.pause()
        screen = pilot.app.screen
        assert isinstance(screen, CLIScreen)
        assert screen.query_one("#transcript")
        assert screen.query_one("#pane", GraphPane)


async def test_a_typed_statement_reaches_the_machine_without_thinking():
    async with HarneskillsTUI().run_test() as pilot:
        await pilot.pause()
        runner = pilot.app.screen.driver.runner
        await _type(pilot, "rule <b> = causes( { +water(?w) }, { +wet(?w) } )")
        await _type(pilot, "fact +water(kettle)")
        # An authored fact is deposited at load, so it holds at once...
        assert runner.holds("water(kettle)") == "+"
        # ...but nothing has been DERIVED, because authoring does not think.
        assert runner.steps == []
        assert runner.holds("wet(kettle)") is None


async def test_running_drives_to_quiescence_and_fills_the_pane():
    async with HarneskillsTUI().run_test() as pilot:
        await pilot.pause()
        screen = pilot.app.screen
        for line in KETTLE.strip().splitlines():
            await _type(pilot, line)
        await _type(pilot, "/run")
        await _settle(pilot, screen)
        assert screen.driver.runner.holds("boiling(kettle)") == "+"
        pane = screen.query_one("#pane", GraphPane)
        pane.refresh_from()
        tree = pane.query_one("#pane-tree")
        assert tree.root.children, "the goal tree should not be empty"


async def test_the_pane_cycles_layers():
    async with HarneskillsTUI().run_test() as pilot:
        await pilot.pause()
        pane = pilot.app.screen.query_one("#pane", GraphPane)
        first = pane.current_layer
        second = pane.cycle_layer()
        assert second != first


async def test_a_bad_line_is_shown_and_does_not_kill_the_session():
    async with HarneskillsTUI().run_test() as pilot:
        await pilot.pause()
        screen = pilot.app.screen
        await _type(pilot, "fact +p(a) @certain")
        await _type(pilot, "fact +p(a)")
        assert screen.driver.runner.machine.g.count() > 0
        assert pilot.app.is_running


async def test_the_agent_asks_and_the_prompt_answers_it():
    """The one that crosses threads: the driver blocks on the human tool, the
    screen shows the question, the next typed line is the answer."""
    async with HarneskillsTUI().run_test() as pilot:
        await pilot.pause()
        screen = pilot.app.screen
        for line in (
            "rule <curious> = implies( { +goal(?w) }, { +ask(?w) } )",
            "rule <believe> = implies( { +answered(<human>, ?q, ?a) }, { +?a } )",
            "fact +goal(weather(today))",
        ):
            await _type(pilot, line)
        await _type(pilot, "/run")

        for _ in range(100):                     # wait for the question
            if screen.driver.waiting:
                break
            await pilot.pause(0.05)
        assert screen.driver.waiting, "the agent never asked"

        await _type(pilot, "sunny(here)")
        await _settle(pilot, screen)
        assert screen.driver.runner.holds("sunny(here)") == "+"


async def test_the_pane_refreshes_while_a_question_is_pending():
    """⚠ The regression that hung the window. A tick that consults the human
    holds the runner lock until the person answers; a pane that acquired that
    lock blocking could never return, so the UI thread could never deliver the
    answer, and the session deadlocked with the question on screen."""
    async with HarneskillsTUI().run_test() as pilot:
        await pilot.pause()
        screen = pilot.app.screen
        for line in (
            "rule <curious> = implies( { +goal(?w) }, { +ask(?w) } )",
            "fact +goal(weather(today))",
        ):
            await _type(pilot, line)
        await _type(pilot, "/run")
        for _ in range(100):
            if screen.driver.waiting:
                break
            await pilot.pause(0.05)
        assert screen.driver.waiting

        # This is the call the timer makes. It must return, not block.
        screen.query_one("#pane", GraphPane).refresh_from()
        await _type(pilot, "sunny(here)")
        await _settle(pilot, screen)
        assert not screen.driver.waiting


async def test_stopping_releases_an_outstanding_question():
    async with HarneskillsTUI().run_test() as pilot:
        await pilot.pause()
        screen = pilot.app.screen
        for line in (
            "rule <curious> = implies( { +goal(?w) }, { +ask(?w) } )",
            "fact +goal(weather(today))",
        ):
            await _type(pilot, line)
        await _type(pilot, "/run")
        for _ in range(100):
            if screen.driver.waiting:
                break
            await pilot.pause(0.05)
        screen.action_stop()
        await _settle(pilot, screen)
        assert not screen.driver.waiting


async def test_playing_the_dungeon_from_the_prompt():
    """A whole fight through the real screen: `/play`, `/run`, and a declaration
    typed at the prompt each time it stops and asks."""
    from harneskills.dungeon import corpus_path

    if corpus_path() is None:
        pytest.skip("this ugm build has no rules/dungeon.ugm")

    async with HarneskillsTUI().run_test() as pilot:
        await pilot.pause()
        screen = pilot.app.screen
        await _type(pilot, "/play dungeon 1")
        assert screen.driver.runner.scenario is not None
        pane = screen.query_one("#pane", GraphPane)
        assert pane._view == "play", "loading a scenario should show the scoreboard"

        await _type(pilot, "/run")
        for _ in range(400):                       # answer every cue it raises
            if not screen._driving:
                break
            if screen.driver.waiting:
                await _type(pilot, "attack(goblin1)")
            await pilot.pause(0.05)

        scenario = screen.driver.runner.scenario
        assert scenario.over(screen.driver.runner) is not None, "the fight should finish"
        pane.refresh_from()


async def test_loading_a_shipped_corpus_from_the_prompt():
    async with HarneskillsTUI().run_test() as pilot:
        await pilot.pause()
        screen = pilot.app.screen
        await _type(pilot, "/load corpus/kettle.ugm")
        await _type(pilot, "/run")
        await _settle(pilot, screen)
        assert screen.driver.runner.holds("boiling(kettle)") == "+"
