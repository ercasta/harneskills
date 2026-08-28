"""The vocabulary's own pins: what a relation IS, and the four hazards
`facts.py`'s module note says it exists to have already survived.

⭐ Three of these arrived with the module from `pystrider` (2026-08-28),
where they had been sitting in a "the substrate adapter" section of a suite
about Python. They use no domain at all -- that is what made them the wrong
tests to leave behind, and the right ones to keep here.
"""
from __future__ import annotations

import pytest

from ugm.facts import Facts, Printed, relation


# -- what a relation IS ----------------------------------------------------------


def test_a_relation_is_a_component_and_its_objects_are_ORDERED_rows():
    """⚠ A body is an ordered thing. Describing a three-line loop by its first
    statement is the bug ordering exists to prevent."""
    f = Facts()
    block, s1, s2 = f.node("block"), f.node("s1"), f.node("s2")
    f.fact("stmt", block, s1)
    f.fact("stmt", block, s2)
    assert f.of("stmt", block) == [(s1,), (s2,)]


def test_a_KIND_is_the_same_relation_with_one_EMPTY_row():
    """Nothing to say about the subject except that it is one."""
    f = Facts()
    n = f.node("n")
    f.fact("for_stmt", n)
    assert f.of("for_stmt", n) == [()]
    assert f.has("for_stmt", n) and f.subjects("for_stmt") == [n]


def test_rows_are_DEDUPED_so_fact_is_idempotent():
    f = Facts()
    block, s1 = f.node("block"), f.node("s1")
    f.fact("stmt", block, s1)
    f.fact("stmt", block, s1)
    assert f.of("stmt", block) == [(s1,)]


def test_state_REPLACES_where_fact_appends():
    """⭐ A conclusion that can be revised must not leave both answers standing —
    `one()` would then refuse to pick, correctly, about a question with one answer."""
    f = Facts()
    point, a, b = f.node("point"), f.word("a"), f.word("b")
    f.state("winner", point, a)
    f.state("winner", point, b)
    assert f.of("winner", point) == [(b,)]
    assert f.one("winner", point) == b


def test_deny_is_REMOVAL_so_a_reader_cannot_see_a_withdrawn_claim():
    """⚠ An append-only chain spelled *change this* as `-old, +new`, and a reader
    walking its own deposit log saw BOTH — a repair that "succeeded" while emitting
    byte-identical source. There is one store here, and removal is removal."""
    f = Facts()
    cmp_, gt, ge = f.node("cmp"), f.word("gt"), f.word("ge")
    f.fact("operator", cmp_, gt)
    assert f.deny("operator", cmp_, gt) is True
    assert f.deny("operator", cmp_, gt) is False, "nothing left to withdraw"
    f.fact("operator", cmp_, ge)
    assert f.of("operator", cmp_) == [(ge,)]


def test_one_REFUSES_to_pick_between_several_rather_than_taking_the_first():
    """⚠ Taking `of(...)[0]` is the shape of two measured bugs: a three-line loop
    described by its first statement, and `f(a, b)` described by its first argument
    after a gap renumbered the rest."""
    f = Facts()
    assign, a, b = f.node("assign"), f.node("a"), f.node("b")
    f.fact("assigned", assign, a)
    f.fact("assigned", assign, b)
    assert f.one("assigned", f.node("untouched")) is None, "silence is not a refusal"
    with pytest.raises(ValueError):
        f.one("assigned", assign)


def test_reify_INTERNS_so_a_claim_about_a_claim_JOINS():
    """⚠ Asking twice about the same proposition must get the same subject, or two
    rules reasoning about it never meet."""
    f = Facts()
    n, case = f.node("n"), f.value(3)
    p = f.reify("evaluated", n, case)
    assert f.reify("evaluated", n, case) == p
    assert f.has("proposition", p)


# -- the four hazards ------------------------------------------------------------


