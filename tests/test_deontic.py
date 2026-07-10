"""
Deontic policy surface + defeasible-priority OVERRIDE, tested standalone (no planner yet).

The card-trader domain's transient-policy layer: prohibition / encouragement / discouragement
over action classes, authored in plain deontic English (`harneskills/deontic.py`), resolved by
the generic machinery `corpus/policy.cnl`. These tests pin the two behaviours the design turns
on: a transient `today` advice OVERRIDING a contradictory standing norm, and a `law`-sourced
norm REFUSING to be overridden — both as rule reasoning over the shared graph.
"""
import pathlib

import harneskills as h
from harneskills.deontic import (
    load_deontic, _normalize_deontic, parse_deontic_lexicon, _DEFAULT_LEXICON,
)
from harneskills.machine_rules import load_machine_rules

_POLICY = load_machine_rules(
    (pathlib.Path(__file__).resolve().parent.parent / "corpus" / "policy.cnl")
    .read_text(encoding="utf-8"))


def _marks(g: h.Graph, pred: str) -> set[str]:
    """Subjects `s` with an `s --pred--> _` relation (read straight off `relations_from`)."""
    return {g.name(n) for n in g.nodes()
            for r, _ in g.relations_from(n) if g.name(r) == pred}


def _rel(g: h.Graph, s: str, p: str, o: str) -> bool:
    return any(g.name(rn) == p and g.name(on) == o
              for n in g.nodes_named(s) for rn, on in g.relations_from(n))


# --- the surface parses to the intended deontic facts ------------------------------------

def test_deontic_surface_folds_to_facts_with_source():
    g = load_deontic(h.Graph(), """
        don't buy
        it is good to trade
        better not to sell
        today it is good to buy
    """)
    assert _rel(g, "buy", "forbidden", "standing")      # `don't buy` -> standing prohibition
    assert _rel(g, "trade", "encouraged", "standing")   # `it is good to trade`
    assert _rel(g, "sell", "discouraged", "standing")   # `better not to sell`
    assert _rel(g, "buy", "encouraged", "today")        # leading `today` -> the today source


def test_contraction_normalization():
    assert _normalize_deontic("don't sell") == "do not sell"
    assert _normalize_deontic("today it's good to buy") == "today it is good to buy"


# --- the lexicon is DATA: a new phrasing works with NO code change ------------------------

def test_default_lexicon_reads_from_data():
    # the shipped phrasings come from `DEONTIC_LEXICON_CNL` (data), read by the §8 reader.
    assert _DEFAULT_LEXICON[("do", "not")] == "forbidden"
    assert _DEFAULT_LEXICON[("it", "is", "good", "to")] == "encouraged"
    assert _DEFAULT_LEXICON[("better", "not", "to")] == "discouraged"


def test_lexicon_reader_splits_phrase_from_polarity():
    lex = parse_deontic_lexicon("steer clear of means forbidden\nfeel free to means encouraged")
    assert lex[("steer", "clear", "of")] == "forbidden"
    assert lex[("feel", "free", "to")] == "encouraged"


def test_newly_declared_phrasing_folds_with_no_code_change():
    # Author a NEW multi-word deontic phrasing inline (`steer clear of`) and use it in the same
    # KB. It must fold exactly like a built-in phrasing — the proof the lexicon is data, not
    # hardwired forms. A leading source word still applies to the new frame, too.
    g = load_deontic(h.Graph(), """
        steer clear of means forbidden
        steer clear of buy
        today steer clear of sell
    """)
    assert _rel(g, "buy", "forbidden", "standing")
    assert _rel(g, "sell", "forbidden", "today")


def test_new_phrasing_drives_exclusion_end_to_end():
    # the declared phrasing flows all the way to operator exclusion via the SAME machinery.
    g = load_deontic(h.Graph(), """
        avoid means forbidden
        buy_online is a buy
        avoid buy
    """)
    h.run_rules(g, _POLICY, provenance=False)
    assert _marks(g, "excluded") == {"buy_online"}


def test_outranks_line_keeps_its_leading_source_word():
    # `today outranks standing` must NOT lose its `today` to source-stripping (it is a priority
    # fact, not a today-sourced advice). Regression for the source-detection guard.
    g = load_deontic(h.Graph(), "today outranks standing")
    assert _rel(g, "today", "outranks", "standing")


