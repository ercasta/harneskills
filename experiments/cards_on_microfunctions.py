"""SLICE 0 — the decider probe. Does the card-trader domain survive onto the UGM engine?

⚠ **Re-run 2026-08-02 against `ugm` @ `2a7589b`, and the answer to its one open finding arrived.**
Upstream renamed the package `microfunctions` → `ugm`, and — in direct answer to
`docs/feedback_microfunctions.md` §3 — shipped `ugm/norm.py`. The `prohibitions()` function that was
this probe's central *negative* finding (~17 lines of arbitration in Python, and unauditable) is gone;
see `declare_norms` below for what replaced it. Everything else about the probe is unchanged.


See `docs/migration_to_microfunctions.md` §6. This is the go/no-go: it re-expresses the domain we know
cold (`corpus/cards_kb.cnl` + `corpus/cards_scenarios.txt`) on the new engine and measures TWO things:

  (a) **how much of the domain stays DATA rather than becoming Python** — the standing rule of this
      project is "domain logic ONLY in banks, never in Python", and that rule rode on the pattern
      matching the new engine deleted. Whether it survives is the actual bet under test.
  (b) **whether the answers are sensible** — under the 2026-07-10 ratification, a different-but-sensible
      answer is ratified; a nonsensical one is a bug.

Run: `python experiments/cards_on_microfunctions.py`
"""
from __future__ import annotations

from ugm import (asm, discourse as DC, driver as D, guideline as GL, intake as I, norm as N,
                 thread as T, types as TY)
from ugm.graph import Graph

# ---------------------------------------------------------------------------------------------------
# THE KB, as data. Compare `corpus/cards_kb.cnl`.
#
# ⭐ The operator surface is GONE and replaced by the signature. `buy_at_shop needs money` /
# `buy_at_shop produces have_rare_card` were two authored FACTS that a rule bank had to interpret;
# here the precondition is the parameter type and the effect is the return type, and the engine reads
# both off the stored body. Nothing interprets them.
# ---------------------------------------------------------------------------------------------------

TYPES = """
type trader:
    kind_of = "trader"

type funded_trader:
    is a trader
    money = true

type card_holder:
    is a trader
    has_rare_card = true

type cash_holder:
    is a trader
    has_cash = true
"""

OPERATORS = """
# Each trading action. The signature IS the causal knowledge.
fn buy_at_shop(t: funded_trader) -> card_holder:
    SET F(t) "has_rare_card" true

fn buy_online(t: funded_trader) -> card_holder:
    SET F(t) "has_rare_card" true

fn trade_at_club(t: trader) -> card_holder:
    SET F(t) "has_rare_card" true

fn counterfeit_card(t: trader) -> card_holder:
    SET F(t) "has_rare_card" true

fn sell_rare(t: card_holder) -> cash_holder:
    SET F(t) "has_cash" true
"""

# The action classes (`buy_at_shop is a buy`) — still data, still needed, because a norm scopes to a
# CLASS while `norm.declare` speaks about one operator. Expanding a class over its operators is the
# only thing this file still does to a norm, and it is a lookup, not a decision (see `operators_of`).
CLASSES = {"buy_at_shop": "buy", "buy_online": "buy", "trade_at_club": "trade",
           "counterfeit_card": "counterfeit", "sell_rare": "sell"}

# Risk gradings, verbatim from the KB. Degrees stay authored data, never a magic number in code.
DEGREE = {"very": 0.8, "somewhat": 0.5, "slightly": 0.3}
RISK = {"buy_online": "somewhat", "trade_at_club": "very",
        "counterfeit_card": "very", "sell_rare": "somewhat"}
CAUTION = {"high": 0.3, "medium": 0.5, "low": 0.8}   # a caution is the alpha-cut it sets

# Standing house norms: (action, source, force). `law` is inviolable — not merely top-ranked.
STANDING = [("sell", "standing", N.DEFEASIBLE),      # a default stance — today can defeat it
            ("counterfeit", "law", N.INVIOLABLE)]    # not up for discussion, whatever the day says
