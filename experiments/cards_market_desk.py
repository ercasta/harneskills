"""SLICE 0b — the trading DESK. A card domain that must LOOK at a market and ACT on it.

`cards_on_microfunctions.py` asked whether the card domain survives onto the UGM engine. It does. But
that probe is a **closed world**: every fact it needs is authored before the goal exists, every
operator's effect is known in advance, nothing it does can fail, and its goals are monotone —
`has_rare_card` is a flag that only ever goes up, so a plan can never make things worse.

A real desk is none of those things, and this probe is that desk:

  * **You do not know the world.** How many rares are in the case, and what they are quoted at, are
    facts you have to *go and look at* — `dispatch.register(..., observes=True)` and the pursuit's
    SENSING phase.
  * **Acting is irreversible and can miss.** An order goes to a market that decides the fill. The plan
    says one thing, reality does another, and the loop has to notice — divergence and replan.
  * **The goal is TWO-SIDED.** *"Balance the stock"* is `rares >= 3` **and** `cash >= 300`. Every
    operator that helps one side hurts the other, so a plan is a trade-off rather than an accumulation
    and a wrong step is not merely useless, it is a regression.
  * **What you knew goes stale.** A quote is true at a moment. The market moves underneath a plan that
    was built on it.

Run: `python experiments/cards_market_desk.py`

⚠ **Read what each scenario measured, not the done/stuck column.** Six of these are `stuck`, crash or
loop *on purpose* — they are the measurements behind `docs/feedback_ugm_market_desk.md` (F1–F7), and a
uniformly green run would mean the probe had stopped asking anything. The findings, in short:

  F1  a comparison constraint is rendered as `=` whatever the operator was  (s1, and every `why`)
  F2  ⭐⭐ arithmetic over an UNKNOWN slot raises a raw `TypeError` out of `loop.run`  (s2 vs s3)
  F3  ⭐ sensing considers only the pursuit's subject; planning searches *under* it  (s4)
  F4  `blocked_on_ignorance` is all-or-nothing, so a half-ignorant desk never looks  (s5)
  F5  replanning after a divergence has no memory, and repeats the irreversible order  (s6)
  F6  a value once known is known for ever; nothing ever re-observes  (s7)
  F7  `ADD` is the only arithmetic, so a cost *read from the world* cannot be subtracted  (s11)

And what worked, because a finding list is a biased sample: the two-sided numeric plan (s1), norms and
defeasible authority in a domain that is about money rather than flags (s8–s10), and the
stop-before-the-first-irreversible-step gate that makes this a UI story at all (s12).
"""
from __future__ import annotations

import sys

from ugm import (asm, discourse as DC, dispatch as DP, driver as D, goal as G, guideline as GL,
                 intake as I, loop as L, norm as N, thread as T, types as TY)
from ugm.graph import Graph, UNKNOWN

# =====================================================================================================
# THE DOMAIN, as authored data. Compare `corpus/cards_kb.cnl`: the operator surface is again nothing but
# signatures, and "balanced" is two ordinary type constraints that no single operator satisfies.
# =====================================================================================================

TYPES = [
    'type desk:\n    kind_of = "desk"\n',
    'type stocked_desk:\n    is a desk\n    rares >= 3\n',
    'type funded_desk:\n    is a desk\n    cash >= 300\n',
]

# --- THE LOOKS. Everything they learn is on the far side of a DISPATCH, so `establishes` reads nothing
# from them and means-ends can never select one. Sensing has to pick them directly, and does.
LOOKS = """
fn check_inventory(d: desk) -> desk:
    DISPATCH R(out) "count_stock" F(d)

fn check_market(d: desk) -> desk:
    DISPATCH R(out) "market_quote" F(d)
"""

