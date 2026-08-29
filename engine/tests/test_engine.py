"""What the engine promises: one world, one thread that ever touches it,
and any number of channels attached to it -- see `ugm.engine`'s own
docstring for the contract a channel has to keep."""

import dataclasses
import threading
import time

import pytest

from ugm.delta import destroy, detach, spawn
from ugm.engine import BROADCAST, Engine
from ugm.loop import Loop
from ugm.world import Reply, Said


@dataclasses.dataclass(frozen=True)
class Ping:
    pass


class Fake:
    """The smallest thing that satisfies the channel contract: a name,
    and a place messages land. `post` is called by the TEST, standing in
    for whatever thread a real channel would read from."""

    def __init__(self, name=None):
        self.name = name
        self.messages = []
        self.started_with = None
        self.closed = False

    def start(self, engine):
        self.started_with = engine

    def deliver(self, message):
        self.messages.append(message)

    def close(self):
        self.closed = True


class Breaks(Fake):
    def deliver(self, message):
        raise RuntimeError("this channel is gone")


@pytest.fixture
def loop():
    return Loop()


@pytest.fixture
def engine(loop):
    return Engine(loop)


def run_briefly(engine, seconds=0.3):
    """`engine.run()` on its own thread, stopped after a short window --
    for a test that wants to `post` from the main thread while the engine
    thread is the one draining the queue, the same shape any real channel
    is in."""
    thread = threading.Thread(target=engine.run, daemon=True)
    thread.start()
    time.sleep(seconds)
    engine.stop()
    thread.join(2)
    assert not thread.is_alive()


# --- attaching ------------------------------------------------------------

def test_attach_names_a_channel_that_did_not_name_itself(engine):
    a, b = Fake(), Fake()
    engine.attach(a)
    engine.attach(b)
    assert a.name != b.name and a.name and b.name


def test_attach_leaves_a_channel_s_own_name_alone(engine):
    mine = Fake(name="dashboard")
    engine.attach(mine)
    assert mine.name == "dashboard"


def test_attach_calls_start_with_the_engine(engine):
    fake = Fake()
    engine.attach(fake)
    assert fake.started_with is engine


def test_user_is_reserved_for_broadcast_not_a_channel_name(engine):
    with pytest.raises(ValueError):
        engine.attach(Fake(name=BROADCAST))


def test_detach_closes_it_and_it_hears_nothing_more(engine):
    fake = Fake()
    engine.attach(fake)
    engine.detach(fake)
    assert fake.closed
    engine.to_all({"reply": {"channel": "user", "text": "hi"}})
    assert fake.messages == []


# --- routing ----------------------------------------------------------

def test_a_reply_to_user_reaches_everyone(engine):
    a, b = Fake(), Fake()
    engine.attach(a)
    engine.attach(b)
    engine.to(BROADCAST, {"reply": {"channel": "user", "text": "hi"}})
    assert a.messages and b.messages


def test_a_reply_to_one_channel_s_name_reaches_only_that_one(engine):
    a, b = Fake(name="alice"), Fake(name="bob")
    engine.attach(a)
    engine.attach(b)
    engine.to("alice", {"reply": {"channel": "alice", "text": "psst"}})
    assert a.messages and not b.messages


def test_a_channel_whose_deliver_raises_is_dropped_not_left_broken(engine):
    bad, good = Breaks(), Fake()
    engine.attach(bad)
    engine.attach(good)
    engine.to_all({"reply": {"channel": "user", "text": "hi"}})
    assert bad not in engine.channels
    assert good.messages, "the other channel still got it"


# --- the world, through post() -----------------------------------------

def test_say_spawns_said_under_the_poster_s_own_channel_name(engine):
    fake = Fake(name="alice")
    engine.attach(fake)
    engine.post(fake, "say", "hello")
    run_briefly(engine)
    assert engine.loop.world.the(Said) is None, "settled and destroyed"
    assert any("unheard" in m or "reply" in m for m in fake.messages)