def test_the_TWIN_TRAP_is_structurally_impossible():
    """⚠⚠ It cost four recorded wrong readings, and there is nothing left to get wrong.

    A graph substrate minting a FRESH node per `atom(name)` call made a relation
    built beside the corpus's table a TWIN: nothing matched, and the run reported a
    contented quiescence having done nothing. A relation is a Python class interned
    by name here — two lookups are the same object because Python says so.
    """
    assert relation("for_stmt") is relation("for_stmt")
    f = Facts()
    assert f.word("gt") == f.word("gt"), "a WORD interns too"
    assert f.node("gt") != f.node("gt"), "...but an occurrence does not"


def test_a_WORD_and_a_LITERAL_are_different_kinds_of_entity():
    """⚠⚠ Conflating them made a corpus unable to talk about code: the operator was
    stored `repr`-encoded as `'gt'`, so a rule naming the bare `gt` could never
    match and one of two rule families was dead — and the suite could not tell."""
    f = Facts()
    assert f.word("gt") != f.value("gt")
    assert f.show(f.word("gt")) == "gt" and f.show(f.value("gt")) == "'gt'"


@pytest.mark.parametrize("payload", ["a'b", 'q"q', "", 3, -2.5, True, None, b"\x00"])
def test_a_literal_survives_the_world_exactly(payload):
    """The value lives IN the world as an entity's printed name, via `repr`, so
    nothing is held in a Python map the systems cannot see."""
    f = Facts()
    assert f.payload(f.value(payload)) == payload
    assert type(f.payload(f.value(payload))) is type(payload)


def test_a_system_RE_DERIVING_what_already_holds_still_SETTLES():
    """⚠⚠ The `no <own conclusion>` premise is not load-bearing here. An engine with
    no inert set offers an application that changed nothing again, so a rule that
    did not stop itself never stopped — the whole budget burned on the first
    applicable rule while every later rule never fired."""
    f = Facts()
    n = f.node("n")
    f.fact("for_stmt", n)

    @f.system
    def restates(world):
        for subject in f.subjects("for_stmt"):
            f.fact("iteration", subject)

    settled = f.run(budget=20)
    assert settled.hot == [], "nothing was still changing when the loop stopped"
    assert settled.ticks < 20, "it settled well inside the budget, not on it"
    assert f.has("iteration", n)


def test_a_reader_sees_what_a_SYSTEM_concluded_not_only_what_a_caller_wrote():
    """⚠ A private index once saw only what `fact()` wrote, so a reader could not see
    what a RULE had concluded. It cannot recur while there is one store."""
    f = Facts()
    n = f.node("n")
    f.fact("for_stmt", n)

    @f.system
    def describe(world):
        for subject in f.subjects("for_stmt"):
            f.fact("iteration", subject)

    @f.system
    def read_it_back(world):
        for subject in f.subjects("iteration"):
            f.fact("seen", subject)

    f.run()
    assert f.has("seen", n), "the second system read the first system's conclusion"


# -- the delta contract ----------------------------------------------------------


def test_a_deny_then_a_fact_in_ONE_turn_sees_its_own_effect():
    """⚠ A repair `deny`s an operator and `fact`s its replacement in the same turn.
    The second call reads `_held`, not the world as of the turn's start, or both
    rows would stand."""
    f = Facts()
    cmp_ = f.node("cmp")
    f.fact("operator", cmp_, f.word("gt"))

    @f.system
    def repair(world):
        for subject in f.subjects("operator"):
            if f.deny("operator", subject, f.word("gt")):
                f.fact("operator", subject, f.word("ge"))

    f.run()
    assert [f.show(o) for (o,) in f.of("operator", cmp_)] == ["ge"]


def test_a_word_MINTED_inside_a_system_is_found_again_by_a_LATER_turn():
    """⭐ `word()` inside a system DESCRIBES an entity; that description resolves
    only within its own turn, so a later turn needing the same text has to find what
    an earlier one already made real. Two entities for `ge` would not join."""
    f = Facts()
    for name in ("a", "b"):
        f.fact("cmp", f.node(name))

    @f.system
    def mint(world):
        for subject in f.subjects("cmp"):
            if not f.has("operator", subject):
                f.fact("operator", subject, f.word("ge"))

    f.run()
    made = {o for subject in f.subjects("cmp") for (o,) in f.of("operator", subject)}
    assert len(made) == 1, "one `ge`, not one per turn"


