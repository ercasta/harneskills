"""The view: the layer classification, and that every projection is read-only."""

from __future__ import annotations

import harneskills as h
from harneskills import Runner

KETTLE = """
rule <boiling> = causes( { +doing(heat(?w)), +water(?w) }, { +boiling(?w) } )
rule <commit>  = implies( { +goal(doing(?a)) }, { +doing(?a) } )
fact +water(kettle)
fact +goal(boiling(kettle))
"""


def solved() -> Runner:
    r = Runner()
    r.feed(KETTLE)
    r.run()
    return r


def test_corpus_vocabulary_is_world_and_machinery_is_not():
    """The whole classification rests on this: a relation the corpus coined is
    world, a relation the engine reserved is not. Nothing is hand-listed."""
    r = solved()
    world = {p.text for p in h.propositions(r.machine, ["world"])}
    assert "water(kettle)" in world
    assert "boiling(kettle)" in world
    assert not any(t.startswith("goal(") or t.startswith("fits(") for t in world)


def test_layers_partition_what_is_settled():
    r = solved()
    everything = h.propositions(r.machine, generic=True)
    per_layer = sum(len(h.propositions(r.machine, [l], generic=True)) for l in h.LAYERS)
    assert len(everything) == per_layer
    assert len({p.node for p in everything}) == len(everything)


def test_every_layer_is_explained():
    assert set(h.LAYER_HELP) == set(h.LAYERS)


def test_a_view_never_changes_the_machine():
    """Every projection is a rendering. If one of these starts minting nodes it
    has begun deriving something, and a viewer that derives is a second engine
    with no provenance -- so this is the module's whole invariant, asserted."""
    r = solved()
    before = r.machine.g.count(), len(r.steps)
    h.propositions(r.machine, generic=True, settled_only=False)
    h.goal_tree(r.machine)
    h.rules(r.machine, bundled=True)
    h.tools(r.machine)
    h.channels(r.machine)
    h.counts(r.machine)
    h.why(r.machine, r.term("boiling(kettle)"))
    assert (r.machine.g.count(), len(r.steps)) == before


def test_credit_is_the_one_projection_that_costs_something():
    """⚠ `credit` is the exception, and it is upstream's rather than ours:
    `Machine.review` / `Machine.blame` mint as they walk the licences. Recorded
    as a test so that it is a known property rather than a surprise -- a UI must
    not put this one on a refresh timer."""
    r = solved()
    before = r.machine.g.count()
    h.credit(r.machine)
    assert r.machine.g.count() > before


def test_goal_tree_recovers_the_reports_nesting():
    r = solved()
    rows = h.goal_tree(r.machine)
    assert rows[0].kind == "section" and rows[0].text == "asked for:"
    goal = next(x for x in rows if x.text.startswith("boiling(kettle)"))
    assert goal.depth == 1 and goal.status == "held"
    sub = next(x for x in rows if x.text.startswith("water(kettle)"))
    assert sub.depth == 2


def test_a_blocked_goal_is_marked_as_such():
    """Delete the rule that commits to acting and the same plan is found and
    nothing is done -- which the tree must say rather than merely omit."""
    r = Runner()
    r.feed("""
    rule <boiling> = causes( { +doing(heat(?w)), +water(?w) }, { +boiling(?w) } )
    fact +water(kettle)
    fact +goal(boiling(kettle))
    """)
    r.run()
    assert any(x.status == "BLOCKED" for x in h.goal_tree(r.machine))


def test_rules_shows_what_applied_and_hides_the_bundle_by_default():
    r = solved()
    authored = h.rules(r.machine)
    assert {x.name for x in authored} == {"boiling", "commit"}
    assert all(x.exercised for x in authored)
    assert len(h.rules(r.machine, bundled=True)) > len(authored)


def test_modality_needs_no_special_column():
    """Grades left the entry; `likely(p)` is an ordinary proposition, so it
    lands in `world` beside everything else with nothing added here."""
    r = Runner()
    r.feed("""
    rule <w> = implies( { +cloudy(?d) }, { +likely(rain(?d)) } )
    fact +cloudy(monday)
    """)
    r.run()
    assert "likely(rain(monday))" in {p.text for p in h.propositions(r.machine, ["world"])}


def test_why_answers_the_empty_case_rather_than_returning_nothing():
    r = Runner()
    r.feed("fact +p(a)")
    lines = h.why(r.machine, r.term("q(a)"))
    assert lines and "nothing concluded it" in lines[0]


def test_provenance_names_the_channel_and_the_licence():
    r = Runner()
    r.feed("rule <trust> = implies( { +says(user, ?p, plus) }, { +?p } )")
    r.say("user", "raining(here)")
    r.run()
    trail = "\n".join(h.why(r.machine, r.term("raining(here)")))
    assert "<trust>" in trail
    assert "user" in trail


def test_step_lines_name_the_silence():
    r = Runner()
    r.feed("fact +p(a)")
    r.run()
    last = h.step_lines(r.machine, r.steps[-1])
    assert last[0].startswith("[")
    assert h.view.STATE_HELP[r.steps[-1].state] in last[0]