def test_a_reply_addressed_to_user_is_seen_by_the_asker_too(loop):
    @loop.system
    def echo(w):
        deltas = []
        for entity, said in w.each(Said):
            deltas.append(destroy(entity))
            deltas.append(spawn(Reply("user", "echo: %s" % said.text)))
        return deltas

    engine = Engine(loop)
    fake = Fake()
    engine.attach(fake)
    engine.post(fake, "say", "hi")
    run_briefly(engine)
    assert any(m.get("reply", {}).get("text") == "echo: hi" for m in fake.messages)


def test_get_returns_the_world_only_to_the_asker(loop):
    a, b = Fake(), Fake()
    engine = Engine(loop)
    engine.attach(a)
    engine.attach(b)
    engine.post(a, "get", None)
    run_briefly(engine)
    assert any("world" in m for m in a.messages)
    assert not any("world" in m for m in b.messages)


def test_stop_posted_through_the_queue_does_not_strand_a_say_before_it(loop):
    # The race this guards: a channel that posts `say` and then `stop` in
    # quick succession must have the say acted on first, not have `stop`
    # race it to the front (see `Engine.post`'s own docstring).
    @loop.system
    def echo(w):
        deltas = []
        for entity, said in w.each(Said):
            deltas.append(destroy(entity))
            deltas.append(spawn(Reply("user", "got: %s" % said.text)))
        return deltas

    engine = Engine(loop)
    fake = Fake()
    engine.attach(fake)
    engine.post(fake, "say", "hello")
    engine.post(fake, "stop", None)
    thread = threading.Thread(target=engine.run, daemon=True)
    thread.start()
    thread.join(2)
    assert not thread.is_alive()
    assert any(m.get("reply", {}).get("text") == "got: hello" for m in fake.messages)


def test_a_command_is_run_on_the_engine_s_own_thread(loop):
    seen = {}

    def whoami(engine_, arg):
        seen["thread"] = threading.current_thread()
        return None

    engine = Engine(loop, commands={"/whoami": whoami})
    fake = Fake()
    engine.attach(fake)
    run_thread = threading.Thread(target=engine.run, daemon=True)
    run_thread.start()
    engine.post(fake, "command", "/whoami")
    time.sleep(0.2)
    engine.stop()
    run_thread.join(2)
    assert seen["thread"] is run_thread


def test_a_command_may_hand_back_a_fresh_loop(loop):
    fresh = Loop()

    def swap(engine_, arg):
        return fresh

    engine = Engine(loop, commands={"/swap": swap})
    fake = Fake()
    engine.attach(fake)
    engine.post(fake, "command", "/swap")
    run_briefly(engine)
    assert engine.loop is fresh


def test_show_and_systems_are_built_in_commands(loop):
    loop.system(lambda w: None, name="noop")
    engine = Engine(loop)
    fake = Fake()
    engine.attach(fake)
    engine.post(fake, "command", "/systems")
    run_briefly(engine)
    lines = [m["lines"] for m in fake.messages if "lines" in m]
    assert lines and "noop" in lines[0][0]


def test_an_unknown_command_says_so_to_the_one_who_typed_it(engine):
    fake = Fake()
    engine.attach(fake)
    engine.post(fake, "command", "/nope")
    run_briefly(engine)
    assert any(m.get("error", {}).get("text") == "no such command: /nope"
              for m in fake.messages)


# --- settling -----------------------------------------------------------

def test_settle_reports_a_runaway_pair_and_their_names(loop):
    @loop.system
    def ping(w):
        return [detach(e, Ping) for e, _ in w.each(Ping)]

    loop.world.spawn(Ping())

    @loop.system
    def pong(w):
        return [] if w.each(Ping) else [spawn(Ping())]

    engine = Engine(loop)
    fake = Fake()
    engine.attach(fake)
    engine.settle()
    errors = [m["error"]["text"] for m in fake.messages if "error" in m]
    assert any("still firing" in e and "ping" in e and "pong" in e for e in errors)


def test_on_settle_is_called_once_the_world_has_finished_saying_things(loop):
    calls = []
    engine = Engine(loop, on_settle=lambda lp: calls.append(lp))
    engine.settle()
    assert calls == [loop]