# --- THE ACTS. The market decides the fill, so each body is a dispatch and the ASSUMPTION about how it
# turns out is a `mocks` — the declared prediction a plan is built on and reality is checked against.
#
# ⚠ F7 lives in `fills_at_ask`. A purchase costs the ASK, which is a number read from the world
# (`quote + 20`), and the cost has to be *subtracted* from cash. `ADD` is the only arithmetic opcode —
# there is no SUB, MUL or NEG — and a literal is the only thing that can be negative, so the ask price
# is hardcoded at 140 here and the operator silently stops being about the market it is trading on.
# See s11: this is not a style complaint, it is the domain becoming unwritable.
ACTS = """
fn sell_rare(d: stocked_desk) -> funded_desk:
    DISPATCH R(out) "place_sell_order" F(d)

fn sells_at_quote(d: stocked_desk) -> funded_desk mocks sell_rare:
    ATTR R(c) F(d) "cash"
    ATTR R(q) F(d) "quote"
    ADD R(c) R(c) R(q)
    SET F(d) "cash" R(c)
    ATTR R(n) F(d) "rares"
    ADD R(n) R(n) -1
    SET F(d) "rares" R(n)

fn buy_rare(d: funded_desk) -> stocked_desk:
    DISPATCH R(out) "place_buy_order" F(d)

fn fills_at_ask(d: funded_desk) -> stocked_desk mocks buy_rare:
    ATTR R(n) F(d) "rares"
    ADD R(n) R(n) 1
    SET F(d) "rares" R(n)
    ATTR R(c) F(d) "cash"
    ADD R(c) R(c) -140
    SET F(d) "cash" R(c)

fn sell_bulk_commons(d: desk) -> funded_desk:
    DISPATCH R(out) "sell_commons" F(d)

fn commons_clear(d: desk) -> funded_desk mocks sell_bulk_commons:
    ATTR R(c) F(d) "cash"
    ADD R(c) R(c) 90
    SET F(d) "cash" R(c)

fn wash_trade(d: desk) -> funded_desk:
    DISPATCH R(out) "wash" F(d)

fn wash_pays(d: desk) -> funded_desk mocks wash_trade:
    ATTR R(c) F(d) "cash"
    ADD R(c) R(c) 400
    SET F(d) "cash" R(c)
"""

# Action classes, so a norm over a CLASS scopes to its operators. Still a lookup over authored data and
# it must stay one — the moment it decides anything it has become what `ugm/norm.py` deleted.
CLASSES = {"sell_rare": "liquidate", "sell_bulk_commons": "liquidate", "buy_rare": "acquire",
           "wash_trade": "wash", "check_market": "look", "check_inventory": "look"}

STANDING = [("liquidate", "standing", N.DEFEASIBLE),   # we hold our stock — unless today says otherwise
            ("wash", "law", N.INVIOLABLE)]             # never, whatever the day says
OUTRANKS = [("today", "standing")]


def operators_of(action: str) -> list:
    return [op for op, cls in CLASSES.items() if cls == action or op == action]


def declare_norms(g: Graph, today, standing=STANDING) -> None:
    """Declare who forbids what, on whose authority. Decides nothing — `norm.apply` settles it.

    `standing` is a parameter only so s1 can install the law without the house's hold-your-stock
    stance: the law is in force every day, and a scenario that omits it is not a neutral scenario, it
    is a scenario in which crime pays. s1 found that out the hard way."""
    for holder, over in OUTRANKS:
        DC.authority(g, DC.speaker(g, holder), DC.speaker(g, over))
    for action, source, force in standing:
        for op in operators_of(action):
            N.declare(g, action=op, stance=N.FORBID, source=DC.speaker(g, source), force=force,
                      because=f"the {source} says not to {action}")
    for action, source, good in today:
        for op in operators_of(action):
            N.declare(g, action=op, stance=N.PERMIT if good else N.FORBID,
                      source=DC.speaker(g, source),
                      because=f"today {'favours' if good else 'rules out'} {action}")


# =====================================================================================================
# THE MARKET — the world behind the tools. The graph cannot see any of it until it looks and cannot
# change any of it except by acting. That is the whole point: a ledger the engine does not own, which
# moves whether or not anybody is watching.
# =====================================================================================================

