"""What the terminal promises: a line in, a reply out, and nothing else
printed unasked -- now as one channel over a running `Engine`."""

import dataclasses
import io
import threading
import time

import pytest

from ugm.delta import spawn
from ugm.engine import Engine
from ugm.loop import Loop
from ugm.world import Reply, Said

from harneskills import repl

VOCAB = {"show", "file", "files", "big", "in", "stale", "after", "days"}


# --- autocorrect --------------------------------------------------------
# A module-level function now (`repl.autocorrect`), not the loop's own --
# any channel that wants it may call it, and the engine never does.

def test_a_near_miss_is_corrected_and_reported():
    line, fixes = repl.autocorrect("shwo file", VOCAB)
    assert (line, fixes) == ("show file", [("shwo", "show")])


def test_a_word_it_knows_is_left_exactly_alone():
    assert repl.autocorrect("show file", VOCAB) == ("show file", [])


def test_a_swapped_pair_counts_as_one_mistake():
    # The commonest way to mistype a word you know how to spell.
    assert repl.autocorrect("fiel", VOCAB)[1] == [("fiel", "file")]


def test_a_word_near_two_words_equally_is_not_guessed_at():
    # `dats` is one edit from `days` and one from `data`: ambiguous, so it
    # stays as typed and the domain's own systems decide it means nothing.
    line, fixes = repl.autocorrect("dats", VOCAB | {"data"})
    assert (line, fixes) == ("dats", [])


def test_a_word_too_far_from_anything_is_left_alone():
    assert repl.autocorrect("dinner", VOCAB) == ("dinner", [])


def test_a_short_word_has_to_be_closer_than_a_long_one():
    # `for` is two edits from `to`, which for a three-letter word is a
    # different word rather than a typo -- "what is for dinner" must not
    # become a sentence nobody typed.
    assert repl.autocorrect("what is for dinner", VOCAB | {"to"})[1] == []
    # Two edits into a long word is still unmistakable.
    assert repl.autocorrect("stalle", VOCAB)[1] == [("stalle", "stale")]


def test_two_characters_are_never_corrected():
    # At that length everything is near everything.
    assert repl.autocorrect("fi", VOCAB) == ("fi", [])


@pytest.mark.parametrize("path", [
    "/etc/rc.d", "~/Documnets", "..\\Windows", '"my notes"', "notes.txt"])
def test_a_path_is_never_corrected(path):
    line = "show file in %s" % path
    assert repl.autocorrect(line, VOCAB) == (line, [])


def test_correction_stops_at_a_path_and_does_not_resume():
    # Every word of a folder name is a word this prompt has no business
    # having an opinion about.
    line = "show file in /tmp/x stale big"
    assert repl.autocorrect(line, VOCAB)[0] == line


def test_spacing_is_preserved_exactly():
    assert repl.autocorrect("show   file", VOCAB)[0] == "show   file"


# --- a session, driven through a real Engine ---------------------------

def drive(loop, typed, timeout=2.0, **engine_kwargs):
    """Attach one `Terminal` to a fresh `Engine` around `loop`, type these
    lines at it, and give back everything printed once the engine stops.

    `engine.run()` blocks -- run it on its own thread and join with a
    timeout, so a test that leaves the engine running (a bug, not a
    feature) fails as a slow test rather than hanging the suite.
    """
    out = io.StringIO()
    engine = Engine(loop, **engine_kwargs)
    term = repl.Terminal(stdin=io.StringIO("".join(l + "\n" for l in typed)),
                         stdout=out, echo_prompt=False)
    engine.attach(term)
    thread = threading.Thread(target=engine.run, daemon=True)
    thread.start()
    thread.join(timeout)
    assert not thread.is_alive(), "the engine never stopped -- missing /quit?"
    return out.getvalue().splitlines()


@dataclasses.dataclass(frozen=True)
class Secret:
    pass


@pytest.fixture
def loop():
    lp = Loop()
    lp.world.learn("hello")

    @lp.system
    def greet(w):
        for entity, said in w.each(Said):
            if said.text == "hello":
                w.destroy(entity)
                w.spawn(Reply("user", "hello yourself"))
    return lp


def test_a_line_becomes_a_saying_and_a_reply_is_printed_bare(loop):
    assert "hello yourself" in drive(loop, ["hello", "/quit"])


def test_a_typo_is_corrected_against_what_a_domain_registered(loop):
    printed = drive(loop, ["helo", "/quit"])
    assert "  ~ helo -> hello" in printed
    assert "hello yourself" in printed


