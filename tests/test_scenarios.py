"""
The card-trader scenario harness over the real KB + scenario files — the end-to-end demo as a
test. One persistent KB (`corpus/cards_kb.cnl`), five transient days (`corpus/cards_scenarios.txt`),
each driving the SAME operators to a different decision under a different deontic policy.
"""
import pathlib

from harneskills.scenarios import (
    load_cards_kb, parse_scenarios, run_scenario, run_scenarios,
)

_CORPUS = pathlib.Path(__file__).resolve().parent.parent / "corpus"
_KB = (_CORPUS / "cards_kb.cnl").read_text(encoding="utf-8")
_SCN = (_CORPUS / "cards_scenarios.txt").read_text(encoding="utf-8")


def test_all_authored_scenarios_pass():
    results = run_scenarios(_KB, _SCN)
    assert len(results) == 13
    bad = [f"{r.scenario.name}: {r.failures}" for r in results if not r.ok]
    assert not bad, "failing scenarios: " + "; ".join(bad)


def test_standing_law_norm_excludes_counterfeit_by_default():
    # Even with no policy, the KB's `law never counterfeit` keeps the counterfeit operator out.
    g = load_cards_kb(_KB)
    from harneskills.scenarios import POLICY_RULES, chosen_operators
    import harneskills as h
    h.seed_goal(g, "have_rare_card")
    assert h.solve(g, extra_rules=POLICY_RULES) == "done"
    assert "counterfeit_card" not in chosen_operators(g)


def test_scenario_parse_shapes():
    scns = {s.name: s for s in parse_scenarios(_SCN)}
    assert set(scns) == {"acquire_default", "cautious_no_buying", "hold_the_line",
                         "sell_today", "law_holds", "play_it_safe", "relaxed_day",
                         "cautious_and_lawful", "prefer_encouraged", "demote_discouraged",
                         "discouraged_is_last_resort", "hot_market", "cold_market"}
    assert scns["hold_the_line"].outcome == "stuck"
    assert scns["cautious_no_buying"].not_chosen == ["buy_online"]
    assert scns["sell_today"].policy == ["today it is good to sell"]


def test_graded_risk_cut_is_tuned_by_the_caution_mood():
    # Same KB, same goal; only the caution level changes the α-cut — a somewhat-risky operator
    # (buy_online, 0.5) is cut at `medium` but survives at `low`. The safe shop survives both.
    scns = {s.name: s for s in parse_scenarios(_SCN)}
    medium = run_scenario(_KB, scns["play_it_safe"])
    low = run_scenario(_KB, scns["relaxed_day"])
    assert "buy_online" not in medium.got_chosen and "buy_at_shop" in medium.got_chosen
    assert "buy_online" in low.got_chosen
    # the very-risky trade is out at both levels
    assert "trade_at_club" not in medium.got_chosen and "trade_at_club" not in low.got_chosen


def test_deontic_ranking_demotes_without_excluding():
    # `better not to buy` DISCOURAGES (ranks below neutral) rather than forbids: the buys lose to
    # the neutral trade, but stay candidates — so when trade is also forbidden, a buy is still
    # chosen. This is the discrete-tier ranking (no calculator), distinct from prohibition.
    scns = {s.name: s for s in parse_scenarios(_SCN)}
    demote = run_scenario(_KB, scns["demote_discouraged"])
    assert demote.got_chosen == {"trade_at_club"}                 # neutral trade beats discouraged buys
    last = run_scenario(_KB, scns["discouraged_is_last_resort"])
    assert last.got_outcome == "done" and "buy_at_shop" in last.got_chosen  # discouraged still used


def test_encouraged_means_is_preferred():
    scns = {s.name: s for s in parse_scenarios(_SCN)}
    r = run_scenario(_KB, scns["prefer_encouraged"])
    assert r.got_chosen == {"trade_at_club"}                      # encouraged beats the neutral buys


def test_same_kb_diverges_by_policy():
    # The headline: identical KB, opposite outcomes for `have_cash` driven only by the transient
    # policy — `hold_the_line` (no override) is stuck; `sell_today` (override) reaches it.
    scns = {s.name: s for s in parse_scenarios(_SCN)}
    assert run_scenario(_KB, scns["hold_the_line"]).got_outcome == "stuck"
    assert run_scenario(_KB, scns["sell_today"]).got_outcome == "done"