class Market:
    ASK_OVER_BID = 20

    def __init__(self, *, rares=5, cash=120, quote=200, fills=True, drift=0):
        self.rares, self.cash, self.quote = rares, cash, quote
        self.fills, self.drift = fills, drift
        self.log: list = []
        self.quote_history: list = []      # what each fill ACTUALLY went off at — see s7

    def _move(self):
        """Every interaction moves the market. A quote is true at a moment, not for ever."""
        self.quote += self.drift

    # --- looks: they change what we KNOW, never what IS -------------------------------------------
    def count_stock(self, g, d):
        self.log.append(f"count_stock->{self.rares}")
        g.put(d, rares=self.rares)
        return self.rares

    def market_quote(self, g, d):
        self.log.append(f"market_quote->{self.quote}")
        g.put(d, quote=self.quote)
        return self.quote

    # --- acts: irreversible, and the market decides the outcome -----------------------------------
    def place_sell_order(self, g, d):
        self.log.append("place_sell_order")
        self._move()
        if not self.fills or self.rares <= 0:
            return None                     # nobody bid. Nothing moves, and the order is spent anyway.
        self.rares -= 1
        self.cash += self.quote
        self.quote_history.append(self.quote)
        g.put(d, rares=self.rares, cash=self.cash)
        return self.quote

    def place_buy_order(self, g, d):
        self.log.append("place_buy_order")
        self._move()
        ask = self.quote + self.ASK_OVER_BID
        if self.cash < ask:
            return None
        self.rares += 1
        self.cash -= ask
        g.put(d, rares=self.rares, cash=self.cash)
        return ask

    def sell_commons(self, g, d):
        self.log.append("sell_commons")
        self._move()
        self.cash += 90
        g.put(d, cash=self.cash)
        return 90

    def wash(self, g, d):
        self.log.append("WASH TRADE")       # if this is ever in the log, the law failed
        self.cash += 400
        g.put(d, cash=self.cash)
        return 400


def world(m: Market, *, knows_stock=True, knows_quote=True, arithmetic=True):
    """A desk on a market.

    `knows_*` is what has been LOOKED AT, not what is true — an unlooked slot is `UNKNOWN`, which is the
    engine's own third value and not a `None` we invented.

    `arithmetic=False` loads the looks without the acts. That is not a convenience: it is the control
    for F2, and the only configuration in which this domain can sense at all (s2 vs s3)."""
    g = Graph()
    for block in TYPES:
        I.read(g, block)                    # one block per read, by design
    asm.load_text(g, LOOKS + (ACTS if arithmetic else ""))
    shop = g.mint("shop")
    g.link("root", "has", shop)
    d = g.mint("desk", kind_of="desk", label="desk", cash=m.cash,
               rares=m.rares if knows_stock else UNKNOWN,
               quote=m.quote if knows_quote else UNKNOWN)
    g.link(shop, "desk", d)
    TY.tag(g, d, "desk")
    DP.register("count_stock", m.count_stock, observes=True)
    DP.register("market_quote", m.market_quote, observes=True)
    DP.register("place_sell_order", m.place_sell_order)
    DP.register("place_buy_order", m.place_buy_order)
    DP.register("sell_commons", m.sell_commons)
    DP.register("wash", m.wash)
    return g, shop, d


def believed(g, d) -> str:
    """What the desk THINKS is true — which is the only thing it can plan against."""
    return f"cash={g.attr(d, 'cash')} rares={g.attr(d, 'rares')} quote={g.attr(d, 'quote')}"


def drive(g, task, *, max_ticks=400, stop_before_acting=False):
    """Tick a pursuit on its own agenda, reporting the verbs. `stop_before_acting` is the human gate:
    read `verb_of` on the head and decline, which is the one thing a caller must do for itself."""
    lp = L.open_loop(g)
    L.schedule(g, lp, task, why="run the desk")
    verbs, held = [], None
    for _ in range(max_ticks):
        ag = L.agenda(g, lp)
        if not ag:
            break
        if stop_before_acting and L.verb_of(g, ag[0]) in L.IRREVERSIBLE:
            held = L.describe(g, ag[0])
            break
        rec = L.tick(g, lp)
        if rec is None:
            break
        if rec["verb"]:
            verbs.append(rec["verb"])
    return tuple(dict.fromkeys(verbs)), held


# =====================================================================================================
# THE SCENARIOS. Each is a measurement, and `stuck` is a result rather than a failure.
# =====================================================================================================

