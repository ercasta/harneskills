"""What a delta promises: data describing a change, applied by `Loop`
alone -- and what a `Pending` resolves to once its own `Spawn` is real."""

import pytest

from ugm.delta import Attach, Destroy, Detach, Pending, Spawn, attach, destroy, detach, spawn
from ugm.world import Component, World


class Size(Component):
    def __init__(self, bytes):
        self.bytes = bytes


class Ref(Component):
    def __init__(self, other):
        self.other = other


@pytest.fixture
def world():
    return World()


def test_the_four_free_functions_build_the_matching_delta_type():
    assert isinstance(spawn(Size(1)), Spawn)
    assert isinstance(attach(object(), Size(1)), Attach)
    assert isinstance(detach(object(), Size), Detach)
    assert isinstance(destroy(object()), Destroy)


def test_a_spawn_s_own_entity_is_a_pending_until_applied():
    made = spawn(Size(4300))
    assert isinstance(made.entity, Pending)


def test_applying_a_spawn_resolves_its_pending_to_a_real_entity(world):
    made = spawn(Size(4300))
    resolved = {}
    made._apply(world, resolved)
    entity = resolved[made.entity]
    assert world.get(entity, Size) == Size(4300)


def test_a_pending_used_by_a_later_delta_in_the_same_batch_resolves(world):
    made = spawn(Size(1))
    deltas = [made, attach(made.entity, Ref("later"))]
    resolved = {}
    for d in deltas:
        d._apply(world, resolved)
    entity = resolved[made.entity]
    assert world.get(entity, Ref).other == "later"


def test_a_pending_nested_inside_a_component_field_resolves():
    class Holder(Component):
        def __init__(self, ref):
            self.ref = ref

    class Index(Component):
        def __init__(self, by_name):
            self.by_name = by_name

    world = World()
    made = spawn(Size(1))
    deltas = [made, spawn(Holder(made.entity)), spawn(Index({"a": made.entity, "b": (made.entity,)}))]
    resolved = {}
    for d in deltas:
        d._apply(world, resolved)
    target = resolved[made.entity]
    holder = world.each(Holder)[0][1]
    index = world.each(Index)[0][1]
    assert holder.ref == target
    assert index.by_name == {"a": target, "b": (target,)}


def test_a_pending_referenced_before_its_own_spawn_is_a_clear_error(world):
    made = spawn(Size(1))
    resolved = {}
    with pytest.raises(ValueError, match="not the entity of a Spawn"):
        attach(made.entity, Ref("too early"))._apply(world, resolved)


def test_attach_detach_destroy_resolve_a_pending_the_same_way(world):
    made = spawn(Size(1))
    resolved = {}
    made._apply(world, resolved)
    entity = resolved[made.entity]

    detach(made.entity, Size)._apply(world, resolved)
    assert world.get(entity, Size) is None

    attach(made.entity, Ref("back"))._apply(world, resolved)
    assert world.get(entity, Ref).other == "back"

    destroy(made.entity)._apply(world, resolved)
    assert not world.alive(entity)


def test_an_entity_already_in_the_world_needs_no_resolving(world):
    real = world.spawn(Size(1))
    resolved = {}
    attach(real, Ref("x"))._apply(world, resolved)
    assert world.get(real, Ref).other == "x"


def test_a_component_with_no_pending_fields_is_returned_unchanged(world):
    """No needless rebuild when there is nothing to resolve -- the same
    object a system built, attached as-is."""
    made = spawn(Size(1))
    resolved = {}
    made._apply(world, resolved)
    entity = resolved[made.entity]
    plain = Ref("nothing pending here")
    attach(entity, plain)._apply(world, resolved)
    assert world.get(entity, Ref) is plain
