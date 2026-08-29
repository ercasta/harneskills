"""What the state file promises: the same world, ids and all, next time.

⚠ The `__ugm_save__`/`module:factory(arg)` mechanism this file used to test
(a class minted by `ugm.facts.relation()` naming its own factory so `save`
could find it) is gone along with `facts.py`'s quarantine -- see
`docs/overview.md`. `_kind()` only ever resolves `module:ClassName` now.
"""

import dataclasses
import json
from typing import Any

import pytest

from ugm import save
from ugm.world import World


@dataclasses.dataclass(frozen=True)
class Folder:
    path: str


@dataclasses.dataclass(frozen=True)
class Contents:
    by_name: dict = dataclasses.field(default_factory=dict)


@dataclasses.dataclass(frozen=True)
class Entry:
    folder: int
    name: str


@dataclasses.dataclass(frozen=True)
class Stale:
    pass


@dataclasses.dataclass(frozen=True)
class Odd:
    value: Any


def peopled():
    """A world shaped like the fs domain's: a folder holding entries, each
    pointing back at it, and an index keyed by name."""
    w = World()
    folder = w.spawn(Folder("/tmp/notes"))
    by_name = {}
    for name in ("a.txt", "b.bin"):
        by_name[name] = w.spawn(Entry(folder, name)).id
    w.attach(folder, Contents(by_name))
    w.attach(w.entity(by_name["a.txt"]), Stale())
    return w, folder, by_name


def roundtrip(w):
    fresh = World()
    records = [json.loads(json.dumps(r)) for r in save.dump(w)]
    assert save.load(fresh, records) == []
    return fresh


# --- the round trip ---------------------------------------------------

def test_everything_comes_back_with_the_same_ids():
    w, folder, by_name = peopled()
    back = roundtrip(w)
    assert [e.id for e in back.entities()] == [e.id for e in w.entities()]
    assert back.get(folder, Folder) == Folder("/tmp/notes")
    assert (back.has(back.entity(by_name["a.txt"]), Stale)
           and not back.has(back.entity(by_name["b.bin"]), Stale))


def test_a_reference_still_points_at_the_same_entity():
    w, folder, by_name = peopled()
    back = roundtrip(w)
    # The relationship, and the hand-kept index that holds entities as
    # values, are the two ways this can go wrong. Both are the point --
    # and both are now plain ints, not handles, so there is no `.world`
    # left to check: the whole reason a stored reference cannot silently
    # point into the wrong world is that it never held one.
    assert back.get(back.entity(by_name["b.bin"]), Entry).folder == folder.id
    assert back.get(folder, Contents).by_name == by_name


def test_the_counter_resumes_above_every_restored_id():
    w, _, _ = peopled()
    back = roundtrip(w)
    # A world that started counting at 1 again would hand a new entity an
    # id a component is still pointing at.
    assert back.spawn().id == 4


def test_a_destroyed_highest_entity_does_not_free_its_id():
    w, _, by_name = peopled()
    w.destroy(w.entity(by_name["b.bin"]))
    assert roundtrip(w).spawn().id == 4


def test_a_component_is_rebuilt_without_calling_its_init():
    # A dataclass's constructor takes its fields in declaration order, but
    # rebuilding never calls it -- the fields are what comes back.
    w, _, by_name = peopled()
    entry = roundtrip(w).get(w.entity(by_name["a.txt"]), Entry)
    assert (entry.name, entry.folder) == ("a.txt", 1)


@pytest.mark.parametrize("value", [
    None, True, 17, 1.5, "text", [], [1, "two", None], {"k": [1, 2]},
    (1, 2), {"nested": {"deep": (1, [2, 3])}}])
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
#
# ⚠ A set, an arbitrary object, or a dict with a non-string key are
# already refused by `World.attach` itself now -- see `test_world.py` --
# so `save.dump` never even sees them. The one thing left that is
# genuinely THIS format's own business is `$tuple`, its own reserved
# marker for a value `World` already accepted.


def test_a_reserved_KEY_is_named_not_mangled():
    w = World()
    w.spawn(Odd({"$tuple": 3}))
    with pytest.raises(save.SaveError) as raised:
        save.dump(w)
    assert "may not start with '$'" in str(raised.value)
    assert "Odd.value" in str(raised.value)


def test_loading_wants_an_empty_world():
    w, _, _ = peopled()
    with pytest.raises(ValueError):
        save.load(w, save.dump(w))


# --- surviving the file itself ----------------------------------------

def test_a_component_whose_class_is_gone_is_skipped_and_named():
    w, folder, _ = peopled()
    records = save.dump(w)
    folder_record = next(r for r in records
                         if r.get("entity") == folder.id
                         and r.get("type", "").endswith(":Folder"))
    folder_record["type"] = "ugm.world:NoSuchThing"
    back = World()
    problems = save.load(back, records)
    assert len(problems) == 1 and "NoSuchThing" in problems[0]
    # The entity keeps everything else it carried.
    assert back.get(folder, Contents) is not None
    assert back.get(folder, Folder) is None


def test_a_state_file_from_another_version_is_not_guessed_at():
    records = save.dump(World())
    records[0]["version"] = 99
    back = World()
    assert "version" in save.load(back, records)[0]
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
    header = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
    assert header["next"] == 3
    assert not (tmp_path / "deep" / "down" / "world.json.tmp").exists()


def test_written_and_read_back_is_the_same_world(tmp_path):
    w, folder, by_name = peopled()
    path = str(tmp_path / "world.json")
    save.write(w, path)
    back = World()
    assert save.read(back, path) == []
    assert back.get(back.entity(by_name["a.txt"]), Entry).folder == folder.id


def test_the_file_is_the_same_bytes_on_every_platform(tmp_path):
    # Text mode would turn every \n into \r\n on Windows, and a state file
    # whose bytes depend on which machine wrote it is one you cannot
    # compare. Only bites on Windows; the guard belongs here anyway.
    w, _, _ = peopled()
    path = tmp_path / "world.json"
    save.write(w, str(path))
    assert b"\r\n" not in path.read_bytes()
    assert path.read_bytes().endswith(b"\n")


def test_one_line_per_record_is_what_makes_it_JSONL():
    w, folder, by_name = peopled()
    records = save.dump(w)
    # Header, plus one line per component instance -- Folder, Contents,
    # two Entry, one Stale -- nothing nested inside another.
    assert records[0] == {"version": save.VERSION, "next": w._next}
    assert len(records) == 1 + 5


def test_a_type_that_names_a_NON_CLASS_is_a_problem_not_a_crash():
    """The promise is that a bad state file costs you the component, not
    the session."""
    world = World()
    problems = save.load(world, [
        {"version": save.VERSION, "next": 2},
        {"entity": 1, "type": "ugm.save:VERSION", "fields": {}},
    ])
    assert len(problems) == 1 and "not a class" in problems[0]
    assert len(world) == 1, "the entity survives, having lost that component"