def s1_balance_the_stock():
    """⭐ THE HEADLINE, and it works. A two-sided goal that no single operator reaches.

    `rares >= 3` and `cash >= 300` from `rares=2, cash=250`. Buying the rare closes the stock side and
    *breaks* the cash side (−140); selling commons (+90) closes cash and does nothing for stock. So the
    plan has to interleave them and get the arithmetic right — which the first probe never asked,
    because `has_rare_card` was a flag that only went up.

    ⚠ Only the law is installed here, and that is load-bearing rather than tidy: with no norms at all
    the first run of this scenario planned `sell_bulk_commons → buy_rare → wash_trade`, because a wash
    trade pays 400 and closes the cash side in one step. The planner was right and the scenario was
    wrong. A "neutral" day is not one with no norms in it.

    ⚠ F1 rides along: read the rendered goal against what the block actually said."""
    m = Market(rares=2, cash=250, quote=120)
    g, shop, d = world(m)
    goal = I.read_goal(g, "goal balance:\n    desk.rares >= 3\n    desk.cash >= 300\n")
    declare_norms(g, [], standing=[("wash", "law", N.INVIOLABLE)])
    N.apply(g, goal)
    r = D.pursue(g, goal, T.open_thread(g, "day"), shop)
    plan = tuple(f for f, _ in D.plan_bindings(g, r["plan"])) if r["found"] else ()
    return {"found": r["found"], "plan": plan,
            "the block said": "desk.rares >= 3 / desk.cash >= 300",
            "the engine renders it as":
                "; ".join(G.describe_constraint(g, c) for c in G.constraints(g, goal)),
            "F1": "the operator is stored on the constraint and dropped by describe_constraint"}


def s2_the_unknown_number_stops_everything():
    """⚠⚠ FINDING F2, and it is the severe one. The desk does not know what is in its own case.

    `rares` is UNKNOWN, so this is the textbook SENSING case — go and look, then plan. It never gets
    there. Means-ends imagines `sell_rare`, whose mock does `ADD` on the unknown `rares`, and the ISA
    adds `_Unknown` to an int: a raw `TypeError` out of `Machine.tick`, through `workbench.step`,
    through `driver.step`, out of `loop.run`. The pursuit is stranded mid-planning and **the agenda is
    emptied**, so anything else sharing that loop dies with it.

    That is the exact failure `check_a_pursuit_ACTS_on_an_unfinished_plan` records having fixed for
    `Imagined` — *"the exception escaped `loop.tick`, stranding the pursuit and killing every other task
    on the shared agenda"* — one phase earlier and still unguarded. And it is not an edge case here: it
    means **no numeric domain can ever sense**, because the arithmetic that makes the domain worth
    planning over is what crashes on the unknown the sensing exists to resolve. s3 is the control."""
    m = Market(rares=5, cash=400, quote=200)
    g, shop, d = world(m, knows_stock=False, arithmetic=True)
    goal = I.read_goal(g, "goal know_the_case:\n    desk.rares >= 3\n")
    try:
        verbs, _ = drive(g, D.open_pursuit(g, goal, T.open_thread(g, "day"), d))
        return {"found": False, "plan": (), "verbs": verbs, "F2": "did NOT raise — has this been fixed?"}
    except TypeError as e:
        return {"found": False, "plan": (),
                "raised out of loop.run": f"{type(e).__name__}: {e}",
                "tools actually called": tuple(m.log),
                "F2": "planning over an UNKNOWN number is a crash, not a refusal; the agenda is emptied"}


def s3_look_before_you_trade():
    """The control for F2, and the good news: sensing itself works, and works well.

    The identical desk and the identical goal, with the arithmetic operators simply not loaded. The
    pursuit reports `look`, dispatches a real tool against the market's ledger, learns `rares=5` and
    closes the goal. One line of the library is the whole difference between this and s2."""
    m = Market(rares=5, cash=400, quote=200)
    g, shop, d = world(m, knows_stock=False, arithmetic=False)
    goal = I.read_goal(g, "goal know_the_case:\n    desk.rares >= 3\n")
    p = D.open_pursuit(g, goal, T.open_thread(g, "day"), d)
    verbs, _ = drive(g, p)
    return {"found": D.pursuit_report(g, p)["done"], "plan": g.attr(p, "sensed") or (),
            "verbs": verbs, "tools actually called": tuple(m.log),
            "the desk now believes": believed(g, d)}


