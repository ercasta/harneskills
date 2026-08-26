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
#
# `_split_argv` returns `(specs, options, ok)` -- `options` a dict with
# keys "config", "state", "serve", "token", "headless".

def test_bare_arguments_are_domains(monkeypatch, tmp_path):
    monkeypatch.setenv("HARNESKILLS_CONFIG", str(tmp_path / "config"))
    monkeypatch.setenv("HARNESKILLS_STATE", str(tmp_path / "world.json"))
    specs, options, ok = _split_argv(["a:install", "b:install"])
    assert (specs, ok) == (["a:install", "b:install"], True)
    assert options["config"] == str(tmp_path / "config")
    assert options["state"] == str(tmp_path / "world.json")
    assert options["serve"] is None and options["headless"] is False


def test_no_config_means_no_config_file(monkeypatch, tmp_path):
    monkeypatch.setenv("HARNESKILLS_STATE", str(tmp_path / "world.json"))
    specs, options, ok = _split_argv(["--no-config", "a:install"])
    assert (specs, options["config"], ok) == (["a:install"], None, True)
    assert options["state"] is not None, "--no-config says nothing about the world"


def test_no_state_means_the_world_starts_empty(monkeypatch, tmp_path):
    monkeypatch.setenv("HARNESKILLS_CONFIG", str(tmp_path / "config"))
    specs, options, ok = _split_argv(["--no-state"])
    assert (options["state"], ok) == (None, True)
    assert options["config"] is not None, "--no-state says nothing about the domains"


def test_each_flag_names_a_file_either_way(tmp_path):
    for argv in (["--config", "/c", "--state", "/s"],
                 ["--config=/c", "--state=/s"]):
        specs, options, ok = _split_argv(argv)
        assert (specs, options["config"], options["state"], ok) == (
            [], "/c", "/s", True)


def test_a_flag_and_its_negation_together_are_refused(capsys):
    assert _split_argv(["--config", "/x", "--no-config"])[2] is False
    assert "opposite" in capsys.readouterr().err
    assert _split_argv(["--no-state", "--state=/x"])[2] is False
    assert "opposite" in capsys.readouterr().err


def test_a_flag_without_an_argument_is_refused(capsys):
    assert _split_argv(["--config"])[2] is False
    assert "needs an argument" in capsys.readouterr().err
    assert _split_argv(["a:install", "--state"])[2] is False
    assert "needs an argument" in capsys.readouterr().err


def test_a_negation_with_an_argument_is_refused(capsys):
    assert _split_argv(["--no-state=/x"])[2] is False
    assert "takes no argument" in capsys.readouterr().err


def test_an_unknown_flag_is_refused_rather_than_taken_for_a_domain(capsys):
    assert _split_argv(["--tools", "a:install"])[2] is False
    assert "no such option" in capsys.readouterr().err


# --- --serve / --token / --headless ------------------------------------

def test_serve_bare_means_loopback_on_the_default_port():
    _, options, ok = _split_argv(["--serve"])
    assert (options["serve"], ok) == (("127.0.0.1", 8765), True)


def test_serve_takes_a_host_and_or_a_port_via_equals():
    assert _split_argv(["--serve=0.0.0.0:9000"])[1]["serve"] == ("0.0.0.0", 9000)
    assert _split_argv(["--serve=:9000"])[1]["serve"] == ("127.0.0.1", 9000)


def test_serve_a_bad_address_is_refused(capsys):
    assert _split_argv(["--serve=host:not-a-port"])[2] is False
    assert "HOST:PORT" in capsys.readouterr().err


def test_serve_never_consumes_the_domain_spec_that_follows_it():
    # The value can ONLY arrive via `=` -- a bare `--serve` followed by a
    # separate token is ambiguous with a domain spec that happens to come
    # next (`--serve fs:install`: the default address, then install `fs`,
    # or the address named `fs:install`?), and there is no reading of the
    # second that makes sense. `ls --color[=WHEN]` draws the same line.
    specs, options, ok = _split_argv(["--serve", "fs:install"])
    assert options["serve"] == ("127.0.0.1", 8765)
    assert specs == ["fs:install"]


def test_token_is_read_like_any_other_valued_flag():
    assert _split_argv(["--serve", "--token", "abc123"])[1]["token"] == "abc123"
    assert _split_argv(["--serve", "--token=abc123"])[1]["token"] == "abc123"


def test_headless_without_serve_is_a_process_nothing_drives(capsys):
    assert _split_argv(["--headless"])[2] is False
    assert "nothing drives" in capsys.readouterr().err


def test_headless_with_serve_is_fine():
    _, options, ok = _split_argv(["--serve", "--headless"])
    assert (options["headless"], ok) == (True, True)


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
