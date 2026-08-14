"""The runner: loading, saying, thinking, and the two things that were subtly
wrong before they were tested -- the shared name scope and the scoped tool door.
"""

from __future__ import annotations

import json

import pytest

from harneskills import Runner, RunnerError

KETTLE = """
rule <boiling> = causes( { +doing(heat(?w)), +water(?w) }, { +boiling(?w) } )
rule <commit>  = implies( { +goal(doing(?a)) }, { +doing(?a) } )
fact +water(kettle)
fact +goal(boiling(kettle))
"""


def test_feed_and_run_reaches_the_goal():
    r = Runner()
    assert r.feed(KETTLE) == 4
    assert r.state == "unstarted"
    steps = r.run()
    assert steps
    assert r.state in ("quiescent", "stopped")
    assert r.holds("boiling(kettle)") == "+"


def test_feeding_does_not_think():
    """Authoring writes and stops. A harness that ran on every line could not
    show a corpus before it had drawn conclusions."""
    r = Runner()
    r.feed(KETTLE)
    assert r.steps == []
    assert r.holds("boiling(kettle)") is None


def test_the_agent_acts_and_says_so():
    r = Runner()
    r.feed(KETTLE)
    r.run()
    assert r.new_emissions() == ["heat(kettle)"]
    assert r.new_emissions() == []       # drained, not re-reported


def test_documents_share_a_name_scope():
    """Two feeds must be about the same kettle, and the second must be able to
    name a rule the first declared -- which a fresh Loader per document cannot
    do, and which is why the runner keeps one."""
    r = Runner()
    r.feed("rule <a> = implies( { +p(?x) }, { +q(?x) } )\nfact +p(thing)")
    r.feed("fact overrides(<a>, <a>)\nfact +r(thing)")
    r.run()
    assert r.holds("q(thing)") == "+"
    assert r.term("thing") == r.term("thing")


def test_separate_scopes_stay_apart():
    r = Runner()
    r.feed("fact +p(thing)", scope="one")
    r.feed("fact +p(thing)", scope="two")
    assert r.term("thing", scope="one") != r.term("thing", scope="two")


def test_say_after_load_lands_in_the_same_scope():
    r = Runner()
    r.feed("rule <trust> = implies( { +says(user, ?p, plus) }, { +?p } )")
    r.say("user", "raining(here)")
    r.run()
    assert r.holds("raining(here)") == "+"


def test_the_agent_does_not_simply_believe_its_user():
    """Without a trust rule the arrival is on the record and nothing about the
    world follows. Heard and not believed is a state worth being able to hold."""
    r = Runner()
    r.say("user", "raining(here)")
    r.run()
    assert r.holds("raining(here)") is None
    # ⚠ Written `plus`, though it prints as `+`: the sign atoms are spelled out
    # in the surface because `+` there is the sign of the statement itself.
    assert r.holds("says(user, raining(here), plus)") == "+"


def test_a_parse_error_is_explained_not_raised_raw():
    r = Runner()
    with pytest.raises(RunnerError) as exc:
        r.feed("fact +boiling(kettle) @certain")
    assert "@" in str(exc.value)          # the engine's own message, kept


def test_the_human_is_a_tool_and_can_be_believed():
    r = Runner()
    asked = []

    def oracle(question):
        asked.append(question)
        return "sunny(here)"

    r.set_oracle(oracle)
    r.feed("""
    rule <curious> = implies( { +goal(?w) }, { +ask(?w) } )
    rule <believe> = implies( { +answered(<human>, ?q, ?a) }, { +?a } )
    fact +goal(weather(today))
    """)
    r.run()
    assert asked == ["weather(today)"]
    assert r.holds("sunny(here)") == "+"


def test_declining_is_an_answer():
    r = Runner()
    r.set_oracle(lambda q: None)
    r.feed("""
    rule <curious> = implies( { +goal(?w) }, { +ask(?w) } )
    fact +goal(weather(today))
    """)
    r.run()
    assert r.state in ("quiescent", "stopped")   # it carried on regardless


def test_run_reports_each_tick_as_it_happens():
    r = Runner()
    r.feed(KETTLE)
    seen = []
    r.run(on_step=lambda s: seen.append(s.state) or True)
    assert len(seen) == len(r.steps)


def test_a_callback_can_stop_the_run():
    r = Runner()
    r.feed(KETTLE)
    steps = r.run(on_step=lambda s: False)
    assert len(steps) == 1
    assert r.state not in ("quiescent",)


def test_save_and_resume_without_acting_again(tmp_path):
    r = Runner()
    r.feed(KETTLE)
    r.run()
    assert r.new_emissions() == ["heat(kettle)"]
    path = tmp_path / "session.json"
    r.save(str(path))
    assert json.loads(path.read_text())["ugm"] == 1

    again = Runner()
    again.resume(str(path))
    # It remembers acting -- and nothing left the agent a second time.
    assert again.holds("boiling(kettle)") == "+"
    assert again.new_emissions() == []
