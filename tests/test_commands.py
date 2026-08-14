"""The command layer, which every front end shares."""

from __future__ import annotations

from harneskills import COMMANDS, Runner, dispatch
from harneskills.commands import CORPUS_KEYWORDS


def drive(r, text):
    """Dispatch, and carry out a `/run` inline the way a front end would."""
    resp = dispatch(r, text)
    if resp.drive is not None:
        r.run(resp.drive)
    return resp


def test_the_input_language_is_the_corpus_language():
    r = Runner()
    for line in ("fact +water(kettle)",
                 "rule <b> = causes( { +water(?w) }, { +wet(?w) } )",
                 "say user: +raining(here)"):
        assert dispatch(r, line).ok, line
    assert r.holds("water(kettle)") == "+"


def test_a_bare_term_asks_and_explains():
    r = Runner()
    dispatch(r, "rule <b> = causes( { +water(?w) }, { +wet(?w) } )")
    dispatch(r, "fact +water(kettle)")
    drive(r, "/run")
    out = "\n".join(dispatch(r, "wet(kettle)").lines)
    assert "held" in out
    assert "<b>" in out          # the verdict AND the trail


def test_an_unknown_command_suggests_rather_than_shrugs():
    r = Runner()
    resp = dispatch(r, "/repot")
    assert not resp.ok
    assert any("/report" in l for l in resp.lines)


def test_a_bad_statement_reports_the_engines_own_words():
    r = Runner()
    resp = dispatch(r, "fact +p(a) @certain")
    assert not resp.ok
    assert "@" in "\n".join(resp.lines)


def test_run_hands_back_a_budget_rather_than_driving_itself():
    """So a UI can put it on a worker and show ticks as they land."""
    r = Runner()
    dispatch(r, "fact +p(a)")
    resp = dispatch(r, "/run")
    assert resp.drive is not None and r.steps == []


def test_graph_refuses_an_unknown_layer_and_names_the_real_ones():
    r = Runner()
    resp = dispatch(r, "/graph nonsense")
    assert not resp.ok
    assert "world" in "\n".join(resp.lines)


def test_graph_defaults_to_the_world():
    r = Runner()
    dispatch(r, "fact +water(kettle)")
    out = "\n".join(dispatch(r, "/graph").lines)
    assert "water(kettle)" in out
    assert "scoped(" not in out          # machinery is not the default view


def test_commands_that_only_look_do_not_mark_the_graph_changed():
    r = Runner()
    dispatch(r, "fact +p(a)")
    for verb in ("/report", "/graph", "/rules", "/tools", "/channels"):
        assert dispatch(r, verb).changed is False, verb


def test_help_is_rendered_from_the_command_table():
    r = Runner()
    out = "\n".join(dispatch(r, "/help").lines)
    for c in COMMANDS:
        assert c.name in out, c.name
    for keyword in CORPUS_KEYWORDS:
        assert keyword in out


def test_comments_and_blank_lines_are_accepted_silently():
    r = Runner()
    assert dispatch(r, "").lines == []
    assert dispatch(r, "# a note").lines == []


def test_save_and_resume_round_trip(tmp_path):
    r = Runner()
    dispatch(r, "fact +water(kettle)")
    drive(r, "/run")
    path = tmp_path / "s.json"
    assert dispatch(r, f"/save {path}").ok
    assert dispatch(r, f"/resume {path}").ok
    assert r.holds("water(kettle)") == "+"


def test_resume_of_a_missing_file_is_explained():
    r = Runner()
    resp = dispatch(r, "/resume nowhere.json")
    assert not resp.ok and "no such session" in resp.lines[0]


def test_loading_the_shipped_corpora():
    for name in ("kettle", "weather", "ask"):
        r = Runner()
        r.set_oracle(lambda q: "sunny(here)")
        resp = dispatch(r, f"/load corpus/{name}.ugm")
        assert resp.ok, (name, resp.lines)
        drive(r, "/run")
        assert r.state in ("quiescent", "stopped"), name
