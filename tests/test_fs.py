"""The filesystem domain, end to end: words in, facts and real files out.

The old harness's own README admitted its test suite never reached the
example, and two bugs sat in it unnoticed as a result. These drive the
whole chain -- a typed line, the rules, the tools, the disk -- through the
same `Loop` the REPL uses.
"""

import os
import time

import pytest

from ugm.loop import Loop
from ugm.world import Reply, Said

from harneskills.examples import fs
from harneskills.examples.model import (Asked, Big, Contents, Entry, Focus,
                                        Folder, NeedsApproval, RenameWish,
                                        Session, Size, Stale)

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


def session(folder):
    """A loop with the fs domain installed, launched "in" `folder`, with a
    fixed clock. Approval is answered by `say`ing "y" or "n" once the
    question comes back as a reply -- see `approve`/`hear_answer` in
    `fs.py`; nothing here is asked synchronously any more."""
    loop = Loop()
    fs.install(loop, clock=lambda: time.time(), cwd=lambda: folder)
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
    loop = session(folder)
    replies = say(loop, "stale in %s after 7 days" % folder)
    assert replies[0] == "1 of 3 older than 7 day(s) in %s" % folder
    assert replies[1] == "approve rename alpha.txt -> stale-alpha.txt in %s? [y/n]" % folder
    assert os.path.exists(os.path.join(folder, "alpha.txt")), "asked, not yet acted"
    assert say(loop, "y") == ["renamed alpha.txt -> stale-alpha.txt"]
    assert os.path.exists(os.path.join(folder, "stale-alpha.txt"))
    assert not os.path.exists(os.path.join(folder, "alpha.txt"))


def test_saying_no_leaves_the_file_alone(folder):
    loop = session(folder)
    say(loop, "stale after 7 days")
    assert say(loop, "n") == ["left alpha.txt alone"]
    assert os.path.exists(os.path.join(folder, "alpha.txt"))


def test_yes_or_no_answers_whichever_wish_is_currently_asked(folder):
    # Anyone's "y" resolves it -- this domain has not been taught to
    # whisper, and neither has this test's assertion about who may answer.
    loop = session(folder)
    say(loop, "stale after 7 days")
    loop.world.spawn(Said("someone-else", "y"))
    loop.run()
    assert not os.path.exists(os.path.join(folder, "alpha.txt"))


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
    loop = session(folder)
    say(loop, "stale after 7 days")
    say(loop, "y")
    w = loop.world
    here = folder_of(w, folder)
    entity = named(w, here, "stale-alpha.txt")
    assert entity is not None and not w.has(entity, Stale)


def test_a_proposal_waits_as_one_component_until_answered(folder):
    loop = session(folder)
    say(loop, "stale after 7 days")
    w = loop.world
    # Held: the wish exists, and `do_rename` asks for exactly the ones
    # without this tag, so nothing has happened to it yet.
    assert len(w.each(RenameWish, NeedsApproval)) == 1
    assert w.each(RenameWish, without=NeedsApproval) == []
    assert "alpha.txt" in os.listdir(folder), "asked first, acted after"
    say(loop, "y")
    assert "alpha.txt" not in os.listdir(folder)


def test_only_one_wish_is_asked_about_at_a_time(tmp_path):
    # Two stale files, two proposals -- but only one question ever goes
    # out, so a "y" answers the one that was asked and never the other.
    old = time.time() - 30 * DAY
    for name in ("old1.txt", "old2.txt"):
        (tmp_path / name).write_text("x", encoding="utf-8")
        os.utime(tmp_path / name, (old, old))
    loop = session(str(tmp_path))
    replies = say(loop, "stale after 7 days")
    assert sum(r.startswith("approve rename") for r in replies) == 1
    w = loop.world
    assert len(w.each(RenameWish, Asked)) == 1
    assert len(w.each(RenameWish, NeedsApproval, without=Asked)) == 1
    say(loop, "y")
    # One resolved, and the other's question goes out only now.
    assert sorted(os.listdir(str(tmp_path))) == ["old2.txt", "stale-old1.txt"]
    assert len(w.each(RenameWish, Asked)) == 1


def test_an_already_marked_file_is_not_marked_again(folder):
    loop = session(folder)
    say(loop, "stale after 7 days")
    say(loop, "y")
    replies = say(loop, "stale after 7 days")
    assert replies == ["1 of 3 older than 7 day(s) in %s" % folder]
    assert sorted(os.listdir(folder)) == ["huge.bin", "stale-alpha.txt", "sub"]


def test_your_own_rename_is_not_held_for_approval(folder):
    loop = session(folder)
    say(loop, "show file")
    replies = say(loop, "rename huge.bin to enormous.bin")
    assert replies == ["renamed huge.bin -> enormous.bin"], (
        "a rename typed directly must never be held for approval")
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
    loop = session(folder)
    # A question left unanswered still settles -- `approve` does not ask
    # about an already-`Asked` wish twice, so nothing here spins.
    for line in ("show file", "show big", "stale after 7 days", "show file", "y"):
        loop.world.spawn(Said("someone", line))
        assert loop.run().hot == [], "%r never settled" % line


# --- surviving a restart ----------------------------------------------

def restart(folder, path):
    """What `python -m harneskills` does on the way up: an empty world,
    the file read into it, and only then the domain installed."""
    from ugm import save
    loop = Loop()
    assert save.read(loop.world, path) == []
    fs.install(loop, cwd=lambda: folder)
    return loop


def test_the_world_survives_a_restart(folder, tmp_path):
    from ugm import save
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
    from ugm import save
    path = str(tmp_path / "world.json")
    loop = session(folder)
    say(loop, "stale after 7 days")     # found, proposed, asked
    say(loop, "n")                      # refused
    save.write(loop.world, path)

    w = restart(folder, path).world
    entity = named(w, folder_of(w, folder), "alpha.txt")
    assert w.has(entity, Stale), "a claim a system made is part of the world"


def test_the_folder_you_were_looking_at_survives(folder, tmp_path):
    from ugm import save
    path = str(tmp_path / "world.json")
    loop = session(folder)
    say(loop, "show file")
    save.write(loop.world, path)

    w = restart(folder, path).world
    assert [e.id for e, _, _ in w.each(Folder, Focus)] == [folder_of(w, folder).id]


def test_installing_over_a_restored_world_replaces_only_the_session(folder, tmp_path):
    from ugm import save
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
    from ugm import save
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


# --- one directory is one folder --------------------------------------

@pytest.mark.parametrize("spelling", ["%s", "%s/", "%s/./", "%s/sub/.."])
def test_two_spellings_of_a_directory_are_one_folder(folder, spelling):
    loop = session(folder)
    say(loop, "show file")
    w = loop.world
    before = len(w.each(Folder))
    assert say(loop, "show file in %s" % (spelling % folder))[-1].endswith(folder)
    # A second Folder would bring its own Contents to fill and its own
    # Focus to fight over.
    assert len(w.each(Folder)) == before


def test_a_relative_path_is_the_folder_it_names(folder, monkeypatch):
    monkeypatch.chdir(folder)
    loop = session(folder)
    say(loop, "show file")
    assert say(loop, "show file in sub")[-1] == "0 item(s) in %s" % os.path.join(
        folder, "sub")


def test_the_folder_a_person_typed_is_the_one_they_are_shown(folder):
    # Normalising for comparison and normalising for display are
    # different jobs: `folder_at` matches through `normcase`, and stores
    # the spelling first seen.
    loop = session(folder)
    assert say(loop, "show file in %s/" % folder)[-1] == "3 item(s) in %s" % folder
