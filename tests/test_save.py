"""What the state file promises: the same world, ids and all, next time."""

import json

import pytest

from harneskills import save
from harneskills.world import Component, World


class Folder(Component):
    def __init__(self, path):
        self.path = path


class Contents(Component):
    def __init__(self):
        self.by_name = {}


class Entry(Component):
    def __init__(self, folder, name):
        self.folder = folder
        self.name = name


class Stale(Component):
    pass


class Odd(Component):
    def __init__(self, value):
        self.value = value


def peopled():
    """A world shaped like the fs domain's: a folder holding entries, each
    pointing back at it, and an index keyed by name."""
    w = World()
    folder = w.spawn(Folder("/tmp/notes"), Contents())
    index = w.get(folder, Contents).by_name
    for name in ("a.txt", "b.bin"):
        index[name] = w.spawn(Entry(folder, name))
    w.attach(index["a.txt"], Stale())
    return w, folder, index


def roundtrip(w):
    fresh = World()
    assert save.load(fresh, json.loads(json.dumps(save.dump(w)))) == []
    return fresh


# --- the round trip ---------------------------------------------------

def test_everything_comes_back_with_the_same_ids(monkeypatch):
    w, folder, index = peopled()
    back = roundtrip(w)
    assert [e.id for e in back.entities()] == [e.id for e in w.entities()]
    assert back.get(folder, Folder) == Folder("/tmp/notes")
    assert back.has(index["a.txt"], Stale) and not back.has(index["b.bin"], Stale)


def test_a_reference_still_points_at_the_same_entity():
    w, folder, index = peopled()
    back = roundtrip(w)
    # The relationship, and the hand-kept index that holds entities as
    # values, are the two ways this can go wrong. Both are the point.
    #
    # By id, not by handle: a handle carries which world it belongs to,
    # and one from the old world is deliberately not equal to one from
    # the new -- that is what stops two worlds' entities colliding.
    assert back.get(index["b.bin"], Entry).folder.id == folder.id
    assert back.get(index["b.bin"], Entry).folder.world is back
    assert ({n: e.id for n, e in back.get(folder, Contents).by_name.items()}
            == {n: e.id for n, e in index.items()})


def test_the_counter_resumes_above_every_restored_id():
    w, _, _ = peopled()
    back = roundtrip(w)
    # A world that started counting at 1 again would hand a new entity an
    # id a component is still pointing at.
    assert back.spawn().id == 4


def test_a_destroyed_highest_entity_does_not_free_its_id():
    w, _, index = peopled()
    w.destroy(index["b.bin"])
    assert roundtrip(w).spawn().id == 4


def test_a_component_is_rebuilt_without_calling_its_init():
    # `Entry(folder, name)` takes positional arguments that are not its
    # field names, and nothing could call it; the fields are what comes
    # back.
    w, _, index = peopled()
    entry = roundtrip(w).get(index["a.txt"], Entry)
    assert (entry.name, entry.folder.id) == ("a.txt", 1)


@pytest.mark.parametrize("value", [
    None, True, 17, 1.5, "text", [], [1, "two", None], {"k": [1, 2]},
    (1, 2), {"nested": {"deep": (1, [2, {"$notallowed": 0}.get("x", 3)])}}])
def test_the_field_types_a_component_may_hold(value):
    w = World()
    entity = w.spawn(Odd(value))
    assert roundtrip(w).get(entity, Odd).value == value


def test_a_tuple_comes_back_a_tuple():
    w = World()
    entity = w.spawn(Odd((1, 2)))
    assert isinstance(roundtrip(w).get(entity, Odd).value, tuple)


def test_an_empty_world_round_trips_to_an_empty_world():
    assert len(roundtrip(World())) == 0


# --- what it refuses to pretend ---------------------------------------

@pytest.mark.parametrize("value, complaint", [
    ({1, 2}, "cannot save a set"),
    (object(), "cannot save an object"),
    ({1: "int key"}, "must be a string"),
    ({"$entity": 3}, "may not start with '$'"),
])
def test_a_field_it_cannot_write_is_named_not_mangled(value, complaint):
    w = World()
    w.spawn(Odd(value))
    with pytest.raises(save.SaveError) as raised:
        save.dump(w)
    assert complaint.replace("an object", "a object") in str(
        raised.value).replace("an object", "a object")
    assert "Odd.value" in str(raised.value)


def test_loading_wants_an_empty_world():
    w, _, _ = peopled()
    with pytest.raises(ValueError):
        save.load(w, save.dump(w))


# --- surviving the file itself ----------------------------------------

def test_a_component_whose_class_is_gone_is_skipped_and_named():
    w, folder, _ = peopled()
    data = save.dump(w)
    data["entities"][0]["components"][0]["type"] = "harneskills.world:NoSuchThing"
    back = World()
    problems = save.load(back, data)
    assert len(problems) == 1 and "NoSuchThing" in problems[0]
    # The entity keeps everything else it carried.
    assert back.get(folder, Contents) is not None
    assert back.get(folder, Folder) is None


def test_a_state_file_from_another_version_is_not_guessed_at():
    data = save.dump(World())
    data["version"] = 99
    back = World()
    assert "version" in save.load(back, data)[0]
    assert len(back) == 0


def test_no_file_is_not_a_problem_it_is_a_first_run(tmp_path):
    w = World()
    assert save.read(w, str(tmp_path / "never-written.json")) == []
    assert len(w) == 0


def test_a_corrupt_file_costs_the_world_not_the_session(tmp_path):
    path = tmp_path / "world.json"
    path.write_text("{not json at all", encoding="utf-8")
    w = World()
    problems = save.read(w, str(path))
    assert len(problems) == 1 and str(path) in problems[0]
    assert len(w) == 0
    assert path.exists(), "the file is still there to look at"


def test_writing_makes_the_directory_and_replaces_atomically(tmp_path):
    w, _, _ = peopled()
    path = tmp_path / "deep" / "down" / "world.json"
    save.write(w, str(path))
    save.write(w, str(path))                      # again, over the top
    assert json.loads(path.read_text(encoding="utf-8"))["next"] == 3
    assert not (tmp_path / "deep" / "down" / "world.json.tmp").exists()


def test_written_and_read_back_is_the_same_world(tmp_path):
    w, folder, index = peopled()
    path = str(tmp_path / "world.json")
    save.write(w, path)
    back = World()
    assert save.read(back, path) == []
    assert back.get(index["a.txt"], Entry).folder.id == folder.id
