"""What the loop promises: every rule, in order, until nothing changes
-- called once a tick, writing to the world directly, with nothing in
between the write and the next rule seeing it."""

import dataclasses

import pytest

from ugm.loop import Loop


@dataclasses.dataclass(frozen=True)
class Step:
    n: object


@dataclasses.dataclass(frozen=True)
class Ping:
    pass


@dataclasses.dataclass(frozen=True)
class Pong:
    pass


@dataclasses.dataclass(frozen=True)
class Seen:
    pass


@pytest.fixture
def loop():
    return Loop()


def test_rules_run_in_registration_order_every_tick(loop):
    order = []
    loop.rule(lambda w: order.append("first"), name="first")
    loop.rule(lambda w: order.append("second"), name="second")
    loop.tick()
    loop.tick()
    assert order == ["first", "second", "first", "second"]


def test_a_rule_is_named_for_its_module_and_function(loop):
    @loop.rule
    def flag_big(w):
        pass

    @loop.rule(name="say hello")
    def _(w):
        pass

    assert [name for name, _ in loop.rules] == ["test_loop.flag_big", "say hello"]


def test_a_rule_fires_by_changing_something(loop):
    @loop.rule
    def marks(w):
        for e, _ in w.each(Step):
            w.attach(e, Seen())          # news once, and then never again

    loop.world.spawn(Step(0))
    assert loop.tick() == ["test_loop.marks"]
    assert loop.tick() == []


def test_a_rule_that_writes_nothing_does_not_fire(loop):
    @loop.rule
    def idle(w):
        for entity, step in w.each(Step):
            pass   # reads, writes nothing

    loop.world.spawn(Step(0))
    assert loop.tick() == []


def test_run_settles_when_a_whole_pass_changes_nothing(loop):
    @loop.rule
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


def test_a_spawn_is_a_real_entity_usable_the_same_call(loop):
    """`w.spawn(...)` hands back the real entity, not a placeholder --
    usable immediately, in the rest of the SAME rule, for a further
    `w.attach`/`w.get`/anything else."""
    @loop.rule
    def make_and_mark(w):
        made = w.spawn(Step(1))
        w.attach(made, Seen())

    loop.tick()
    entity, step = loop.world.each(Step)[0]
    assert step.n == 1
    assert loop.world.has(entity, Seen)


def test_a_freshly_spawned_entity_s_id_is_usable_in_another_component_field(loop):
    @dataclasses.dataclass(frozen=True)
    class Holder:
        ref: object

    @dataclasses.dataclass(frozen=True)
    class Index:
        by_name: dict

    @loop.rule
    def make(w):
        made = w.spawn(Step(1))
        w.spawn(Holder(made))
        w.spawn(Index({"a": made}))

    loop.tick()
    w = loop.world
    target = w.each(Step)[0][0]
    holder = w.each(Holder)[0][1]
    index = w.each(Index)[0][1]
    # A component field never holds a live handle -- see ugm.world's own
    # note -- so the entity is lowered to its plain id on the way in.
    assert holder.ref == target.id
    assert index.by_name == {"a": target.id}


def test_two_rules_feeding_each_other_stop_at_the_budget_and_are_named(loop):
    @loop.rule
    def ping(w):
        for entity, _ in w.each(Pong):
            w.destroy(entity)
            w.spawn(Ping())

    @loop.rule
    def pong(w):
        for entity, _ in w.each(Ping):
            w.destroy(entity)
            w.spawn(Pong())

    loop.world.spawn(Ping())
    settled = loop.run(budget=20)
    assert settled.ticks == 20
    assert sorted(set(settled.hot)) == ["test_loop.ping", "test_loop.pong"]


def test_a_rule_that_raises_is_recorded_and_the_others_still_run(loop):
    @loop.rule
    def explodes(w):
        raise ValueError("no")

    @loop.rule
    def carries_on(w):
        # `attach`, not `spawn`: spawning is never idempotent, so a rule
        # that spawned every tick would keep the world awake by itself and
        # tell us nothing about the one that raises.
        for e, _ in w.each(Step):
            w.attach(e, Seen())

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
        lp.rule(lambda w: None, name="noop")

    loop.install(domain, greeting="hello")
    assert loop.world.the(Step).n == "hello"
    assert [name for name, _ in loop.rules] == ["noop"]


