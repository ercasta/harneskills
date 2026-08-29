"""A small prototype of `docs/decision_patterns.md`: propose, justify,
arbitrate, over one generic reader — plus a judge that needs information
unblocking without any goal-management code at all.
"""
from __future__ import annotations

import pytest

# ⚠⚠ ON HOLD, not deleted: `arbitration.py` sits on `ugm.facts`, which does
# not currently import. See `docs/overview.md` and `ugm/__init__.py`'s own note.
pytest.importorskip("ugm.facts", exc_type=ImportError)
from ugm import arbitration
from ugm.facts import Facts, relation


def load(only=None):
    return Facts(lambda loop, f: arbitration.install(loop, f, only=only))


def rank(f: Facts, occasion, option, score):
    f.fact("ranked", occasion, option, f.value(score))


# -- candidate / rank / winner ---------------------------------------------------


def test_pizza_beats_ice_cream_on_preference_alone():
    f = load()
    dessert = f.node("dessert")
    pizza, ice_cream, nothing = f.word("pizza"), f.word("ice_cream"), f.word("nothing")
    for option in (pizza, ice_cream, nothing):
        f.fact("candidate", dessert, option)
    rank(f, dessert, pizza, 2)
    rank(f, dessert, ice_cream, 1)
    f.run()
    assert f.text("verdict", dessert) == "forced"
    assert f.show(f.one("winner", dessert)) == "pizza"


def test_a_tie_in_rank_is_ambiguous_not_guessed():
    f = load()
    occasion = f.node("choice")
    a, b = f.word("a"), f.word("b")
    f.fact("candidate", occasion, a)
    f.fact("candidate", occasion, b)
    rank(f, occasion, a, 1)
    rank(f, occasion, b, 1)
    f.run()
    assert f.text("verdict", occasion) == "ambiguous"
    assert f.of("winner", occasion) == []


def test_everything_ruled_out_is_unresolved_not_a_guess():
    f = load()
    occasion = f.node("choice")
    a = f.word("a")
    f.fact("candidate", occasion, a)

    def veto(world):
        for occ, held in world.each(relation("candidate")):
            for (option,) in [r for r in held.rows if len(r) == 1]:
                f.fact("ruled_out", occ, option, f.word("no_reason_given"))

    f.rule(veto, name="veto")
    f.run()
    assert f.text("verdict", occasion) == "unresolved"
    assert f.of("winner", occasion) == []


# -- realizes, and the chain a judge reasons over --------------------------------


def test_realizes_is_transitive_so_a_judge_reasons_at_a_distance():
    f = Facts(lambda loop, ff: arbitration.install(loop, ff, only={"realizes_closure"}))
    pizza = f.word("pizza")
    f.fact("realizes", pizza, f.word("deep_dish"))
    f.fact("realizes", f.word("deep_dish"), f.word("junk_food"))
    f.run()
    assert f.holds("realizes", pizza, f.word("junk_food"))


def test_a_hard_veto_dominates_the_soft_preference_it_already_won_on():
    """'pizza or nothing? you're on a diet, so nothing' — the diet judge is
    authored purely against `junk_food`, two hops from `pizza` through
    `deep_dish` it never names, and it wins over a preference ranking that
    already had pizza in first place: elimination is checked before
    ranking is ever consulted.
    """
    f = load()
    dessert = f.node("dessert")
    pizza, ice_cream, nothing = f.word("pizza"), f.word("ice_cream"), f.word("nothing")
    for option in (pizza, ice_cream, nothing):
        f.fact("candidate", dessert, option)
    rank(f, dessert, pizza, 2)
    rank(f, dessert, ice_cream, 1)
    f.fact("realizes", pizza, f.word("deep_dish"))
    f.fact("realizes", f.word("deep_dish"), f.word("junk_food"))
    f.fact("realizes", ice_cream, f.word("junk_food"))

    def diet(world):
        for occasion, held in world.each(relation("candidate")):
            for (option,) in [r for r in held.rows if len(r) == 1]:
                if f.holds("realizes", option, f.word("junk_food")):
                    f.fact("ruled_out", occasion, option, f.word("dieting"))

    f.rule(diet, name="diet")
    f.run()
    assert f.text("verdict", dessert) == "forced"
    assert f.show(f.one("winner", dessert)) == "nothing"


# -- a judge that needs information, unblocking with no goal machinery -----------


def test_a_judge_that_needs_information_unblocks_without_any_goal_machinery():
    """Two rules, each oblivious to the other. `judge` cannot rule until
    it knows a price, so it asserts `needs` instead of guessing —
    `docs/decision_patterns.md`'s claim, made runnable: `needs` is an
    ordinary fact, satisfied by whoever happens to make it true, with no
    call from one rule into the other and nothing suspended in between.
    """
    f = Facts()
    lunch = f.node("lunch")
    pizza = f.node("pizza")
    f.fact("on_menu", lunch, pizza)

    def judge(world):
        for occasion, held in world.each(relation("on_menu")):
            for (item,) in [r for r in held.rows if len(r) == 1]:
                price = f.one("price", item)
                if price is None:
                    f.fact("needs", occasion, f.word("price"), item)
                    continue
                if f.payload(price) <= 10:
                    f.fact("affordable", occasion, item)

    def unrelated_pricer(world):
        # Knows nothing about `judge`, `on_menu`, or occasions in general —
        # it prices whatever anyone asked the price of.
        for occasion, held in world.each(relation("needs")):
            for row in held.rows:
                if len(row) != 2 or f.show(row[0]) != "price":
                    continue
                item = row[1]
                if f.one("price", item) is None:
                    f.fact("price", item, f.value(7))

    f.rule(judge, name="judge")
    f.rule(unrelated_pricer, name="pricer")
    f.run()

    assert f.holds("affordable", lunch, pizza)
    # ⚠ Read back STRUCTURALLY, not by calling `f.word("price")` again: that
    # text was only ever minted mid-turn (inside `judge`), so it was never
    # cached in `_words` and a call from out here would mint a SECOND,
    # different "price" -- the same discipline `_find`/`known()` document,
    # extended past a single turn to reading back after the run entirely.
    needed = f.of("needs", lunch)
    assert len(needed) == 1  # the request stays on the record, unconsumed
    assert f.show(needed[0][0]) == "price" and needed[0][1] == pizza