def s4_the_subject_that_cannot_look():
    """⚠ FINDING F3. s3 again, changing exactly one argument: the pursuit's subject is the shop that
    holds the desk rather than the desk itself.

    Planning searches *under* a subject — which is why `cards_on_microfunctions.py` passes the shop
    everywhere and is right to. Sensing selects *on* the subject (`selection.candidates(g, subject)`),
    so a container can never look, and the pursuit then reports what a genuinely impossible goal
    reports. Two meanings of "subject" on one parameter, and the wrong one fails silently."""
    m = Market(rares=5, cash=400, quote=200)
    g, shop, d = world(m, knows_stock=False, arithmetic=False)
    goal = I.read_goal(g, "goal know_the_case:\n    desk.rares >= 3\n")
    p = D.open_pursuit(g, goal, T.open_thread(g, "day"), shop)      # the ONLY difference from s3
    verbs, _ = drive(g, p)
    return {"found": D.pursuit_report(g, p)["done"], "plan": g.attr(p, "sensed") or (),
            "verbs": verbs, "tools actually called": tuple(m.log),
            "why": D.pursuit_report(g, p).get("why"),
            "F3": "the refusal names ignorance; nothing names the subject that could not look"}


def s5_the_half_ignorant_desk():
    """⚠ FINDING F4. The realistic desk: cash is known and short, stock is unknown.

    `blocked_on_ignorance` is all-or-nothing by design, and the design is well argued — a plan must
    *bottom out* in ignorance so an agent does not look in every box. But a desk always knows one thing
    and never knows the other, so the test is never met and the one box worth opening is never opened.
    Nothing is refused and nothing is reported; it simply plans blind about a number it could have had
    for the cost of one look."""
    m = Market(rares=5, cash=120, quote=200)
    g, shop, d = world(m, knows_stock=False, arithmetic=False)
    goal = I.read_goal(g, "goal balance:\n    desk.rares >= 3\n    desk.cash >= 300\n")
    p = D.open_pursuit(g, goal, T.open_thread(g, "day"), d)
    verbs, _ = drive(g, p)
    return {"found": D.pursuit_report(g, p)["done"], "plan": g.attr(p, "sensed") or (),
            "unmet": tuple(G.describe_constraint(g, c) for c in G.unmet(g, goal, under=d)),
            "of which undetermined":
                tuple(G.describe_constraint(g, c) for c in G.undetermined(g, goal, under=d)),
            "blocked_on_ignorance": G.blocked_on_ignorance(g, goal, under=d),
            "tools actually called": tuple(m.log),
            "F4": "one known-false constraint beside one unknown, and it never looks"}


def s6_the_order_that_did_not_fill():
    """⚠ FINDING F5. Nobody bids.

    The good half first: the plan assumed a fill, reality delivered none, and the divergence is caught
    exactly as designed — the declared type would have passed, and only the concrete expectation
    notices. Then the pursuit replans and **places the same order again**, once per attempt.

    `carry_out` says replanning is going round the loop from the world as it really is, and it is. But
    the world did not change, so the same plan is re-derived, and the attempt record that says what just
    failed is not read by the thing that replans. On a filesystem a repeated failing step costs a
    syscall. Here it costs three real orders into a market that refused the first one."""
    m = Market(rares=5, cash=120, quote=200, fills=False)
    g, shop, d = world(m)
    goal = I.read_goal(g, "goal raise_cash:\n    desk.cash >= 300\n")
    r = D.carry_out(g, goal, T.open_thread(g, "day"), shop, attempts=3)
    return {"found": r["done"], "plan": (), "attempts": r["tries"],
            "orders actually placed": tuple(m.log),
            "each time": tuple({a["diverged"].splitlines()[0] for a in r["attempts"]
                                if a.get("diverged")}),
            "why": r.get("why"),
            "F5": "three identical irreversible orders; the divergence taught the replan nothing"}


