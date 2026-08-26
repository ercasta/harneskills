"""The filesystem domain, end to end: words in, facts and real files out.

The old harness's own README admitted its test suite never reached the
example, and two bugs sat in it unnoticed as a result. These drive the
whole chain -- a typed line, the rules, the tools, the disk -- through the
same `Loop` the REPL uses.
"""

import os
import time

import pytest

from harneskills.examples import fs
from harneskills.examples.model import (Big, Contents, Entry, Focus, Folder,
                                        NeedsApproval, RenameWish, Session,
                                        Size, Stale)
from harneskills.loop import Loop
from harneskills.world import Reply, Said

DAY = 86400


@pytest.fixture
def folder(tmp_path):
    """A folder with one old small file, one fresh big one, and a
    subfolder. `now` is pinned, so every age here is exact."""
    (tmp_path / "alpha.txt").write_text("hello", encoding="utf-8")
    (tmp_path / "huge.bin").write_bytes(b"x" * 5000)
    (tmp_path / "sub").mkdir()
    old = time.time() - 30 * DAY
    os.utime(tmp_path / "alpha.txt", (old, old))
    return str(tmp_path)


def session(folder, answers=()):
    """A loop with the fs domain installed, launched "in" `folder`, with a
    fixed clock and a scripted answer for every approval prompt."""
    said = list(answers)
    loop = Loop()
    fs.install(loop, ask=lambda prompt: said.pop(0) if said else "n",
               clock=lambda: time.time(), cwd=lambda: folder)
    return loop


def say(loop, line):
    """One typed line, settled, and every reply it produced."""
    w = loop.world
    w.spawn(Said("user", line))
    loop.run()
    return [reply.text for entity, reply in w.each(Reply)
            if w.destroy(entity) or True]


def named(w, folder, name):
    """The entity for one entry, by name."""
    return w.get(folder, Contents).by_name.get(name)


def folder_of(w, path):
    return fs.folder_at(w, path)


# --- listing ----------------------------------------------------------

def test_show_file_lists_where_the_session_started(folder):
    loop = session(folder)
    assert say(loop, "show file") == [
        "alpha.txt (5 bytes)", "huge.bin (5000 bytes)", "sub/",
        "3 item(s) in %s" % folder,
    ]


def test_the_plural_is_understood_rather_than_corrected_into(folder):
    assert say(session(folder), "show files")[-1].startswith("3 item(s)")


def test_listing_spawns_an_entity_per_entry(folder):
    loop = session(folder)
    say(loop, "show file")
    w = loop.world
    here = folder_of(w, folder)
    assert sorted(w.get(here, Contents).by_name) == ["alpha.txt", "huge.bin", "sub"]
    assert w.get(named(w, here, "huge.bin"), Size) == Size(5000)
    assert w.get(named(w, here, "sub"), Entry).folder == here
    assert w.has(named(w, here, "sub"), fs.IsDir)


def test_listing_the_same_folder_twice_does_not_pile_up_duplicates(folder):
    loop = session(folder)
    say(loop, "show file")
    before = len(loop.world)
    assert len(say(loop, "show file")) == 4      # it answers again...
    assert len(loop.world) == before             # ...and spawns nothing new


def test_relisting_drops_an_entry_that_has_gone_from_the_disk(folder):
    loop = session(folder)
    say(loop, "show file")
    w = loop.world
    here = folder_of(w, folder)
    gone = named(w, here, "alpha.txt")
    os.remove(os.path.join(folder, "alpha.txt"))
    assert say(loop, "show file") == ["huge.bin (5000 bytes)", "sub/",
                                      "2 item(s) in %s" % folder]
    assert not w.alive(gone)
    assert "alpha.txt" not in w.get(here, Contents).by_name


def test_a_folder_that_is_not_there_says_why(folder):
    replies = say(session(folder), "show file in %s/nope" % folder)
    assert replies[0].startswith("! could not list")
    assert "No such file" in replies[0]


# --- here -------------------------------------------------------------

def test_listing_moves_the_focus_and_only_one_folder_has_it(folder, tmp_path):
    other = tmp_path / "other"
    other.mkdir()
    loop = session(folder)
    say(loop, "show file")
    say(loop, "show file in %s" % other)
    w = loop.world
    assert [e for e, _, _ in w.each(Folder, Focus)] == [folder_of(w, str(other))]