def test_a_rule_with_watches_is_not_even_called_while_dormant(loop):
    calls = []

    @loop.rule(watches=(Step,))
    def counts_calls(w):
        calls.append(None)

    loop.tick()
    loop.tick()
    assert calls == [], "Step has never existed -- the body never ran"

    loop.world.spawn(Step(0))
    loop.tick()
    assert len(calls) == 1, "a Step exists now -- it runs"
    loop.tick()
    assert len(calls) == 2, "populated now, so it runs every tick again"


def test_watches_accepts_a_single_type_or_several(loop):
    seen = []
    loop.rule(lambda w: seen.append("one"), name="one", watches=Step)
    loop.rule(lambda w: seen.append("either"), name="either",
               watches=(Step, Ping))

    loop.tick()
    assert seen == []

    loop.world.spawn(Ping())
    loop.tick()
    assert seen == ["either"], "Ping alone wakes the OR-watcher, not the Step one"


def test_a_rule_with_no_watches_runs_every_tick_regardless(loop):
    seen = []
    loop.rule(lambda w: seen.append(None), name="always")
    loop.tick()
    loop.tick()
    assert len(seen) == 2, "the default: called whether or not anything exists"


# --- priority: the one deliberate override of registration order --------


def test_higher_priority_runs_first_regardless_of_registration_order(loop):
    order = []
    loop.rule(lambda w: order.append("low"), name="low", priority=1)
    loop.rule(lambda w: order.append("high"), name="high", priority=10)
    loop.tick()
    assert order == ["high", "low"]


def test_equal_priority_including_the_default_keeps_registration_order(loop):
    order = []
    loop.rule(lambda w: order.append("first"), name="first")
    loop.rule(lambda w: order.append("second"), name="second", priority=0)
    loop.rule(lambda w: order.append("third"), name="third", priority=5)
    loop.tick()
    # "third" (priority 5) leads; "first" and "second" are both priority 0
    # and keep the order they were registered in relative to each other.
    assert order == ["third", "first", "second"]


def test_priority_does_not_reorder_the_registry_itself(loop):
    """`self.rules` is what `/rules` prints and what other tests read
    -- it stays in registration order. Priority is `tick()`'s own
    execution order, not a second registry."""
    loop.rule(lambda w: None, name="low", priority=1)
    loop.rule(lambda w: None, name="high", priority=10)
    assert [name for name, _ in loop.rules] == ["low", "high"]


def test_a_late_registered_high_priority_rule_still_runs_first(loop):
    """Priority is read fresh each tick, not fixed at whatever position a
    rule happened to be appended at -- a rule two domains install in
    either order still runs in the order THEY declared, not the order
    `install()` happened to run in."""
    order = []
    loop.tick()                                    # nothing registered yet
    loop.rule(lambda w: order.append("first-installed"), name="a", priority=0)
    loop.rule(lambda w: order.append("installed-later-but-important"),
               name="b", priority=100)
    loop.tick()
    assert order == ["installed-later-but-important", "first-installed"]


def test_a_rule_watching_SEVERAL_kinds_still_fires_ONCE_per_tick(loop):
    calls = []
    loop.rule(lambda w: calls.append(None), name="watcher",
               watches=(Step, Ping, Pong))
    loop.world.spawn(Step(0))
    loop.world.spawn(Ping())
    loop.world.spawn(Pong())               # all three watched kinds exist
    loop.tick()
    assert len(calls) == 1, "one entry in self.rules, called once, full stop"


def test_after_tick_runs_between_ticks_not_at_the_end(loop):
    seen = []

    @loop.rule
    def countdown(w):
        for entity, step in w.each(Step):
            w.destroy(entity)
            if step.n > 0:
                w.spawn(Step(step.n - 1))

    loop.world.spawn(Step(3))
    loop.run(after_tick=lambda: seen.append(
        [s.n for _, s in loop.world.each(Step)]))
    assert seen == [[2], [1], [0], []]
