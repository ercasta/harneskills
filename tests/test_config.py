"""What the config file promises: which domains, in what order."""

import os

import pytest

from harneskills import config as cfg
from harneskills.__main__ import _split_argv


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    return path


# --- config_path ------------------------------------------------------

def test_xdg_location_is_the_default(monkeypatch, tmp_path):
    monkeypatch.delenv("HARNESKILLS_CONFIG", raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    assert cfg.config_path() == str(tmp_path / "cfg" / "harneskills" / "config")


def test_falls_back_to_dot_config_under_home(monkeypatch, tmp_path):
    monkeypatch.delenv("HARNESKILLS_CONFIG", raising=False)
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    assert cfg.config_path() == str(tmp_path / ".config" / "harneskills" / "config")


def test_env_override_wins(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "ignored"))
    monkeypatch.setenv("HARNESKILLS_CONFIG", str(tmp_path / "elsewhere"))
    assert cfg.config_path() == str(tmp_path / "elsewhere")


# --- read_domains -----------------------------------------------------

def test_missing_file_is_no_domains_not_an_error(tmp_path):
    assert cfg.read_domains(str(tmp_path / "nope")) == []


def test_a_folder_where_a_file_should_be_is_no_domains_either(tmp_path):
    assert cfg.read_domains(str(tmp_path)) == []


def test_order_is_file_order(tmp_path):
    conf = write(str(tmp_path / "config"), "b:install\na:install\nc:install\n")
    assert cfg.read_domains(conf) == ["b:install", "a:install", "c:install"]


def test_blank_lines_and_leading_hash_are_skipped(tmp_path):
    conf = write(str(tmp_path / "config"),
                 "# a note\n\n   \n   # indented\nkeep:install\n")
    assert cfg.read_domains(conf) == ["keep:install"]


def test_surrounding_space_is_not_part_of_the_spec(tmp_path):
    conf = write(str(tmp_path / "config"), "   pkg.mod:install   \n")
    assert cfg.read_domains(conf) == ["pkg.mod:install"]


def test_the_same_domain_twice_is_installed_once(tmp_path):
    # Installing twice would register every rule twice, and every one of
    # them would then run twice a tick.
    conf = write(str(tmp_path / "config"), "a:install\nb:install\na:install\n")
    assert cfg.read_domains(conf) == ["a:install", "b:install"]


def test_nothing_here_imports_what_it_names(tmp_path):
    conf = write(str(tmp_path / "config"), "no.such.module.at.all:install\n")
    assert cfg.read_domains(conf) == ["no.such.module.at.all:install"]


# --- the command line -------------------------------------------------

def test_bare_arguments_are_domains(monkeypatch, tmp_path):
    monkeypatch.setenv("HARNESKILLS_CONFIG", str(tmp_path / "config"))
    monkeypatch.setenv("HARNESKILLS_STATE", str(tmp_path / "world.json"))
    specs, where, state, ok = _split_argv(["a:install", "b:install"])
    assert (specs, ok) == (["a:install", "b:install"], True)
    assert where == str(tmp_path / "config")
    assert state == str(tmp_path / "world.json")


def test_no_config_means_no_config_file(monkeypatch, tmp_path):
    monkeypatch.setenv("HARNESKILLS_STATE", str(tmp_path / "world.json"))
    specs, where, state, ok = _split_argv(["--no-config", "a:install"])
    assert (specs, where, ok) == (["a:install"], None, True)
    assert state is not None, "--no-config says nothing about the world"


def test_no_state_means_the_world_starts_empty(monkeypatch, tmp_path):
    monkeypatch.setenv("HARNESKILLS_CONFIG", str(tmp_path / "config"))
    specs, where, state, ok = _split_argv(["--no-state"])
    assert (state, ok) == (None, True)
    assert where is not None, "--no-state says nothing about the domains"


def test_each_flag_names_a_file_either_way(tmp_path):
    for argv in (["--config", "/c", "--state", "/s"],
                 ["--config=/c", "--state=/s"]):
        specs, where, state, ok = _split_argv(argv)
        assert (specs, where, state, ok) == ([], "/c", "/s", True)