def test_show_big_is_about_the_folder_you_last_looked_at(folder, tmp_path):
    other = tmp_path / "other"
    other.mkdir()
    (other / "small.txt").write_text("x", encoding="utf-8")
    loop = session(folder)
    say(loop, "show file")                       # ...the big one is here
    say(loop, "show file in %s" % other)         # ...but now you are there
    assert say(loop, "show big") == ["nothing over 1000 bytes in %s" % other]
    say(loop, "show file in %s" % folder)
    assert say(loop, "show big") == ["huge.bin (5000 bytes)"]


def test_show_big_in_a_folder_nobody_listed_looks_first(folder):
    assert say(session(folder), "show big in %s" % folder) == [
        "huge.bin (5000 bytes)"]


def test_a_directory_is_never_big_however_many_bytes_the_entry_takes(folder):
    loop = session(folder)
    w = loop.world
    entity, session_ = w.each(Session)[0]
    w.attach(entity, Session(session_.cwd, session_.now, big_floor=1))
    assert "sub" not in " ".join(say(loop, "show big in %s" % folder))


def test_a_finding_is_a_component_on_the_file_it_is_about(folder):
    loop = session(folder)
    say(loop, "show big in %s" % folder)
    w = loop.world
    here = folder_of(w, folder)
    assert [e for e, _ in w.each(Big)] == [named(w, here, "huge.bin")]


# --- stale, proposed, approved ----------------------------------------

def test_stale_finds_the_old_file_and_asks_before_touching_it(folder):
    loop = session(folder, answers=["y"])
    replies = say(loop, "stale in %s after 7 days" % folder)
    assert replies[0] == "1 of 3 older than 7 day(s) in %s" % folder
    assert replies[1] == "renamed alpha.txt -> stale-alpha.txt"
    assert os.path.exists(os.path.join(folder, "stale-alpha.txt"))
    assert not os.path.exists(os.path.join(folder, "alpha.txt"))


def test_saying_no_leaves_the_file_alone(folder):
    loop = session(folder, answers=["n"])
    assert say(loop, "stale after 7 days")[-1] == "left alpha.txt alone"
    assert os.path.exists(os.path.join(folder, "alpha.txt"))


def test_a_rename_keeps_the_entity_and_renames_it(folder):
    loop = session(folder)
    say(loop, "show file")
    w = loop.world
    here = folder_of(w, folder)
    entity = named(w, here, "alpha.txt")
    say(loop, "rename alpha.txt to beta.txt")
    # The same file, now called something else -- not a new entity, and
    # nothing about it re-derived.
    assert named(w, here, "beta.txt") == entity
    assert w.get(entity, Entry).name == "beta.txt"
    assert "alpha.txt" not in w.get(here, Contents).by_name


def test_renaming_a_stale_file_unmakes_the_claim(folder):
    loop = session(folder, answers=["y"])
    say(loop, "stale after 7 days")
    w = loop.world
    here = folder_of(w, folder)
    entity = named(w, here, "stale-alpha.txt")
    assert entity is not None and not w.has(entity, Stale)


def test_a_proposal_waits_as_one_component_and_approving_takes_it_off(folder):
    asked = {}

    def ask(prompt):
        w = loop.world
        # Held: the wish exists, and `do_rename` is asking for exactly the
        # ones without this tag, so nothing has happened to it yet.
        asked["held"] = [e for e, _, _ in w.each(RenameWish, NeedsApproval)]
        asked["free"] = w.each(RenameWish, without=NeedsApproval)
        asked["disk"] = sorted(os.listdir(folder))
        return "y"

    loop = Loop()
    fs.install(loop, ask=ask, cwd=lambda: folder)
    say(loop, "stale after 7 days")
    assert len(asked["held"]) == 1 and asked["free"] == []
    assert "alpha.txt" in asked["disk"], "asked first, acted after"


def test_an_already_marked_file_is_not_marked_again(folder):
    loop = session(folder, answers=["y", "y"])
    say(loop, "stale after 7 days")
    replies = say(loop, "stale after 7 days")
    assert replies == ["1 of 3 older than 7 day(s) in %s" % folder]
    assert sorted(os.listdir(folder)) == ["huge.bin", "stale-alpha.txt", "sub"]