def s7_the_quote_went_stale():
    """⚠ FINDING F6. The desk quoted the card yesterday. The market has moved 60 a trade since.

    Nothing here is unknown, so nothing senses — `undetermined` asks only whether a slot is UNKNOWN, and
    a value once written is known for ever. The desk plans against 200, sells into a market at 140, the
    goal misses, it replans against 200 again, and `check_market` — a registered observing tool, sitting
    right there in the library — is never once called.

    ⭐ The engine already has the missing half: `dispatch.service` stamps every observation with a
    moment and `clock.py` opens with *"everything observed or acted must have an absolute timestamp"*.
    The staleness is recorded. Nothing consults it.

    ⚠ It reports `done`, and that is the sharpest form of the finding rather than a let-off. Every plan
    it made was arithmetically wrong — the first order was planned to bring cash to 320 and brought it
    to 260 — and it arrived only because a second order it had not planned happened to cover the gap.
    The goal is checked against reality, so the *outcome* is honest; the plan is re-derived against
    belief, so the *reasoning* was wrong every single time and nothing anywhere says so."""
    m = Market(rares=5, cash=120, quote=200, drift=-60)
    g, shop, d = world(m)                       # believed quote 200, and it will not be revisited
    goal = I.read_goal(g, "goal raise_cash:\n    desk.cash >= 300\n")
    believed_before = g.attr(d, "cash")
    quote_at_plan = g.attr(d, "quote")
    r = D.carry_out(g, goal, T.open_thread(g, "day"), shop, attempts=3)
    return {"found": r["done"], "plan": (),
            "tools actually called": tuple(m.log),
            "one sale was planned to bring cash to": believed_before + quote_at_plan,
            "the first sale actually brought it to": believed_before + m.quote_history[0],
            "the desk still believes the quote is": g.attr(d, "quote"),
            "the market is actually at": m.quote,
            "F6": "check_market is registered, applicable, and never once called"}


def _norm_day(*, today):
    m = Market(rares=5, cash=120, quote=200)
    g, shop, d = world(m)
    goal = I.read_goal(g, "goal raise_cash:\n    desk.cash >= 300\n")
    declare_norms(g, list(today))
    N.apply(g, goal)
    r = D.pursue(g, goal, T.open_thread(g, "day"), shop, rank=GL.ranker(g))
    plan = tuple(f for f, _ in D.plan_bindings(g, r["plan"])) if r["found"] else ()
    return {"found": r["found"], "plan": plan,
            "refused": tuple(sorted({f for f, _why in r["refused"]})),
            "why": tuple(N.explain(g, op) for op in CLASSES if N.norms(g, op))}


def s8_hold_the_line():
    """The standing house norm, now in a domain about money rather than flags. We hold our stock, and
    `sell_bulk_commons` is `liquidate` too, so the class is forbidden and the desk is honestly stuck."""
    return _norm_day(today=())


def s9_liquidate_today():
    """Today outranks standing, so the same desk sells. Nothing in this file decides that — `norm.apply`
    settles the two sources and writes ordinary `never` constraints, and `norm.explain` says which won."""
    return _norm_day(today=[("liquidate", "today", True)])


def s10_the_law_holds():
    """The wash trade pays 400 and closes the goal in one step, today says do it, everything else is
    ruled out — and it is still refused, because nothing outranks the law. The one operator that would
    have worked is the one that cannot be taken."""
    return _norm_day(today=[("wash", "today", True), ("liquidate", "today", False)])