# Who outranks whom. A norm's source is its SPEAKER, so this is `discourse.authority` and nothing
# norm-specific. `law` appears nowhere: an inviolable norm is not up for discussion, not merely high.
OUTRANKS = [("today", "standing"), ("today", "caution")]


def operators_of(action: str) -> list[str]:
    """A norm names a class (`buy`) or an operator; the engine arbitrates per operator. Data, not logic."""
    return [op for op, cls in CLASSES.items() if cls == action or op == action]


def declare_norms(g: Graph, today: list[tuple[str, str, bool]], caution: str | None) -> None:
    """Declare the standing norms, today's instructions and the risk cut AS NORMS, and rank the sources.

    ⭐⭐ **THIS WAS THE PROBE'S CENTRAL FINDING, AND UPSTREAM CLOSED IT.** This function used to be
    `prohibitions()` — ~17 lines of genuine arbitration logic in Python, composing `never` lines before
    the goal existed, because `never` prunes absolutely and `prefer`/`avoid` only reorder. We reported
    it as `docs/feedback_microfunctions.md` §3 and offered "out of scope" as an acceptable answer.
    The answer was `ugm/norm.py`: **yes, and in data.**

    Nothing here arbitrates. It *declares* — who forbids what, on whose authority, defeasibly or not —
    and `N.apply(g, goal)` settles it and writes ordinary `never` constraints, so the planner learns no
    new concept. ⭐ And the loss that actually mattered is repaid: `N.explain(g, act)` answers *"why is
    selling not excluded?"* by naming the norm that won and the one it overrode, which the Python could
    not do at any price.
    """
    for holder, over in OUTRANKS:
        DC.authority(g, DC.speaker(g, holder), DC.speaker(g, over))

    for action, source, force in STANDING:
        for op in operators_of(action):
            N.declare(g, action=op, stance=N.FORBID, source=DC.speaker(g, source), force=force,
                      because=f"the {source} says not to {action}")

    for action, source, good in today:
        for op in operators_of(action):
            N.declare(g, action=op, stance=N.PERMIT if good else N.FORBID,
                      source=DC.speaker(g, source),
                      because=f"today {'favours' if good else 'rules out'} {action}")

    if caution:
        cut = CAUTION[caution]
        for op, grade in RISK.items():
            if DEGREE[grade] >= cut:
                # ⭐ No `not in encouraged` guard any more. A caution is a SOURCE, `today` outranks it,
                # and an encouragement defeating a risk cut is arbitration — which is no longer ours.
                N.declare(g, action=op, stance=N.FORBID, source=DC.speaker(g, "caution"),
                          because=f"{grade} risky, and caution is {caution}")


def world() -> tuple[Graph, str, str]:
    """A fresh day: the graph, the shop (the subject a search works under), and the trader."""
    g = Graph()
    for block in TYPES.strip().split("\n\n"):    # ⚠ one block per `read`, by design
        I.read(g, block)
    asm.load_text(g, OPERATORS)
    shop = g.mint("shop")
    g.link("root", "has", shop)
    me = g.mint("trader", kind_of="trader", label="me", money=True)
    g.link(shop, "trader", me)
    TY.tag(g, me, "trader")
    return g, shop, me


