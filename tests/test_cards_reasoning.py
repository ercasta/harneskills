"""
The card-trader's DEDUCTIVE business-semantics half — value reasoning (with a why-trace) and
reasoning that DERIVES the trading policy (a hot market -> selling encouraged -> overrides the
standing "don't sell"). The deductive face of the substrate applied to business content, and its
bridge into the planning/policy layer.
"""
import pathlib

import harneskills as h
from harneskills.authoring import load_corpus
from harneskills.query import ask
from harneskills.scenarios import (
    SOLVE_POLICY, chosen_operators, load_cards_kb, _transfer_facts, parse_scenarios, run_scenario,
)

_CORPUS = pathlib.Path(__file__).resolve().parent.parent / "corpus"
_KB = (_CORPUS / "cards_kb.cnl").read_text(encoding="utf-8")
_SCN = (_CORPUS / "cards_scenarios.txt").read_text(encoding="utf-8")
_REASONING = (_CORPUS / "cards_reasoning.cnl").read_text(encoding="utf-8")


# --- deductive card value, multi-step, with provenance --------------------------------------

def _value_kb():
    g, rules = load_corpus(_REASONING + """
        charizard is rare
        charizard is in_demand
        charizard is mint
        blastoise is rare
        pikachu is in_demand
    """)
    journal = h.run_rules(g, rules)
    return g, rules, journal


def test_card_value_is_deduced():
    g, rules, journal = _value_kb()
    assert ask(g, "who is valuable", journal=journal, rules=rules) == ["charizard is valuable"]
    # blastoise is rare but not in demand; pikachu in demand but common -> neither valuable
    assert ask(g, "is blastoise valuable", journal=journal, rules=rules) == ["no"]
    assert ask(g, "is pikachu valuable", journal=journal, rules=rules) == ["no"]


def test_value_composes_three_steps():
    g, rules, journal = _value_kb()
    # rare + in_demand -> valuable; + mint -> premium; -> worth_holding
    assert ask(g, "who is worth_holding", journal=journal, rules=rules) == ["charizard is worth_holding"]


def test_why_trace_walks_the_derivation():
    g, rules, journal = _value_kb()
    why = "\n".join(ask(g, "why charizard is worth_holding", journal=journal, rules=rules))
    # the trace runs worth_holding <- premium <- (mint + valuable <- rare + in_demand)
    for step in ("worth_holding", "premium", "valuable", "rare", "in_demand", "mint"):
        assert step in why, f"missing '{step}' in why-trace:\n{why}"


# --- reasoning DERIVES the policy — a hot market overrides the standing don't-sell -----------

def test_hot_market_reasons_its_way_to_selling():
    scns = {s.name: s for s in parse_scenarios(_SCN)}
    hot = run_scenario(_KB, scns["hot_market"])
    cold = run_scenario(_KB, scns["cold_market"])
    # hot: derives `sell encouraged today` -> overrides `don't sell` -> cash reached
    assert hot.got_outcome == "done" and "sell_rare" in hot.got_chosen
    # cold: the reasoned stance never fires, the standing norm holds -> honest stuck
    assert cold.got_outcome == "stuck"


def test_no_explicit_sell_instruction_in_the_hot_market_scenario():
    # the point: the sell stance is REASONED, not asserted. The scenario names only market facts.
    scns = {s.name: s for s in parse_scenarios(_SCN)}
    assert scns["hot_market"].policy == ["demand is high", "supply is low"]


def test_the_derived_override_is_visible_in_the_graph():
    g = load_cards_kb(_KB)
    _transfer_facts(g, "demand is high\nsupply is low")
    h.seed_goal(g, "have_cash")
    h.solve(g, extra_rules=SOLVE_POLICY)
    def _marks(pred):
        return {g.name(n) for n in g.nodes()
                for r, _ in g.relations_from(n) if g.name(r) == pred}
    assert "market" in {g.name(n) for n in g.nodes()}          # market node exists
    assert "sell" in _marks("overridden")                      # the derived encouragement overrode
