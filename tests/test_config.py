"""What the config file promises: which domains, in what order."""

import os

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
    specs, where, ok = _split_argv(["a:install", "b:install"])
    assert (specs, ok) == (["a:install", "b:install"], True)
    assert where == str(tmp_path / "config")


def test_no_config_means_no_config_file(monkeypatch):
    specs, where, ok = _split_argv(["--no-config", "a:install"])
    assert (specs, where, ok) == (["a:install"], None, True)


def test_config_names_a_file_either_way(tmp_path):
    for argv in (["--config", "/somewhere"], ["--config=/somewhere"]):
        specs, where, ok = _split_argv(argv)
        assert (specs, where, ok) == ([], "/somewhere", True)


def test_config_and_no_config_together_is_refused(capsys):
    assert _split_argv(["--config", "/x", "--no-config"])[2] is False
    assert "opposite" in capsys.readouterr().err


def test_config_without_an_argument_is_refused(capsys):
    assert _split_argv(["--config"])[2] is False
    assert "needs an argument" in capsys.readouterr().err


def test_an_unknown_flag_is_refused_rather_than_taken_for_a_domain(capsys):
    assert _split_argv(["--tools", "a:install"])[2] is False
    assert "no such option" in capsys.readouterr().err
