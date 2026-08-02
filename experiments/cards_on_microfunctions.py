"""SLICE 0 — the decider probe. Does the card-trader domain survive onto the microfunctions engine?

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

from microfunctions import asm, driver as D, guideline as GL, intake as I, thread as T, types as TY
from microfunctions.graph import Graph

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
# CLASS. Nothing upstream reads this; the harness expands a class norm over it (see `prohibitions`).
CLASSES = {"buy_at_shop": "buy", "buy_online": "buy", "trade_at_club": "trade",
           "counterfeit_card": "counterfeit", "sell_rare": "sell"}

# Risk gradings, verbatim from the KB. Degrees stay authored data, never a magic number in code.
DEGREE = {"very": 0.8, "somewhat": 0.5, "slightly": 0.3}
RISK = {"buy_online": "somewhat", "trade_at_club": "very",
        "counterfeit_card": "very", "sell_rare": "somewhat"}
CAUTION = {"high": 0.3, "medium": 0.5, "low": 0.8}   # a caution is the alpha-cut it sets

# Standing house norms, and the authority ranking. `law` is outranked by nothing.
STANDING = [("sell", "standing"), ("counterfeit", "law")]
OUTRANKS = {("today", "standing")}


def prohibitions(today: list[tuple[str, str]], caution: str | None) -> list[str]:
    """Compose the standing norms, today's instructions and the risk cut into `never` lines.

    ⚠⚠ **THIS FUNCTION IS THE PROBE'S CENTRAL FINDING.** In the old engine every line of this was rules
    in `corpus/policy.cnl` and `corpus/risk.cnl`, and the override was auditable — `why is buy not
    excluded` traced to the outranking encouragement. Upstream now, `never` PRUNES ABSOLUTELY and
    `prefer`/`avoid` can only ever REORDER, deliberately, so there is no in-engine place for a
    defeasible norm. The arbitration has nowhere to live but here, in Python.

    That is a real loss and it is the §7.2 open question. Recorded honestly rather than papered over.
    """
    encouraged = {act for act, src, good in today if good}
    banned = []
    for act, src in STANDING:
        beaten = any(a == act and (s, src) in OUTRANKS for a, s, _ in today)
        if not beaten:
            banned.append(act)
    for act, src, good in today:
        if not good and act not in banned:
            banned.append(act)
    if caution:
        cut = CAUTION[caution]
        banned += [op for op, grade in RISK.items()
                   if DEGREE[grade] >= cut and op not in encouraged]
    return banned


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

    lines = [f"goal {name}:", f"    me.{want} = true"]
    for act in prohibitions(list(today), caution):
        for op, cls in CLASSES.items():          # a class norm scopes over its operators
            if cls == act or op == act:
                lines.append(f"    never {op}")
    goal = I.read_goal(g, "\n".join(lines) + "\n")

    th = T.open_thread(g, "day")
    # ⚠ Guidelines are consulted only through `rank=`. Omit it and `prefer`/`avoid` parse, sit in the
    # graph, and silently say nothing — which cost this probe one wrong answer before it was wired.
    report = D.pursue(g, goal, th, shop, rank=GL.ranker(g))
    steps = D.plan_bindings(g, report["plan"]) if report["found"] else ()
    return {"done": bool(report["found"]),
            "chosen": tuple(fn for fn, _ in steps),
            "refused": tuple(sorted(fn for fn, _why in report["refused"])),
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
        except Exception as e:                      # a refusal is a result too — report, never swallow
            print(f"{name:32s} RAISED {type(e).__name__}: {e}")


if __name__ == "__main__":
    main()