def test_a_system_that_RAISED_is_re_raised_rather_than_settling_quietly():
    """⚠⚠ `Loop.run` records it on `loop.errors` and carries on, which is right for a
    prompt and wrong for a derivation: the world settles LOOKING quiescent while the
    conclusion the rule owed is simply absent."""
    f = Facts()

    @f.system
    def broken(world):
        raise ValueError("no")

    with pytest.raises(Exception):
        f.run()


# -- surviving a restart ---------------------------------------------------------
#
# ⚠⚠ The twin trap has a door here that nothing could reach until relations
# became savable: interning lived in `_words`/`_values`, Python dicts beside
# the world, and a dict beside the world does not come back from a file.


def test_a_restored_WORD_is_the_same_entity_the_restored_facts_POINT_AT():
    """⚠⚠ Two `Printed("loop")` entities, a fact pointing at one and every later
    rule asking for the other, is a run that settles having matched nothing."""
    from ugm import save
    from ugm.world import World

    f = Facts()
    n = f.node("n")
    f.fact("name", n, f.word("loop"))

    g = Facts()
    assert save.load(g.world, save.dump(f.world)) == []
    (pointed_at,), = g.of("name", g.world._adopt(n.id))
    assert g.word("loop") == pointed_at
    assert len([e for e, _ in g.world.each(Printed) if _.text == "loop"]) == 1


def test_a_restored_VALUE_interns_the_same_way():
    from ugm import save

    f = Facts()
    n = f.node("n")
    f.fact("threshold", n, f.value(18))

    g = Facts()
    assert save.load(g.world, save.dump(f.world)) == []
    (pointed_at,), = g.of("threshold", g.world._adopt(n.id))
    assert g.value(18) == pointed_at
    assert g.payload(pointed_at) == 18


def test_an_OCCURRENCE_does_not_start_interning_just_because_it_was_saved():
    """⭐ The whole distinction: a `node` carries no `Interned`, so two `gt`s in
    two functions stay two entities across a restart, exactly as they were."""
    from ugm import save

    f = Facts()
    first, second = f.node("gt"), f.node("gt")
    f.fact("occurrence", first)
    f.fact("occurrence", second)

    g = Facts()
    assert save.load(g.world, save.dump(f.world)) == []
    assert len(g.subjects("occurrence")) == 2, "still two"
    assert g.node("gt") != g.node("gt"), "and a new one is a third"


def test_known_SEES_a_restored_word_and_still_mints_nothing():
    """⚠ `known` is the one read that must not spawn. Adoption only moves what
    the world already holds, so it can read a restored vocabulary and keep that."""
    from ugm import save

    f = Facts()
    f.fact("vocabulary", f.node("v"), f.word("premium"))

    g = Facts()
    assert save.load(g.world, save.dump(f.world)) == []
    before = len(g.world)
    assert g.known("premium") is not None, "a word a previous process interned"
    assert g.known("never_seen") is None, "and still None for one nobody has"
    assert len(g.world) == before, "having spawned nothing either way"


def test_a_word_MINTED_INSIDE_A_SYSTEM_is_marked_too():
    """⚠ The mid-turn path describes a `spawn` and returns a `Pending`; the
    `Interned` mark has to be described alongside it or a word a RULE invented
    comes back from a file as an anonymous occurrence."""
    from ugm import save

    f = Facts()
    f.fact("cmp", f.node("c"))

    @f.system
    def repair(world):
        for subject in f.subjects("cmp"):
            if not f.has("operator", subject):
                f.fact("operator", subject, f.word("ge"))

    f.run()
    g = Facts()
    assert save.load(g.world, save.dump(f.world)) == []
    (pointed_at,), = g.of("operator", g.subjects("cmp")[0])
    assert g.word("ge") == pointed_at


def test_the_round_trip_is_STABLE_so_a_second_restart_is_not_a_third_entity():
    from ugm import save

    f = Facts()
    f.fact("name", f.node("n"), f.word("loop"))
    once = save.dump(f.world)

    g = Facts()
    save.load(g.world, once)
    g.word("loop")                      # adopt, then ask again
    twice = save.dump(g.world)
    assert twice == once, "the same world, not one that grew a twin on the way"