def s11_the_cost_that_cannot_be_written():
    """⚠ FINDING F7, measured rather than asserted. What a purchase costs is `quote + 20`, a number read
    from the world, and it has to come *off* cash. `ADD` is the only arithmetic opcode.

    Only a literal can be negative, so `fills_at_ask` hardcodes 140 and quietly stops being about the
    market it trades on. Every money domain hits this on its first operator: a price times a quantity,
    a fee, a spread, a margin. The alternative is a `NATIVE`, which is domain arithmetic in Python —
    precisely the island this project's standing rule exists to prevent."""
    g = Graph()
    I.read(g, 'type desk:\n    kind_of = "desk"\n')
    out = {}
    for op, src in (("SUB", 'fn pay(d: desk) -> desk:\n    ATTR R(c) F(d) "cash"\n'
                            '    ATTR R(q) F(d) "quote"\n    SUB R(c) R(c) R(q)\n'),
                    ("MUL", 'fn value(d: desk) -> desk:\n    ATTR R(n) F(d) "rares"\n'
                            '    ATTR R(q) F(d) "quote"\n    MUL R(v) R(n) R(q)\n')):
        try:
            asm.load_text(g, src)
            out[op] = "accepted"
        except Exception as e:
            out[op] = str(e).split(". Known")[0]
    return {"found": False, "plan": (), **out,
            "F7": "cash -= ask and position = count * price are both inexpressible"}


def s12_confirm_before_the_first_act():
    """⭐ NOT a finding — the affordance that makes this domain a UI story, and it already works.

    `loop.verb_of` answers *what kind of step would this be* BEFORE the step is taken, so a driver ticks
    through planning and stops dead at the first `act`, with a plan in hand and nothing sent. That is
    the moment a desk shows a human the order and asks.

    Nothing in the engine does the asking and nothing should — *"declining to act has to be something a
    caller does, not something a loop does on its behalf"*. Which makes it exactly the seam HarneSkills
    exists to render, and the reason this domain is worth a screen."""
    m = Market(rares=5, cash=120, quote=200)
    g, shop, d = world(m)
    goal = I.read_goal(g, "goal raise_cash:\n    desk.cash >= 300\n")
    p = D.open_pursuit(g, goal, T.open_thread(g, "day"), shop)
    verbs, held = drive(g, p, stop_before_acting=True)
    return {"found": held is not None, "plan": (), "verbs": verbs,
            "held at the door": held,
            "orders actually placed": tuple(m.log),
            "note": "a plan in hand, nothing irreversible spent, and a human still to ask"}


SCENARIOS = [
    ("s1  balance_the_stock",           s1_balance_the_stock,               "⭐ a trade-off plan"),
    ("s2  unknown_number_stops_all",    s2_the_unknown_number_stops_everything, "⚠ F2 TypeError escapes"),
    ("s3  look_before_you_trade",       s3_look_before_you_trade,           "the control: it looks"),
    ("s4  subject_that_cannot_look",    s4_the_subject_that_cannot_look,    "⚠ F3 silent, never looks"),
    ("s5  half_ignorant_desk",          s5_the_half_ignorant_desk,          "⚠ F4 never looks"),
    ("s6  order_did_not_fill",          s6_the_order_that_did_not_fill,     "⚠ F5 repeats the order"),
    ("s7  quote_went_stale",            s7_the_quote_went_stale,            "⚠ F6 never re-looks"),
    ("s8  hold_the_line",               s8_hold_the_line,                   "stuck, and correctly"),
    ("s9  liquidate_today",             s9_liquidate_today,                 "today outranks standing"),
    ("s10 the_law_holds",               s10_the_law_holds,                  "wash_trade refused"),
    ("s11 cost_cannot_be_written",      s11_the_cost_that_cannot_be_written, "⚠ F7 no SUB, no MUL"),
    ("s12 confirm_before_first_act",    s12_confirm_before_the_first_act,   "⭐ the UI seam, and it works"),
]


def main() -> None:
    # The console this runs on is cp1252 by default, and every marker in this file is outside it.
    # Reported rather than silently dropped: a probe whose output depends on the terminal's codepage
    # is a probe whose findings cannot be pasted into a report.
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass
    for name, run, expect in SCENARIOS:
        try:
            r = run()
            print(f"{name:32s} {'done ' if r.get('found') else 'stuck'}  "
                  f"plan={r.get('plan')}   expected: {expect}")
            for k, v in r.items():
                if k not in ("found", "plan"):
                    print(f"{'':32s}        {k}: {v}")
        except Exception as e:              # a refusal is a result too — report, never swallow
            print(f"{name:32s} RAISED {type(e).__name__}: {e}")
        print()


if __name__ == "__main__":
    main()