def test_your_own_rename_is_not_held_for_approval(folder):
    def refuse(prompt):
        raise AssertionError("nobody should be asked about a rename I typed")

    loop = Loop()
    fs.install(loop, ask=refuse, cwd=lambda: folder)
    say(loop, "show file")
    assert say(loop, "rename huge.bin to enormous.bin") == [
        "renamed huge.bin -> enormous.bin"]
    assert os.path.exists(os.path.join(folder, "enormous.bin"))


def test_a_rename_that_cannot_happen_says_why(folder):
    loop = session(folder)
    say(loop, "show file")
    assert say(loop, "rename nothing.txt to something.txt")[0].startswith(
        "! could not rename")


# --- what is not understood -------------------------------------------

def test_a_line_this_domain_has_no_reading_of_is_left_standing(folder):
    loop = session(folder)
    assert say(loop, "what is for dinner") == []
    # Still there, unclaimed, for another domain's systems or for the REPL
    # to report -- never guessed at, never quietly dropped.
    assert loop.world.the(Said).text == "what is for dinner"


def test_stale_without_a_number_of_days_is_not_a_guess(folder):
    loop = session(folder)
    assert say(loop, "stale after a while") == []
    assert loop.world.the(Said).text == "stale after a while"


def test_the_world_settles_after_every_line(folder):
    loop = session(folder, answers=["y"])
    for line in ("show file", "show big", "stale after 7 days", "show file"):
        loop.world.spawn(Said("user", line))
        assert loop.run().hot == [], "%r never settled" % line


# --- surviving a restart ----------------------------------------------

def restart(folder, path, ask="n"):
    """What `python -m harneskills` does on the way up: an empty world,
    the file read into it, and only then the domain installed."""
    from harneskills import save
    loop = Loop()
    assert save.read(loop.world, path) == []
    fs.install(loop, ask=lambda prompt: ask, cwd=lambda: folder)
    return loop


def test_the_world_survives_a_restart(folder, tmp_path):
    from harneskills import save
    path = str(tmp_path / "world.json")
    loop = session(folder)
    say(loop, "show file")
    save.write(loop.world, path)

    back = restart(folder, path)
    w = back.world
    here = folder_of(w, folder)
    # It knows the folder without going near the disk again -- `show big`
    # answers off what was restored.
    assert sorted(w.get(here, Contents).by_name) == ["alpha.txt", "huge.bin", "sub"]
    assert say(back, "show big") == ["huge.bin (5000 bytes)"]


def test_what_was_concluded_survives_too(folder, tmp_path):
    from harneskills import save
    path = str(tmp_path / "world.json")
    loop = session(folder, answers=["n"])          # found, proposed, refused
    say(loop, "stale after 7 days")
    save.write(loop.world, path)

    w = restart(folder, path).world
    entity = named(w, folder_of(w, folder), "alpha.txt")
    assert w.has(entity, Stale), "a claim a system made is part of the world"


def test_the_folder_you_were_looking_at_survives(folder, tmp_path):
    from harneskills import save
    path = str(tmp_path / "world.json")
    loop = session(folder)
    say(loop, "show file")
    save.write(loop.world, path)

    w = restart(folder, path).world
    assert [e.id for e, _, _ in w.each(Folder, Focus)] == [folder_of(w, folder).id]


def test_installing_over_a_restored_world_replaces_only_the_session(folder, tmp_path):
    from harneskills import save
    from harneskills.examples.model import Session as SessionComponent
    path = str(tmp_path / "world.json")
    loop = session(folder)
    say(loop, "show file")
    before = len(loop.world)
    loop.world.attach(loop.world.each(SessionComponent)[0][0],
                      SessionComponent("/somewhere/else", 1, 1))
    save.write(loop.world, path)

    w = restart(folder, path).world
    # One session, not two -- and it belongs to the process now running.
    assert len(w.each(SessionComponent)) == 1
    assert w.the(SessionComponent).cwd == folder
    assert len(w) == before, "nothing else was spawned over the top"


def test_a_restarted_world_does_not_reuse_an_id_something_points_at(folder, tmp_path):
    from harneskills import save
    path = str(tmp_path / "world.json")
    loop = session(folder)
    say(loop, "show file")
    save.write(loop.world, path)

    back = restart(folder, path)
    w = back.world
    here = folder_of(w, folder)
    known = {e.id for e in w.entities()}
    say(back, "show file in %s" % os.path.join(folder, "sub"))
    fresh = [e.id for e in w.entities() if e.id not in known]
    assert fresh and not (set(fresh) & known)
    assert w.get(here, Contents).by_name["huge.bin"].id in known