def scenario(name: str, want: str, *, today=(), caution=None, prefer=(), avoid=()) -> dict:
    """One transient day, exactly as `corpus/cards_scenarios.txt` frames it."""
    g, shop, me = world()
    for act in prefer:
        I.read(g, f"prefer {act}:\n    action {act}\n    because today favours it\n")
    for act in avoid:
        I.read(g, f"avoid {act}:\n    action {act}\n    because today disfavours it\n")

    goal = I.read_goal(g, f"goal {name}:\n    me.{want} = true\n")
    # ⭐ The goal carries no authored `never`. The norms are declared as data and `apply` settles them
    # into ordinary `never` constraints — arbitration before the goal, never inside the planner.
    declare_norms(g, list(today), caution)
    N.apply(g, goal)

    th = T.open_thread(g, "day")
    # ⚠ Guidelines are consulted only through `rank=`. Omit it and `prefer`/`avoid` parse, sit in the
    # graph, and silently say nothing — which cost this probe one wrong answer before it was wired.
    report = D.pursue(g, goal, th, shop, rank=GL.ranker(g))
    steps = D.plan_bindings(g, report["plan"]) if report["found"] else ()
    return {"done": bool(report["found"]),
            "chosen": tuple(fn for fn, _ in steps),
            "refused": tuple(sorted(set(fn for fn, _why in report["refused"]))),
            # ⭐ The audit `prohibitions()` could not give at any price: which norm won, and what it
            # overrode. This is §3's actual loss, repaid.
            "why": tuple(N.explain(g, op) for op in CLASSES if N.norms(g, op)),
            "report": report}


SCENARIOS = [
    # name,                      goal,             kwargs,                                   expectation
    ("acquire_default",          "has_rare_card",  {},                                       ("done",)),
    ("cautious_no_buying",       "has_rare_card",  {"today": [("buy", "today", False)]},      ("done", "not buy_online")),
    ("hold_the_line",            "has_cash",       {},                                        ("stuck",)),
    ("sell_today",               "has_cash",       {"today": [("sell", "today", True)]},      ("done", "sell_rare")),
    ("law_holds",                "has_rare_card",  {"today": [("counterfeit", "today", True)]}, ("done", "not counterfeit_card")),
    ("play_it_safe",             "has_rare_card",  {"caution": "medium"},                     ("done", "buy_at_shop")),
    ("prefer_encouraged",        "has_rare_card",  {"prefer": ["trade_at_club"]},             ("done", "trade_at_club")),
    # ⚠ THE DECISIVE CONTRAST, and the reason these two are adjacent. `buy_at_shop` is what an
    # unadvised day picks anyway, so `discouraged_is_last_resort` alone proves nothing — it would read
    # the same if advice were ignored entirely. `demote_discouraged` is the same advice with nothing
    # banned: it must move OFF the default. Then the pair says both halves — advice reorders, and
    # `avoid` still yields to necessity rather than excluding like `never` does.
    ("demote_discouraged",       "has_rare_card",  {"avoid": ["buy_at_shop", "buy_online"]},  ("done", "trade_at_club")),
    ("discouraged_is_last_resort", "has_rare_card", {"avoid": ["buy_at_shop", "buy_online"],
                                                     "today": [("trade", "today", False)]},   ("done", "buy_at_shop")),
    # ⭐ NEW 2026-08-02 (second pass, after `ugm.norm` landed). Not one of the recorded nine — it exists
    # because the behaviour it tests used to be a Python guard (`op not in encouraged`) and is now
    # arbitration the engine owns. `sell_rare` is both standing-forbidden and above the risk cut, and
    # today permits it: two forbids from two sources, defeated by one permit from a source that
    # outranks both, and `why` says so. Nothing in this file decides it.
    ("risk_cut_defeated_by_today", "has_cash",       {"today": [("sell", "today", True)],
                                                      "caution": "medium"},                   ("done", "sell_rare")),
]


def main() -> None:
    for name, want, kw, expect in SCENARIOS:
        try:
            r = scenario(name, want, **kw)
            got = "done" if r["done"] else "stuck"
            print(f"{name:32s} {got:6s} plan={r['chosen']}   expected={expect}")
            # ⚠ Always, not only on `stuck`. Several scenarios land on `buy_at_shop`, which is also what
            # an unconstrained day picks — so the plan alone cannot distinguish "the norm pruned the
            # alternatives" from "nothing happened and the default won". The refusals say which.
            print(f"{'':32s}        refused={r['refused']}")
            for line in r["why"]:
                print(f"{'':32s}        why: {line}")
        except Exception as e:                      # a refusal is a result too — report, never swallow
            print(f"{name:32s} RAISED {type(e).__name__}: {e}")


if __name__ == "__main__":
    main()
