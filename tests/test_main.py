"""What the wiring promises: a domain named is a domain installed, and a
domain that cannot be is a message rather than a dead session."""

from ugm.loop import Loop

import harneskills.examples.fs as fs
from harneskills.__main__ import build, install
from harneskills.examples.model import Session


def test_a_named_domain_is_imported_and_handed_the_loop():
    loop = Loop()
    assert install(loop, ["harneskills.examples.fs:install"]) == []
    assert [name for name, _ in loop.rules][:2] == ["fs.hear", "fs.hear_answer"]
    assert loop.world.the(Session) is not None


def test_every_way_a_spec_can_be_wrong_is_named_and_survivable():
    loop = Loop()
    problems = install(loop, [
        "no-colon-here",
        "harneskills.examples.nosuchthing:install",
        "harneskills.examples.fs:no_such_callable",
        "harneskills.examples.fs:BIG_BYTES",     # exists, is not callable
        "harneskills.examples.fs:install",       # ...and this one is fine
    ])
    assert len(problems) == 4
    assert "expected module:callable" in problems[0]
    assert "no_such_callable" in problems[2]
    assert "not callable" in problems[3]
    assert loop.rules, "the good spec still installed"


def test_a_domain_that_raises_on_install_is_named_not_raised(tmp_path, monkeypatch):
    (tmp_path / "boomdomain.py").write_text(
        "def install(loop):\n    raise RuntimeError('nope')\n", encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    loop = Loop()
    problems = install(loop, ["boomdomain:install", "harneskills.examples.fs:install"])
    assert problems == ["boomdomain:install: RuntimeError: nope"]
    assert loop.rules, "the domain after it still installed"


def test_reload_picks_up_an_edited_module(monkeypatch):
    # `install` reloads a module it finds already imported, which is the
    # whole point of `/reload`: edit a rule, type it, and the new function
    # is what runs. The visible consequence here is that a monkeypatched
    # attribute does NOT survive into the installed domain.
    monkeypatch.setattr(fs, "BIG_BYTES", 1)
    install(Loop(), ["harneskills.examples.fs:install"])
    assert fs.BIG_BYTES == 1000


def test_build_installs_standing_domains_before_the_command_line(tmp_path, capsys):
    conf = tmp_path / "config"
    conf.write_text("harneskills.examples.fs:install\n", encoding="utf-8")
    loop = build(str(conf), ["harneskills.examples.fs:install"])
    # Named on both sides, installed once -- twice would run every rule
    # twice a tick.
    assert [name for name, _ in loop.rules].count("fs.hear") == 1
    assert "installed:" in capsys.readouterr().out


def test_build_with_nothing_installed_says_so(capsys):
    build(None, [])
    assert "no domains installed" in capsys.readouterr().out
