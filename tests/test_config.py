"""What the config file promises: which folders, which files, what order."""

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


# --- read_folders -----------------------------------------------------

def test_missing_file_is_no_folders_not_an_error(tmp_path):
    assert cfg.read_folders(str(tmp_path / "nope")) == []


def test_order_is_file_order(tmp_path):
    conf = write(str(tmp_path / "config"), "/b\n/a\n/c\n")
    assert cfg.read_folders(conf) == ["/b", "/a", "/c"]


def test_blank_lines_and_leading_hash_are_skipped(tmp_path):
    conf = write(str(tmp_path / "config"), "# a note\n\n   \n   # indented\n/keep\n")
    assert cfg.read_folders(conf) == ["/keep"]


def test_hash_inside_a_path_is_kept(tmp_path):
    # A `#` is legal in a directory name; truncating at one would silently
    # turn a real path into a different real path.
    conf = write(str(tmp_path / "config"), "/rules/c#2\n")
    assert cfg.read_folders(conf) == ["/rules/c#2"]


def test_tilde_and_vars_expand(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", "/home/someone")
    monkeypatch.setenv("CORPORA", "/srv/corpora")
    conf = write(str(tmp_path / "config"), "~/rules\n$CORPORA/shared\n")
    assert cfg.read_folders(conf) == ["/home/someone/rules", "/srv/corpora/shared"]


def test_relative_folder_is_relative_to_the_config_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path / "..")
    conf = write(str(tmp_path / "nested" / "config"), "../rules\n")
    assert cfg.read_folders(conf) == [str(tmp_path / "rules")]


# --- corpus_files -----------------------------------------------------

def test_alphabetical_within_a_folder_folders_in_order(tmp_path):
    write(str(tmp_path / "one" / "b.ugm"), "")
    write(str(tmp_path / "one" / "a.ugm"), "")
    write(str(tmp_path / "two" / "c.ugm"), "")
    paths, problems = cfg.corpus_files([str(tmp_path / "two"), str(tmp_path / "one")])
    assert [os.path.basename(p) for p in paths] == ["c.ugm", "a.ugm", "b.ugm"]
    assert problems == []


def test_only_ugm_files_and_only_one_level_deep(tmp_path):
    write(str(tmp_path / "rules" / "keep.ugm"), "")
    write(str(tmp_path / "rules" / "notes.md"), "")
    write(str(tmp_path / "rules" / "sub" / "deep.ugm"), "")
    paths, problems = cfg.corpus_files([str(tmp_path / "rules")])
    assert [os.path.basename(p) for p in paths] == ["keep.ugm"]
    assert problems == []


def test_missing_folder_is_a_problem_not_an_exception(tmp_path):
    write(str(tmp_path / "rules" / "a.ugm"), "")
    paths, problems = cfg.corpus_files([str(tmp_path / "gone"), str(tmp_path / "rules")])
    assert [os.path.basename(p) for p in paths] == ["a.ugm"]
    assert len(problems) == 1 and "no such folder" in problems[0]


def test_empty_folder_is_reported(tmp_path):
    os.makedirs(str(tmp_path / "rules"))
    paths, problems = cfg.corpus_files([str(tmp_path / "rules")])
    assert paths == []
    assert len(problems) == 1 and "no .ugm files" in problems[0]


def test_same_file_through_two_folders_loads_once(tmp_path):
    write(str(tmp_path / "real" / "a.ugm"), "")
    os.symlink(str(tmp_path / "real"), str(tmp_path / "link"))
    paths, _ = cfg.corpus_files([str(tmp_path / "real"), str(tmp_path / "link")])
    assert len(paths) == 1


# --- argv -------------------------------------------------------------

def test_bare_paths_are_corpora(monkeypatch, tmp_path):
    monkeypatch.setenv("HARNESKILLS_CONFIG", str(tmp_path / "config"))
    paths, where, ok = _split_argv(["a.ugm", "b.ugm"])
    assert ok and paths == ["a.ugm", "b.ugm"]
    assert where == str(tmp_path / "config")


def test_no_config_means_no_config_file(monkeypatch, tmp_path):
    monkeypatch.setenv("HARNESKILLS_CONFIG", str(tmp_path / "config"))
    paths, where, ok = _split_argv(["--no-config", "a.ugm"])
    assert ok and paths == ["a.ugm"] and where is None


@pytest.mark.parametrize("argv", [["--config", "/x"], ["--config=/x"]])
def test_config_flag_both_spellings(argv):
    paths, where, ok = _split_argv(argv)
    assert ok and paths == [] and where == "/x"


def test_contradictory_flags_are_refused():
    assert _split_argv(["--config=/x", "--no-config"])[2] is False


def test_config_with_no_path_is_refused():
    assert _split_argv(["--config"])[2] is False


# --- one bad corpus must not take the session -------------------------