# --- prohibition excludes an action class's operators ------------------------------------

def test_plain_prohibition_excludes_operators():
    g = load_deontic(h.Graph(), """
        buy_at_shop is a buy
        buy_online is a buy
        don't buy
    """)
    h.run_rules(g, _POLICY, provenance=False)
    assert _marks(g, "excluded") == {"buy_at_shop", "buy_online"}  # both buy-operators ruled out
    assert _marks(g, "overridden") == set()                        # nothing overrides it


# --- the two headline behaviours ---------------------------------------------------------

def test_today_advice_overrides_standing_prohibition():
    # standing "don't sell" vs today "it's good to sell"; today outranks standing -> sell is
    # overridden, so its operator is NOT excluded (selling is back on the table today).
    g = load_deontic(h.Graph(), """
        dump_singles is a sell
        don't sell
        today it is good to sell
        today outranks standing
    """)
    h.run_rules(g, _POLICY, provenance=False)
    assert "sell" in _marks(g, "overridden")
    assert _marks(g, "excluded") == set()


def test_inviolable_law_refuses_to_be_overridden():
    # a law-sourced prohibition that only `today outranks standing` covers is NOT overridden by a
    # today encouragement -> its operator stays excluded (the goal would go honestly `stuck`).
    g = load_deontic(h.Graph(), """
        launder_money is a launder
        law never launder
        today it is good to launder
        today outranks standing
    """)
    h.run_rules(g, _POLICY, provenance=False)
    assert _marks(g, "overridden") == set()
    assert _marks(g, "excluded") == {"launder_money"}


def _chosen(g: h.Graph) -> set[str]:
    return _marks(g, "chosen")


def _cards_problem(deontic: str) -> h.Graph:
    """Two operators reaching one goal (`have_card`) — buy at the shop or trade with a stranger —
    plus whatever deontic policy `deontic` declares. The planner runs with the policy bank."""
    g = h.Graph()
    h.seed_operator(g, "buy_at_shop", add=["have_card"])
    h.seed_operator(g, "trade_stranger", add=["have_card"])
    h.seed_state(g, [])
    h.seed_goal(g, "have_card")
    load_deontic(g, deontic)
    return g


def test_prohibition_removes_operator_from_the_plan():
    # `don't buy` excludes buy_at_shop -> the planner reaches the goal via trade_stranger instead.
    g = _cards_problem("buy_at_shop is a buy\ntrade_stranger is a trade\ndon't buy")
    assert h.solve(g, extra_rules=_POLICY) == "done"
    assert _chosen(g) == {"trade_stranger"}


def test_prohibition_can_make_the_goal_honestly_stuck():
    # when the ONLY operator reaching the goal is forbidden, the run ends `stuck` with nothing
    # chosen — a real, auditable outcome (not a silent workaround).
    g = h.Graph()
    h.seed_operator(g, "buy_at_shop", add=["have_card"])
    h.seed_state(g, [])
    h.seed_goal(g, "have_card")
    load_deontic(g, "buy_at_shop is a buy\ndon't buy")
    assert h.solve(g, extra_rules=_POLICY) == "stuck"
    assert _chosen(g) == set()


def test_today_override_puts_a_forbidden_operator_back_in_the_plan():
    # standing `don't trade` would exclude trade_stranger, but today's outranking encouragement
    # overrides it -> trade_stranger is a candidate again and the goal is reached.
    g = _cards_problem("""
        buy_at_shop is a buy
        trade_stranger is a trade
        don't trade
        today it is good to trade
        today outranks standing
    """)
    assert h.solve(g, extra_rules=_POLICY) == "done"
    assert "trade_stranger" in _chosen(g)


def test_law_can_be_overridden_only_when_it_is_outranked():
    # priority is authored DATA: add `emergency outranks law` + an emergency encouragement and the
    # very same law prohibition now yields — proving the refusal above is the ordering, not a
    # hardcoded special-case for `law`.
    g = load_deontic(h.Graph(), """
        launder_money is a launder
        law never launder
        emergency it is good to launder
        emergency outranks law
    """)
    h.run_rules(g, _POLICY, provenance=False)
    assert "launder" in _marks(g, "overridden")
    assert _marks(g, "excluded") == set()
