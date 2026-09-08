"""`harneskills.examples.automations` -- `loopingrules.circuits.Call`,
proven against this repo's own real tool (`fs_tools.ls`) rather than a
synthetic stand-in: a DATA-authored spec refreshes a real folder's
listing, twice, against a real, changing disk -- and the one tool that
actually mutates anything (`fs_tools.rename`) is checked to be
structurally unreachable through the registry this module installs.
"""

import os

import pytest

from loopingrules import circuits
from loopingrules.loop import Loop
from loopingrules.world import World

from harneskills.examples import automations, fs
from harneskills.examples.model import Contents, RescanWanted, Size


def _folder(tmp_path):
    """A bare `World`, one `Folder` entity naming `tmp_path`, and nothing
    listed yet -- `fs.folder_at` is the only thing that makes one, the
    same rule this module's own docstring already names."""
    w = World()
    entity = fs.folder_at(w, str(tmp_path))
    return w, entity


def _rescan(w, folder):
    """One `RescanWanted`, compiled and run directly against `w` -- no
    `Loop` needed for a single-spec check."""
    w.spawn(RescanWanted(folder.id))
    rule = circuits.compile_circuit(automations.do_rescan_spec, tools=automations.TOOLS)
    rule(w)


def test_do_rescan_spec_populates_real_entries_via_the_registered_tool(tmp_path):
    (tmp_path / "a.txt").write_text("hi")
    w, folder = _folder(tmp_path)
    _rescan(w, folder)
    contents = w.get(folder, Contents)
    assert "a.txt" in contents.by_name
    entry = w.entity(contents.by_name["a.txt"])
    real = (tmp_path / "a.txt").stat()
    assert w.get(entry, Size) == Size(real.st_size)
    assert w.first(RescanWanted) is None    # claimed and destroyed


def test_do_rescan_spec_removes_an_entry_deleted_from_disk_since_the_last_look(tmp_path):
    (tmp_path / "gone.txt").write_text("bye")
    w, folder = _folder(tmp_path)
    _rescan(w, folder)
    assert "gone.txt" in w.get(folder, Contents).by_name

    os.remove(tmp_path / "gone.txt")
    _rescan(w, folder)
    assert "gone.txt" not in w.get(folder, Contents).by_name


def test_a_spec_naming_rename_is_refused_before_touching_a_world():
    """The capability boundary this module exists to draw, checked, not
    just documented: `TOOLS` never registers `"rename"`, so a spec that
    tries fails at `compile_circuit`, before any `World` is even
    constructed here."""
    would_rename = circuits.ActionCircuit(
        require=(RescanWanted,),
        without=(),
        effects=(circuits.Call("rename", ()), circuits.Destroy()),
    )
    with pytest.raises(KeyError, match="rename"):
        circuits.compile_circuit(would_rename, tools=automations.TOOLS)


def test_automations_install_composes_with_fs_on_one_loop(tmp_path):
    """`automations.install` and `fs.install` on the SAME `Loop`: a
    data-authored refresh and this domain's own hand-written pipeline,
    oblivious to each other, over one shared `World` -- the ordinary
    structural-stigmergy claim `PRINCIPLES.md` makes, exercised for
    real rather than argued."""
    (tmp_path / "b.txt").write_text("hi")
    loop = Loop()
    fs.install(loop, clock=lambda: 0, cwd=lambda: str(tmp_path))
    automations.install(loop)
    w = loop.world
    folder = fs.folder_at(w, str(tmp_path))
    w.spawn(RescanWanted(folder.id))
    loop.run()
    assert "b.txt" in w.get(folder, Contents).by_name
