"""
FRONTIER probes — object-scoped deontic + specific-card values, exploring the engine's limits.

These push past the class-level card-trader demo (abstract `have_rare_card`, action-class norms)
onto two harder frontiers, and pin what is now SHIPPED vs. where the remaining plumbing is:

  1. VALUE -> PLAN bridge — reasoning DERIVES a planning effect, so a value-based goal
     (`have_valuable`) picks the valuable card. `?o add have_valuable when ?o acts_on ?c and ?c is
     valuable` extends an operator's effects from a derived property.
  2. OBJECT-SCOPED deontic — a norm scoped by a PROPERTY of the acted-on object. The SURFACE
     (`don't sell rare cards` -> `sell forbidden_for rare`) is now a real, lexicon-generated form in
     `deontic.py`, and the exclusion rule (variable-property join `?card is ?prop`) ships in
     `corpus/policy.cnl` — so both are exercised here through the REAL loaders.

STILL THE FRONTIER (NOT engine gaps):
  - the object-scoped norm is SOURCE-LESS (`forbidden_for` drops the authority; see
    `deontic.OBJECT_SCOPE_SUFFIX`), so it does NOT yet compose with the priority/override machinery.
  - naive single-adjective NP: `do not sell <adj> cards` takes the middle word as the property.
  - the planner re-derives already-satisfied subgoals (a stray redundant `buy_*` may appear).

The specific-card KB is now fully CNL (`corpus/cards_frontier_kb.cnl`, loaded by `load_cards_kb` —
`acts_on` folds through the planning loader), so nothing is Python-seeded here.
"""
import pathlib

import ugm
import harneskills as h
from ugm.cnl.authoring import load_rules
from harneskills.deontic import load_deontic
from harneskills.scenarios import POLICY_RULES, chosen_operators, load_cards_kb

_FRONTIER_KB = (pathlib.Path(__file__).resolve().parent.parent / "corpus" / "cards_frontier_kb.cnl"
                ).read_text(encoding="utf-8")

# value reasoning + the value->plan bridge (prose domain rules); the object-scoped EXCLUSION rule
# now ships in POLICY_RULES (corpus/policy.cnl), so the bank is bridge + the real policy machinery.
_BRIDGE = load_rules("""
?c is valuable when ?c is rare and ?c is in_demand
?o add have_valuable when ?o acts_on ?c and ?c is valuable
""")
_RULES = _BRIDGE + POLICY_RULES


def _marks(g: ugm.Graph, pred: str) -> set[str]:
    return {g.name(n) for n in g.nodes() for r, _ in g.relations_from(n) if g.name(r) == pred}


def _has_norm(g: ugm.Graph, polarity: str, action: str, scope: str) -> bool:
    """A reified object-scoped norm node with the given polarity/action/scope relations."""
    for n in g.nodes():
        rels = {(g.name(r), g.name(o)) for r, o in g.relations_from(n)}
        if {("polarity", polarity), ("action", action), ("scope", scope)} <= rels:
            return True
    return False


def _build() -> ugm.Graph:
    """The specific-card sub-domain, loaded entirely from CNL (operators over named cards +
    `acts_on` links + classes + an object-scoped norm + card facts)."""
    return load_cards_kb(_FRONTIER_KB)


# --- probe 1: value -> plan --------------------------------------------------------------

def test_value_reasoning_drives_a_value_based_goal():
    # reasoning derives `buy_charizard add have_valuable` (charizard is valuable) -> the goal
    # `have_valuable` picks buy_charizard, never buy_blastoise (blastoise is common).
    g = _build()
    h.seed_state(g, [])
    h.seed_goal(g, "have_valuable")
    assert h.solve(g, extra_rules=_RULES) == "done"
    assert "buy_charizard" in chosen_operators(g)
    assert "buy_blastoise" not in chosen_operators(g)


# --- probe 2/3: object-scoped norm, from the real surface through the real machinery ------

def test_object_scoped_surface_folds_and_reifies():
    # the lexicon-generated object-scoped form (deontic.py) folds `don't sell rare cards` and the
    # transfer REIFIES it into a norm node carrying polarity/action/scope (+ source).
    g = load_deontic(ugm.Graph(), "don't sell rare cards")
    assert _has_norm(g, "forbidden", "sell", "rare")


def test_new_phrasing_gives_object_scoped_for_free():
    # a NEWLY declared phrasing yields the object-scoped frame too, with no code change — the proof
    # the object-scoped form is lexicon-generated, not hardcoded.
    g = load_deontic(ugm.Graph(), "avoid means forbidden\navoid selling risky cards")
    assert _has_norm(g, "forbidden", "selling", "risky")


def test_object_scoped_norm_excludes_by_the_objects_property():
    # the KB's `don't sell rare cards` (real surface, folded on load) + the policy.cnl exclusion
    # (real machinery): the rare card is unsellable, the common one raises the cash.
    g = _build()                                           # norm already in the KB
    h.seed_state(g, ["have_charizard", "have_blastoise"])
    h.seed_goal(g, "have_cash")
    assert h.solve(g, extra_rules=_RULES) == "done"
    assert "sell_charizard" in _marks(g, "excluded")       # rare -> forbidden to sell
    assert "sell_blastoise" not in _marks(g, "excluded")   # common -> sellable
    assert "sell_blastoise" in chosen_operators(g)          # cash raised by selling the common card


def test_object_scoped_norm_is_overridable():
    # the reified norm carries a SOURCE, so it composes with the override: today's outranking
    # encouragement to sell rares defeats the standing `don't sell rare cards` -> the rare card
    # becomes sellable today (the same defeasible-priority idiom as the class-level norms).
    g = _build()                                           # standing `don't sell rare cards`
    load_deontic(g, "today it is good to sell rare cards\ntoday outranks standing")
    h.seed_state(g, ["have_charizard", "have_blastoise"])
    h.seed_goal(g, "have_cash")
    assert h.solve(g, extra_rules=_RULES) == "done"
    assert "sell_charizard" not in _marks(g, "excluded")   # override lifted the rare-card ban today
    assert "sell_charizard" in chosen_operators(g)
