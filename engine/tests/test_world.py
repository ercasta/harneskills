"""What the world promises: entities are identity, components are data,
and a query is the intersection of the two."""

import dataclasses

import pytest

from ugm.world import Entity, Reply, Said, World


@dataclasses.dataclass(frozen=True)
class Named:
    text: object


@dataclasses.dataclass(frozen=True)
class Size:
    bytes: int


@dataclasses.dataclass(frozen=True)
class Stale:
    """A tag: no fields, so every instance is every other."""


@dataclasses.dataclass(frozen=True)
class Big:
    pass


@pytest.fixture
def w():
    return World()


# --- entities ---------------------------------------------------------

def test_spawning_gives_an_identity_in_order(w):
    first, second = w.spawn(), w.spawn()
    assert (first.id, second.id) == (1, 2)
    assert w.entities() == [first, second]
    assert len(w) == 2


def test_a_handle_is_the_entity_not_a_copy_of_it(w):
    entity = w.spawn(Named("a"))
    (again, _), = w.each(Named)
    assert again == entity and hash(again) == hash(entity)
    assert {entity: "kept"}[again] == "kept"


def test_the_same_id_in_another_world_is_another_entity(w):
    other = World()
    assert w.spawn() != other.spawn()


def test_destroying_takes_everything_on_it(w):
    entity = w.spawn(Named("a"), Size(10))
    assert w.destroy(entity) is True
    assert w.destroy(entity) is False
    assert w.each(Named) == [] and w.get(entity, Size) is None
    assert not w.alive(entity) and entity not in w


# --- components -------------------------------------------------------

def test_a_component_is_a_value(w):
    assert Size(17) == Size(17)
    assert Size(17) != Size(18)
    assert Size(17) != Named("17")
    assert Stale() == Stale()          # a tag is one set, not many values
    assert Stale() != Big()


def test_attach_APPENDS_so_an_entity_may_carry_SEVERAL_of_one_type(w):
    entity = w.spawn(Size(10))
    w.attach(entity, Size(4300))
    assert w.get_all(entity, Size) == [Size(10), Size(4300)]
    with pytest.raises(ValueError):
        w.get(entity, Size)            # refuses to guess between two


def test_replace_CLEARS_every_existing_one_of_that_type_first(w):
    entity = w.spawn(Size(10))
    w.attach(entity, Size(20))          # two, now
    w.replace(entity, Size(4300))
    assert w.get(entity, Size) == Size(4300)
    assert len(w.components(entity)) == 1


def test_replace_with_an_equal_value_is_not_a_change(w):
    entity = w.spawn(Size(17))
    before = w.revision
    w.replace(entity, Size(17))
    assert w.revision == before, "already exactly this -- settling depends on it"
    w.replace(entity, Size(18))
    assert w.revision == before + 1


def test_remove_takes_ONE_value_leaving_the_rest_of_that_type_standing(w):
    entity = w.spawn(Size(10))
    w.attach(entity, Size(20))
    assert w.remove(entity, Size(10)) is True
    assert w.remove(entity, Size(10)) is False, "already gone"
    assert w.get_all(entity, Size) == [Size(20)]


def test_attaching_an_equal_component_is_not_a_change(w):
    # What lets a rule recompute the same answer every tick without
    # keeping the world awake forever.
    entity = w.spawn(Size(17))
    before = w.revision
    w.attach(entity, Size(17))
    assert w.revision == before
    w.attach(entity, Size(18))
    assert w.revision == before + 1


def test_every_other_write_moves_the_revision(w):
    before = w.revision
    entity = w.spawn()                       # 1
    w.attach(entity, Stale())                # 2
    w.detach(entity, Stale)                  # 3
    w.detach(entity, Stale)                  # not there: no change
    w.changed(entity)                        # 4, by hand
    w.destroy(entity)                        # 5
    assert w.revision == before + 5


def test_attaching_to_something_that_is_not_here_is_refused(w):
    entity = w.spawn()
    w.destroy(entity)
    with pytest.raises(ValueError):
        w.attach(entity, Stale())


def test_has_and_get_read_one_entity(w):
    entity = w.spawn(Named("a"), Stale())
    assert w.has(entity, Named, Stale) and not w.has(entity, Size)
    assert w.get(entity, Named).text == "a"
    assert w.get(entity, Size) is None


def test_the_entity_handle_is_sugar_for_the_world_s_own_methods(w):
    entity = w.spawn(Named("a"))
    entity.attach(Stale())
    assert entity.has(Stale) and entity.get(Named).text == "a"
    entity.detach(Stale)
    assert not entity.has(Stale)
    assert entity.alive and entity.destroy() and not entity.alive


# --- entity references are plain ints, never live handles --------------