def test_bad_corpus_warns_and_the_session_still_starts(tmp_path, monkeypatch, capsys):
    from harneskills import __main__ as entry

    folder = tmp_path / "rules"
    write(str(folder / "a_good.ugm"),
          "rule <boil> = implies( { +water($w), no boiling($w) }, { +boiling($w) } )\n")
    write(str(folder / "b_broken.ugm"), "rule <broken> = implies(\n")
    write(str(folder / "c_good.ugm"),
          "rule <cool> = implies( { +ice($w), no cold($w) }, { +cold($w) } )\n")
    conf = write(str(tmp_path / "config"), str(folder) + "\n")
    monkeypatch.setenv("HARNESKILLS_CONFIG", conf)

    seen = {}

    def fake_run(m, ldr, *a, **k):
        seen["reached"] = True
        return 0

    monkeypatch.setattr(entry.repl, "run", fake_run)

    assert entry.main([]) == 0
    out = capsys.readouterr()
    assert seen.get("reached"), "the REPL was never reached"
    # The broken one is named on stderr; the two either side of it loaded.
    assert "b_broken.ugm" in out.err
    assert "a_good.ugm" in out.out and "c_good.ugm" in out.out
    assert "b_broken.ugm" not in out.out


def test_unreadable_corpus_is_reported_not_raised(tmp_path, monkeypatch, capsys):
    from harneskills import __main__ as entry

    monkeypatch.setenv("HARNESKILLS_CONFIG", str(tmp_path / "none"))
    monkeypatch.setattr(entry.repl, "run", lambda m, ldr, *a, **k: 0)
    assert entry.main([str(tmp_path / "missing.ugm")]) == 0
    assert "missing.ugm" in capsys.readouterr().err


# --- tools: lines -----------------------------------------------------

def test_tools_lines_are_separated_from_folders(tmp_path):
    conf = write(str(tmp_path / "config"),
                 "/a\ntools: pkg.mod:register\n/b\ntools:other:go\n")
    folders, tools = cfg.read_config(conf)
    assert folders == ["/a", "/b"]
    assert tools == ["pkg.mod:register", "other:go"]


def test_read_folders_ignores_tools_lines(tmp_path):
    conf = write(str(tmp_path / "config"), "tools: pkg:go\n/a\n")
    assert cfg.read_folders(conf) == ["/a"]


def test_a_tools_spec_is_not_path_expanded(tmp_path, monkeypatch):
    # It is an import path. `~` in it is a typo, and silently turning it
    # into /home/... would hide that behind a confusing ImportError.
    monkeypatch.setenv("HOME", "/home/someone")
    conf = write(str(tmp_path / "config"), "tools: ~pkg:go\n")
    assert cfg.read_config(conf)[1] == ["~pkg:go"]


def test_no_config_file_means_no_tools(tmp_path):
    assert cfg.read_config(str(tmp_path / "nope")) == ([], [])


# --- _register_tools --------------------------------------------------

def _entry():
    from harneskills import __main__ as entry
    return entry


def test_a_named_callable_is_handed_the_loader():
    seen = []
    import harneskills.config as target
    target._probe = seen.append          # a callable reachable by module:attr
    try:
        problems = _entry()._register_tools("LOADER", ["harneskills.config:_probe"])
        assert problems == []
        assert seen == ["LOADER"]
    finally:
        del target._probe


@pytest.mark.parametrize("spec,fragment", [
    ("no_colon_here", "expected module:callable"),
    (":register", "expected module:callable"),
    ("pkg:", "expected module:callable"),
    ("harneskills.nope:register", "harneskills.nope"),
    ("harneskills.config:not_there", "no not_there"),
    ("harneskills.config:APP", "not callable"),
])
def test_a_bad_spec_is_a_problem_not_an_exception(spec, fragment):
    problems = _entry()._register_tools("LOADER", [spec])
    assert len(problems) == 1 and fragment in problems[0]


def test_a_callable_that_raises_is_a_problem_not_an_exception():
    import harneskills.config as target

    def boom(ldr):
        raise RuntimeError("no tools for you")

    target._boom = boom
    try:
        problems = _entry()._register_tools("LOADER", ["harneskills.config:_boom"])
        assert len(problems) == 1
        assert "RuntimeError" in problems[0] and "no tools for you" in problems[0]
    finally:
        del target._boom


def test_tools_register_before_any_corpus_loads(tmp_path, monkeypatch, capsys):
    """The ordering the whole line kind exists for: a corpus naming an
    answerer parses only if the answerer is already there."""
    entry = _entry()
    import harneskills.config as target

    folder = tmp_path / "rules"
    write(str(folder / "needs_tool.ugm"),
          "rule <use> = implies( { +answered(<probe>, asked(thing), yes) }, "
          "{ +done(thing) } )\n")
    # `tools:` is written AFTER the folder line on purpose -- it must still win.
    conf = write(str(tmp_path / "config"),
                 str(folder) + "\ntools: harneskills.config:_reg\n")
    monkeypatch.setenv("HARNESKILLS_CONFIG", conf)

    def reg(ldr):
        ldr.answerer("probe", "asked", lambda mach, prop: ldr.atom("yes"))

    target._reg = reg
    monkeypatch.setattr(entry.repl, "run", lambda m, ldr, *a, **k: 0)
    try:
        assert entry.main([]) == 0
    finally:
        del target._reg

    # The corpus names <probe>, which exists ONLY because _reg ran. Had the
    # folder line won on file order, this would be a parse error on stderr.
    out = capsys.readouterr()
    assert "needs_tool.ugm" in out.out, out.err
    assert out.err == ""


