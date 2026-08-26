"""What the loop promises: every system, in order, until nothing changes."""

import pytest

from harneskills.loop import Loop
from harneskills.world import Component


class Step(Component):
    def __init__(self, n):
        self.n = n


class Ping(Component):
    pass


class Pong(Component):
    pass


class Seen(Component):
    pass


@pytest.fixture
def loop():
    return Loop()


def test_systems_run_in_registration_order_every_tick(loop):
    order = []
    loop.system(lambda w: order.append("first"), name="first")
    loop.system(lambda w: order.append("second"), name="second")
    loop.tick()
    loop.tick()
    assert order == ["first", "second", "first", "second"]


def test_a_system_is_named_for_its_module_and_function(loop):
    @loop.system
    def flag_big(w):
        pass

    @loop.system(name="say hello")
    def _(w):
        pass

    assert [name for name, _ in loop.systems] == ["test_loop.flag_big", "say hello"]


def test_a_system_fires_by_changing_something(loop):
    @loop.system
    def marks(w):
        for entity, _ in w.each(Step):
            w.attach(entity, Seen())      # news once, and then never again

    loop.world.spawn(Step(0))
    assert loop.tick() == ["test_loop.marks"]
    assert loop.tick() == []


def test_run_settles_when_a_whole_pass_changes_nothing(loop):
    @loop.system
    def chain(w):
        for entity, step in w.each(Step):
            w.destroy(entity)
            if step.n < 3:
                w.spawn(Step(step.n + 1))

    loop.world.spawn(Step(0))
    settled = loop.run()
    assert settled.hot == []
    assert settled.ticks == 5          # four steps, then the quiet pass
    assert len(loop.world) == 0


def test_two_systems_feeding_each_other_stop_at_the_budget_and_are_named(loop):
    @loop.system
    def ping(w):
        for entity, _ in w.each(Pong):
            w.detach(entity, Pong)
            w.attach(entity, Ping())

    @loop.system
    def pong(w):
        for entity, _ in w.each(Ping):
            w.detach(entity, Ping)
            w.attach(entity, Pong())

    loop.world.spawn(Ping())
    settled = loop.run(budget=20)
    assert settled.ticks == 20
    assert sorted(set(settled.hot)) == ["test_loop.ping", "test_loop.pong"]


def test_a_system_that_raises_is_recorded_and_the_others_still_run(loop):
    @loop.system
    def explodes(w):
        raise ValueError("no")

    @loop.system
    def carries_on(w):
        # `attach`, not `spawn`: spawning is never idempotent, so a system
        # that spawned every tick would keep the world awake by itself and
        # tell us nothing about the one that raises.
        for entity, _ in w.each(Step):
            w.attach(entity, Seen())

    loop.world.spawn(Step(0))
    settled = loop.run()
    assert loop.world.each(Seen)
    assert [name for name, _ in loop.errors] == ["test_loop.explodes"]
    # It raises every tick, but raising changes nothing, so the world
    # still settles rather than burning the whole budget.
    assert settled.hot == []


def test_install_hands_the_loop_to_a_domain(loop):
    def domain(lp, greeting="hi"):
        lp.world.spawn(Step(greeting))
        lp.system(lambda w: None, name="noop")

    loop.install(domain, greeting="hello")
    assert loop.world.the(Step).n == "hello"
    assert [name for name, _ in loop.systems] == ["noop"]


def test_after_tick_runs_between_ticks_not_at_the_end(loop):
    seen = []

    @loop.system
    def countdown(w):
        for entity, step in w.each(Step):
            w.destroy(entity)
            if step.n > 0:
                w.spawn(Step(step.n - 1))

    loop.world.spawn(Step(3))
    loop.run(after_tick=lambda: seen.append(
        [s.n for _, s in loop.world.each(Step)]))
    assert seen == [[2], [1], [0], []]