def test_a_live_entity_in_a_field_is_LOWERED_to_its_plain_id(w):
    folder = w.spawn(Named("/tmp"))
    entry = w.spawn()
    w.attach(entry, Size(folder.id))    # already an id -- unaffected
    assert w.get(entry, Size).bytes == folder.id

    @dataclasses.dataclass(frozen=True)
    class Entry:
        folder: object

    e2 = w.spawn(Entry(folder))          # a live handle, the ergonomic way
    assert w.get(e2, Entry).folder == folder.id
    assert isinstance(w.get(e2, Entry).folder, int)


def test_a_non_primitive_field_is_refused_naming_the_field(w):
    @dataclasses.dataclass(frozen=True)
    class Holds:
        thing: object

    with pytest.raises(TypeError, match="Holds.thing"):
        w.spawn(Holds(object()))
    with pytest.raises(TypeError, match="Holds.thing"):
        w.spawn(Holds({1, 2}))          # a set: not JSON-shaped either


def test_a_dict_field_s_key_must_be_a_string(w):
    @dataclasses.dataclass(frozen=True)
    class Holds:
        thing: object

    with pytest.raises(TypeError, match="must be a string"):
        w.spawn(Holds({1: "int key"}))


def test_entity_TURNS_a_raw_id_BACK_into_a_handle(w):
    made = w.spawn(Named("a"))
    handle = w.entity(made.id)
    assert handle == made and handle.get(Named).text == "a"


# --- queries ----------------------------------------------------------

def test_each_is_the_intersection_and_hands_back_what_was_asked_for(w):
    small = w.spawn(Named("small.txt"), Size(10))
    big = w.spawn(Named("huge.bin"), Size(5000), Big())
    w.spawn(Size(1))                       # no Named: not a match
    assert [(e, n.text, s.bytes) for e, n, s in w.each(Named, Size)] == [
        (small, "small.txt", 10), (big, "huge.bin", 5000)]
    assert [e for e, _ in w.each(Big)] == [big]


def test_each_yields_ONE_ROW_PER_COMBINATION_for_a_multi_valued_kind(w):
    entity = w.spawn(Named("a"))
    w.attach(entity, Size(1), Size(2))
    assert sorted((s.bytes,) for _, _, s in w.each(Named, Size)) == [(1,), (2,)]


def test_without_excludes(w):
    plain = w.spawn(Named("a"))
    w.spawn(Named("b"), Stale())
    assert [e for e, _ in w.each(Named, without=Stale)] == [plain]
    assert [e for e, _ in w.each(Named, without=(Stale, Big))] == [plain]


def test_matches_come_back_oldest_first_whatever_was_asked_for(w):
    first = w.spawn(Named("a"))
    second = w.spawn(Named("b"))
    w.attach(first, Size(1))               # the rarer component, added late
    w.attach(second, Size(2))
    assert [e for e, _, _ in w.each(Size, Named)] == [first, second]


def test_each_is_a_snapshot_so_a_rule_may_write_while_it_walks(w):
    for name in "ab":
        w.spawn(Named(name))
    for entity, named in w.each(Named):
        w.spawn(Named(named.text.upper()))
        w.destroy(entity)
    assert sorted(n.text for _, n in w.each(Named)) == ["A", "B"]


def test_each_needs_something_to_ask_about(w):
    with pytest.raises(TypeError):
        w.each()


def test_first_and_the_are_for_one_of_a_kind(w):
    assert w.first(Named) is None and w.the(Named) is None
    entity = w.spawn(Named("only"))
    w.spawn(Named("later"))
    assert w.first(Named)[0] == entity
    assert w.the(Named).text == "only"


def test_all_is_every_instance_anywhere_tagged_with_its_entity(w):
    a = w.spawn(Size(1))
    b = w.spawn(Size(2))
    w.attach(b, Size(3))
    assert w.all(Size) == [(a, Size(1)), (b, Size(2)), (b, Size(3))]


def test_get_all_is_every_instance_on_one_entity(w):
    entity = w.spawn(Size(1))
    assert w.get_all(entity, Size) == [Size(1)]
    w.attach(entity, Size(2))
    assert w.get_all(entity, Size) == [Size(1), Size(2)]
    assert w.get_all(w.spawn(), Size) == []


def test_components_and_show_are_for_a_person(w):
    folder = w.spawn(Named("/tmp"))
    entity = w.spawn(Named("a.txt"), Size(17))
    assert repr(w.components(entity)) == "[Named(text='a.txt'), Size(bytes=17)]"
    assert w.show(entity).split() == ["#2", "Named(text='a.txt')", "Size(bytes=17)"]
    # A component holding a live (unattached) entity still names it rather
    # than printing it whole -- Entity's own __repr__ does that.
    assert repr(Named(folder)) == "Named(text=#1)"


# --- what the harness itself puts in a world --------------------------

def test_said_and_reply_are_ordinary_components(w):
    w.spawn(Said("user", "show file"))
    w.spawn(Reply("user", "5 item(s)"))
    assert w.the(Said).text == "show file"
    assert w.the(Reply).channel == "user"


def test_vocabulary_is_only_ever_added_to(w):
    w.learn("show", "file")
    w.learn("big")
    assert w.vocabulary == {"show", "file", "big"}