def test_a_flag_and_its_negation_together_are_refused(capsys):
    assert _split_argv(["--config", "/x", "--no-config"])[3] is False
    assert "opposite" in capsys.readouterr().err
    assert _split_argv(["--no-state", "--state=/x"])[3] is False
    assert "opposite" in capsys.readouterr().err


def test_a_flag_without_an_argument_is_refused(capsys):
    assert _split_argv(["--config"])[3] is False
    assert "needs an argument" in capsys.readouterr().err
    assert _split_argv(["a:install", "--state"])[3] is False
    assert "needs an argument" in capsys.readouterr().err


def test_a_negation_with_an_argument_is_refused(capsys):
    assert _split_argv(["--no-state=/x"])[3] is False
    assert "takes no argument" in capsys.readouterr().err


def test_an_unknown_flag_is_refused_rather_than_taken_for_a_domain(capsys):
    assert _split_argv(["--tools", "a:install"])[3] is False
    assert "no such option" in capsys.readouterr().err


# --- state_path -------------------------------------------------------

def test_the_world_lives_in_the_xdg_state_directory(monkeypatch, tmp_path):
    monkeypatch.delenv("HARNESKILLS_STATE", raising=False)
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    assert cfg.state_path() == str(tmp_path / "state" / "harneskills" / "world.json")


def test_state_falls_back_under_home(monkeypatch, tmp_path):
    monkeypatch.delenv("HARNESKILLS_STATE", raising=False)
    monkeypatch.delenv("XDG_STATE_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    assert cfg.state_path() == str(
        tmp_path / ".local" / "state" / "harneskills" / "world.json")


def test_the_state_env_override_wins(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "ignored"))
    monkeypatch.setenv("HARNESKILLS_STATE", str(tmp_path / "elsewhere.json"))
    assert cfg.state_path() == str(tmp_path / "elsewhere.json")


# --- where a Windows box keeps the same two files ---------------------

@pytest.fixture
def windows(monkeypatch):
    """Pretend, for the length of one test. `config_path` reads `os.name`
    when it is called, which is the only reason this works -- and the
    only reason it is worth testing on a Linux box at all."""
    monkeypatch.setattr(cfg.os, "name", "nt")
    monkeypatch.delenv("HARNESKILLS_CONFIG", raising=False)
    monkeypatch.delenv("HARNESKILLS_STATE", raising=False)


def test_windows_puts_the_domains_in_appdata(windows, monkeypatch, tmp_path):
    monkeypatch.setenv("APPDATA", str(tmp_path / "Roaming"))
    assert cfg.config_path() == os.path.join(
        str(tmp_path / "Roaming"), "harneskills", "config")


def test_windows_puts_the_world_in_localappdata(windows, monkeypatch, tmp_path):
    # Local, not roaming: a world full of absolute paths to this machine's
    # disk is not something you want following you to another machine.
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "Local"))
    assert cfg.state_path() == os.path.join(
        str(tmp_path / "Local"), "harneskills", "world.json")


def test_windows_falls_back_under_appdata_not_under_dot_config(
        windows, monkeypatch, tmp_path):
    monkeypatch.delenv("APPDATA", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    assert cfg.config_path() == os.path.join(
        str(tmp_path), "AppData", "Roaming", "harneskills", "config")


def test_windows_ignores_the_xdg_variables(windows, monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "nope"))
    monkeypatch.setenv("APPDATA", str(tmp_path / "Roaming"))
    assert "nope" not in cfg.config_path()


def test_the_env_override_still_wins_on_windows(windows, monkeypatch, tmp_path):
    monkeypatch.setenv("APPDATA", str(tmp_path / "Roaming"))
    monkeypatch.setenv("HARNESKILLS_STATE", str(tmp_path / "elsewhere.json"))
    assert cfg.state_path() == str(tmp_path / "elsewhere.json")