def test_a_line_no_system_took_is_reported_not_guessed_at(loop):
    assert "  (nothing understood: what is for dinner)" in drive(
        loop, ["what is for dinner", "/quit"])


def test_a_reply_to_another_channel_says_which(loop):
    # A `Reply` not addressed to "user" goes to the ONE channel by that
    # name -- not to everyone with a decorative prefix -- so this system
    # has to know the terminal's actual name, the way a domain that
    # tracked an asker's channel would.
    def gauge(w):
        if not w.each(Secret):
            w.spawn(Secret(), Reply("gauge", "97%"))

    out = io.StringIO()
    engine = Engine(loop)
    term = repl.Terminal(stdin=io.StringIO("/quit\n"), stdout=out, echo_prompt=False)
    term.name = "gauge"
    loop.system(gauge, name="gauge")
    engine.attach(term)
    thread = threading.Thread(target=engine.run, daemon=True)
    thread.start()
    thread.join(2.0)
    assert not thread.is_alive()
    assert "[gauge] 97%" in out.getvalue()


def test_nothing_else_a_system_spawns_reaches_the_terminal(loop):
    def quiet(w):
        if not w.each(Secret):
            w.spawn(Secret())
    loop.system(quiet, name="quiet")
    assert [l for l in drive(loop, ["hello", "/quit"]) if "Secret" in l] == []


def test_show_is_the_whole_world_on_demand(loop):
    # A `Reply` would not still be here to look at -- it is printed and
    # destroyed before the first prompt. Anything else stands.
    loop.world.spawn(Secret())
    printed = drive(loop, ["/show", "/quit"])
    assert any(line.strip() == "#1    Secret()" for line in printed)


def test_systems_lists_them_in_the_order_they_run(loop):
    loop.system(lambda w: None, name="second")
    printed = drive(loop, ["/systems", "/quit"])
    assert printed[-2:] == ["   1. test_repl.greet", "   2. second"]


def test_a_system_that_blew_up_is_named_at_the_prompt(loop):
    @loop.system
    def explodes(w):
        raise ValueError("nope")

    assert "  ! test_repl.explodes: ValueError: nope" in drive(loop, ["hello", "/quit"])


def test_a_system_that_never_settles_is_stopped_and_named(loop):
    loop.system(lambda w: [spawn(Secret())], name="ping")   # spawn is never idempotent
    printed = drive(loop, ["/quit"])
    assert any("still firing: ping" in l for l in printed)


def test_an_unknown_command_is_said_rather_than_typed_at_the_world(loop):
    assert "  ! no such command: /nope" in drive(
        loop, ["/nope", "/quit"], commands={"/other": lambda engine, arg: None})


def test_a_command_may_hand_back_a_whole_new_loop(loop):
    fresh = Loop()

    def announce(w):
        if not w.each(Secret):
            w.spawn(Secret(), Reply("user", "new world"))
    fresh.system(announce, name="announce")
    printed = drive(loop, ["/swap", "hello", "/quit"],
                    commands={"/swap": lambda engine, arg: fresh})
    assert "new world" in printed
    # The old loop's systems are gone with it, so `hello` means nothing now.
    assert "hello yourself" not in printed
    assert "  (nothing understood: hello)" in printed


def test_a_command_that_handles_itself_returns_none(loop):
    seen = []
    drive(loop, ["/note something", "/quit"],
          commands={"/note": lambda engine, arg: seen.append(arg)})
    assert seen == ["something"]


def test_end_of_input_ends_the_session_the_same_way_quit_does(loop):
    # Piped input (`< script.txt`) running out of lines must exit rather
    # than leave `engine.run()` blocked on a queue nothing feeds any more.
    assert drive(loop, []) is not None


class _Spy:
    """A channel that does nothing but remember what it was delivered --
    for watching a SECOND channel's-eye view of a broadcast without a
    second real terminal's own EOF racing to stop the engine first."""

    def __init__(self):
        self.name = None
        self.messages = []

    def start(self, engine):
        pass

    def deliver(self, message):
        self.messages.append(message)

    def close(self):
        pass


def test_a_broadcast_reply_reaches_every_attached_channel(loop):
    out = io.StringIO()
    engine = Engine(loop)
    spy = _Spy()
    term = repl.Terminal(stdin=io.StringIO("hello\n/quit\n"), stdout=out,
                         echo_prompt=False)
    engine.attach(spy)
    engine.attach(term)
    thread = threading.Thread(target=engine.run, daemon=True)
    thread.start()
    thread.join(2.0)
    assert not thread.is_alive()
    assert "hello yourself" in out.getvalue()
    assert any(m.get("reply", {}).get("text") == "hello yourself"
              for m in spy.messages)