# --- /reload and /reset -----------------------------------------------

class Script:
    """A stdin whose lines may include callables -- run, then read on.

    Which is how a test edits a corpus mid-session: the point of `/reload`
    is a file that changed while the REPL was sitting at its prompt, and
    there is no other way to be at the prompt and at the filesystem at once.
    """

    def __init__(self, *items):
        self.items = list(items)

    def readline(self):
        while self.items:
            item = self.items.pop(0)
            if callable(item):
                item()
                continue
            return item
        return ""


def test_reload_picks_up_a_rule_edited_mid_session(tmp_path, monkeypatch, capsys):
    entry = _entry()
    folder = tmp_path / "rules"
    corpus = str(folder / "r.ugm")
    v1 = "rule <r> = implies( { +ping(a), no pong(a) }, { +pong(a) } )\n"
    v2 = "rule <r> = implies( { +ping(a), no zap(a) }, { +zap(a) } )\n"
    write(corpus, v1)
    conf = write(str(tmp_path / "config"), str(folder) + "\n")
    monkeypatch.setenv("HARNESKILLS_CONFIG", conf)

    monkeypatch.setattr("sys.stdin", Script(
        "/godmode\n",
        "fact +ping(a)\n",
        lambda: write(corpus, v2),      # the edit, while sitting at the prompt
        "/reload\n",
        "fact +ping(a)\n",
        "/quit\n",
    ))
    assert entry.main([]) == 0
    out = capsys.readouterr().out
    before, _, after = out.partition("reloading")
    assert "pong(a)" in before and "zap(a)" not in before
    assert "zap(a)" in after, "the edited rule never took"
    # <r> was redeclared -- which UGM refuses within one machine, so this
    # also proves the reload built a new one rather than loading over.
    assert "already declared" not in out


def test_reload_forgets_what_was_typed(tmp_path, monkeypatch, capsys):
    entry = _entry()
    monkeypatch.setenv("HARNESKILLS_CONFIG", str(tmp_path / "none"))
    monkeypatch.setattr("sys.stdin", Script(
        "/godmode\n", "fact +secret(x)\n", "/reload\n", "/show\n", "/quit\n"))
    assert entry.main([]) == 0
    _, _, after = capsys.readouterr().out.partition("reloading")
    assert "secret(x)" not in after


def test_user_mode_still_works_after_a_reload(tmp_path, monkeypatch, capsys):
    """The reload re-lays <trust-user>, which belongs to the loop and not to
    any corpus -- forget it and a bare line stops being believed."""
    entry = _entry()
    monkeypatch.setenv("HARNESKILLS_CONFIG", str(tmp_path / "none"))
    monkeypatch.setattr("sys.stdin", Script("/reload\n", "kettle(on)\n", "/quit\n"))
    assert entry.main([]) == 0
    _, _, after = capsys.readouterr().out.partition("reloading")
    assert "trusted(kettle(on))" in after


def test_reload_rereads_the_config_file_itself(tmp_path, monkeypatch, capsys):
    entry = _entry()
    folder = tmp_path / "later"
    write(str(folder / "late.ugm"), "fact +arrived(late)\n")
    conf = write(str(tmp_path / "config"), "# nothing yet\n")
    monkeypatch.setenv("HARNESKILLS_CONFIG", conf)

    monkeypatch.setattr("sys.stdin", Script(
        lambda: write(conf, str(folder) + "\n"),   # a folder added mid-session
        "/reload\n", "/quit\n"))
    assert entry.main([]) == 0
    assert "late.ugm" in capsys.readouterr().out


def test_reset_is_the_same_act_as_reload(tmp_path, monkeypatch, capsys):
    entry = _entry()
    monkeypatch.setenv("HARNESKILLS_CONFIG", str(tmp_path / "none"))
    monkeypatch.setattr("sys.stdin", Script(
        "/godmode\n", "fact +secret(x)\n", "/reset\n", "/show\n", "/quit\n"))
    assert entry.main([]) == 0
    _, _, after = capsys.readouterr().out.partition("reloading")
    assert "secret(x)" not in after


def test_both_commands_are_listed_in_the_help(tmp_path, monkeypatch, capsys):
    entry = _entry()
    monkeypatch.setenv("HARNESKILLS_CONFIG", str(tmp_path / "none"))
    monkeypatch.setattr("sys.stdin", Script("/quit\n"))
    assert entry.main([]) == 0
    out = capsys.readouterr().out
    # Spliced in with the built-ins, above /quit -- not stranded after the prose.
    assert out.index("/reload") < out.index("/quit      leave")
    assert "/reset" in out
