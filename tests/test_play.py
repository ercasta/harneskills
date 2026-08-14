"""Playing a scenario: the cue mechanism, and the dungeon on top of it.

The check that matters is `test_the_player_actually_decides_the_fight`. Everything
else here could pass while the person at the keyboard was a spectator — the fight
runs itself perfectly well, because the corpus has a standing policy for a hero
whose player has said nothing. Only comparing two fights that differ *solely* in
what was declared can tell a player apart from an audience.
"""

from __future__ import annotations

import pytest

import harneskills as h
from harneskills import dungeon, play
from harneskills.dungeon import corpus_path

pytestmark = pytest.mark.skipif(
    corpus_path() is None,
    reason="this ugm build has no rules/dungeon.ugm",
)

LIMIT = 6000


def start(seed=7):
    scenario = play.find("dungeon")
    r = h.Runner(limit=LIMIT)
    scenario.setup(r, seed)
    r.scenario = scenario
    return r, scenario


def auto(r, scenario, reply_for=lambda ctx, opts: (opts[0] if opts else "")):
    """Play a whole fight, answering every cue with `reply_for`."""
    said = []
    for _ in range(LIMIT):
        if scenario.over(r):
            break
        found = play.pending(r)
        if found is not None:
            cue, ctx = found
            got = play.speak(r, cue, ctx, reply_for(ctx, cue.options(r, ctx)))
            said.append(got)
            continue
        step = r.step()
        if step.state in ("quiescent", "stopped"):
            break
    return said


def always(target):
    return lambda ctx, opts: target


# -- the mechanism ----------------------------------------------------------


def test_the_dungeon_registers_itself():
    assert "dungeon" in {s.name for s in play.available()}
    assert play.find("dungeon") is not None
    assert play.find("nonesuch") is None


def test_loading_does_not_think():
    r, scenario = start()
    assert r.steps == []
    assert scenario.over(r) is None
    assert "round 1 -- hero to act" in scenario.status(r)[0]


def test_the_fight_asks_before_it_swings():
    r, scenario = start()
    found = play.pending(r)
    assert found is not None
    cue, ctx = found
    assert ctx["round"] == "1"
    assert set(cue.options(r, ctx)) == {"attack(goblin1)", "attack(goblin2)"}


def test_a_fight_finishes_and_says_how():
    r, scenario = start(seed=1)
    auto(r, scenario)
    assert scenario.over(r) in ("hero_wins", "hero_falls")


def test_the_hero_can_win():
    """A game nobody can win is a demo, not a game."""
    r, scenario = start(seed=1)
    auto(r, scenario)
    assert scenario.over(r) == "hero_wins"


# -- the one that can see a player ------------------------------------------


def test_the_player_actually_decides_the_fight():
    """⭐ Two fights, same seed, differing only in what was declared. If the
    declarations were being ignored — arriving too late to beat the standing
    policy, say — both would kill the same goblin and this is the only check
    here that would notice."""
    r1, s1 = start(seed=7)
    auto(r1, s1, always("attack(goblin1)"))
    r2, s2 = start(seed=7)
    auto(r2, s2, always("attack(goblin2)"))

    assert dungeon.hp_of(r1, "goblin1") == "0", "declaring goblin1 should kill goblin1"
    assert dungeon.hp_of(r1, "goblin2") == "5", "...and leave goblin2 untouched"
    assert dungeon.hp_of(r2, "goblin2") == "0", "declaring goblin2 should kill goblin2"
    assert dungeon.hp_of(r2, "goblin1") == "5", "...and leave goblin1 untouched"


def test_a_bare_monster_name_is_accepted_as_an_attack():
    r, scenario = start(seed=1)
    said = auto(r, scenario, always("goblin1"))
    assert said and said[0] == "declares(attack(goblin1), 1)"


# -- declining, which must not hang -----------------------------------------


def test_declining_is_recorded_and_the_fight_moves_on():
    """⚠⚠⚠ The regression that hung the REPL. A cue fires on a state; if a
    decline changed nothing, the state would still be there on the next check
    and the same question would be asked for ever."""
    r, scenario = start(seed=1)
    said = auto(r, scenario, always(""))
    assert said and said[0] == "passes(1)"
    assert scenario.over(r) is not None, "the fight must still finish"


def test_an_unparseable_reply_is_a_decline_not_a_crash():
    r, scenario = start(seed=1)
    said = auto(r, scenario, always("run away!!"))
    assert said and said[0].startswith("passes(")
    assert scenario.over(r) is not None


def test_declining_lets_the_corpus_standing_policy_act():
    """`passes` is vocabulary the corpus has never heard of, so nothing follows
    from it and `<hero-holds>` takes the turn. The hero still swings."""
    r, scenario = start(seed=1)
    auto(r, scenario, always(""))
    hurt = [w for w in ("goblin1", "goblin2") if dungeon.hp_of(r, w) != "5"]
    assert hurt, "the hero should have swung on policy"


# -- the cue stops when the fight does ---------------------------------------


def test_no_cue_once_it_is_over():
    r, scenario = start(seed=1)
    auto(r, scenario)
    assert scenario.over(r) is not None
    assert play.pending(r) is None


def test_a_cue_needs_a_scenario():
    assert play.pending(h.Runner()) is None


# -- reproducibility ---------------------------------------------------------


def test_a_seeded_fight_replays_identically():
    outcomes = []
    for _ in range(2):
        r, scenario = start(seed=3)
        auto(r, scenario, always("attack(goblin1)"))
        outcomes.append((scenario.over(r),
                         dungeon.hp_of(r, "hero"),
                         dungeon.hp_of(r, "goblin1"),
                         dungeon.hp_of(r, "goblin2")))
    assert outcomes[0] == outcomes[1]


def test_the_seed_is_on_the_record():
    r, _ = start(seed=7)
    assert r.holds("seeded(<dice>, 7)", scope="dungeon") == "+"


# -- provenance reaches the dice ---------------------------------------------


def test_why_walks_back_through_the_roll_that_did_it():
    """A tool proposes and a rule concludes, so the roll is on the trail like
    any other premise — which is the whole reason the dice are an answerer.

    ⚠ Asked of the hit points rather than of `dead(...)`, because a goblin on its
    last point flees instead of dying: at seed 1 both of them run and nothing in
    the fight is ever dead. Damage is the thing that always happens.
    """
    r, scenario = start(seed=1)
    auto(r, scenario, always("attack(goblin1)"))
    hp = dungeon.hp_of(r, "goblin1")
    assert hp is not None and hp != "5", "goblin1 should have been hurt"
    trail = "\n".join(r.why(f"hp(goblin1, {hp})", scope="dungeon"))
    assert "answered" in trail and "dice" in trail
