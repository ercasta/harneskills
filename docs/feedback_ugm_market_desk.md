# Feedback from HarneSkills — the UGM engine, second round: an agent that must LOOK and ACT

Collected 2026-08-02 from `experiments/cards_market_desk.py`, against `ugm` @ `62ddd3c`,
`universal-graph-machine` 0.3.0, installed editable, Python 3.13, Windows.

Same spirit and format as `feedback_microfunctions.md`, whose five actionable items you closed in a
day: **every item has a minimal repro that imports only the engine**, each separates *what we measured*
from *what we think it means*, and they are ordered by what they would be worth to us. Where an item is
a design question rather than a defect we say so, and *"out of scope"* remains an answer we would
rather have stated than discover.

**What is new about this round.** The first probe re-expressed our card domain and asked whether it
survived the move. It did. But that probe is a **closed world**: every fact authored before the goal
exists, every effect known in advance, nothing that can fail, and goals that are monotone —
`has_rare_card` is a flag that only goes up, so no plan can make anything worse.

This round is the same domain opened up into a **trading desk**, which is the smallest change that
makes all four of those false at once:

* it does not know the world — how many cards are in the case, and what they are quoted at, are facts
  it must **go and look at**;
* acting is **irreversible and can miss** — an order goes to a market that decides the fill;
* the goal is **two-sided** — *"balance the stock"* is `rares >= 3` **and** `cash >= 300`, and every
  operator that helps one side hurts the other;
* what it knew **goes stale** — a quote is true at a moment.

We picked it because it is the smallest honest test of `dispatch`, `loop.verb_of`, the SENSING phase and
divergence *together*, and because those are the surfaces a UI has to render. Seven findings, F1–F7.

⚠ **Scope note, so this is not read as a land grab.** HarneSkills is a UI/UX layer over UGM and owns no
domain and no reasoning. This probe is not a domain we are asking to maintain — it is an instrument.
Everything below is yours to accept, reshape or decline.

---

## 0. What worked, because a defect list is a biased sample

Three things, and the first is the one we did not expect.

- **⭐ Two-sided numeric planning works, out of the box, with nothing of ours involved.** From
  `rares=2, cash=250`, wanting `rares >= 3` **and** `cash >= 300`, where buying costs 140 and selling
  commons pays 90, backward chaining produced:

  ```
  sell_bulk_commons → buy_rare → sell_bulk_commons → sell_bulk_commons
  ```

  It interleaves the two sides, spends the cash it just raised, and raises it back. Nothing about that
  is a flag going up. We had assumed a trade-off would need something we would have to build.

- **`norm.py` holds up in a domain about money rather than about flags.** The standing house stance
  (*hold the stock*), today's instruction (*liquidate*), and an inviolable law (*never wash-trade*)
  arbitrate correctly, and `norm.explain` still names what overrode what:

  ```
  sell_rare: permit — today (today favours liquidate); overriding standing's forbid
  wash_trade: forbid — law (the law says not to wash), inviolable; overriding today's permit
  ```

  ⚠ One thing this domain taught us that the flag domain could not: **a scenario with no norms is not a
  neutral scenario.** Our headline case first planned `… → wash_trade`, because a wash trade pays 400
  and closes the cash side in one step. The planner was right; the scenario was wrong. Worth a line in
  `docs/deliberation.md` for anyone building a fixture.

- **⭐⭐ `loop.verb_of` is the affordance that makes an acting agent presentable, and it already
  works exactly as specified.** Ticking a pursuit and reading the verb on the head of the agenda stops
  the desk dead at `acting`, with a plan in hand and **no order sent**:

  ```
  held at the door: pursuing 'raise_cash', attempt 1: acting (step 0 of 1)
  orders actually placed: ()
  ```

  Your standing position is that declining to act has to be something a caller does, not something the
  loop does on its behalf. We agree, and we are that caller — this is the seam HarneSkills exists to
  render. Please keep `verb_of` answerable *before* the step; everything we want to build on this
  depends on that ordering.

---

## 1. ⭐⭐ Arithmetic over an UNKNOWN slot raises a raw `TypeError` out of `loop.run`, and empties the agenda

**Severity: high, and it is the one that stops the feature working at all in our domain.**

**Measured.** A goal bottoms out in ignorance, which is exactly the SENSING case. It never gets there:
means-ends imagines an operator whose body does `ADD` on the unknown slot, and the ISA adds `_Unknown`
to an `int`.

```python
from ugm import (asm, dispatch as DP, driver as D, goal as G, intake as I, loop as L,
                 thread as T, types as TY)
from ugm.graph import Graph, UNKNOWN

DP.register("count", lambda gr, t: gr.put(t, rares=5), observes=True)

g = Graph()
I.read(g, 'type desk:\n    kind_of = "desk"\n')
I.read(g, 'type stocked_desk:\n    is a desk\n    rares >= 3\n')
asm.load_text(g, 'fn look(d: desk) -> desk:\n    DISPATCH R(o) "count" F(d)\n\n'
                 'fn buy(d: desk) -> stocked_desk:\n'
                 '    ATTR R(n) F(d) "rares"\n    ADD R(n) R(n) 1\n    SET F(d) "rares" R(n)\n')
d = g.mint("desk", kind_of="desk", label="desk", rares=UNKNOWN)
g.link("root", "has", d); TY.tag(g, d, "desk")

goal = I.read_goal(g, "goal hold_three:\n    desk.rares >= 3\n")
print("blocked_on_ignorance:", G.blocked_on_ignorance(g, goal, under=d))
p = D.open_pursuit(g, goal, T.open_thread(g), d)
lp = L.open_loop(g); L.schedule(g, lp, p, why="x")
try:
    L.run(g, lp, max_ticks=200)
except TypeError as e:
    print("raised out of loop.run:", e)
    print("agenda now:", L.agenda(g, lp), "| pursuit stuck in phase:", g.attr(p, "phase"))
```

```
blocked_on_ignorance: True
raised out of loop.run: unsupported operand type(s) for +: '_Unknown' and 'int'
agenda now: () | pursuit stuck in phase: planning
```

Remove the two `ADD` lines — nothing else — and the identical world senses, dispatches for real, learns
`rares=5` and closes the goal. That contrast is `s2` versus `s3` in the probe.

**We think** this is the same defect your own selftest records having fixed one phase earlier, and it
reads almost word for word. `check_a_pursuit_ACTS_on_an_unfinished_plan_and_then_REPLANS`:

> *"such an operator made `dispatch.service` raise `Imagined` inside planning, and the exception escaped
> `loop.tick` — stranding the pursuit and killing every other task on the shared agenda. Exactly what
> `execution.step` already records for `TypeViolation`, one phase earlier. It is skipped and recorded
> now, not fatal."*

An imagined step that cannot be computed is the same category as an imagined step that must not be
taken: the state is unreachable, so the branch should be **skipped and recorded**, not fatal. Two
things follow, and we care much more about the first:

1. **Containment.** An arithmetic failure inside `workbench.step` should be caught where `Imagined` and
   `TypeViolation` are, and reported as a refusal on that branch. Today one bad operator anywhere in the
   library takes down every unrelated task sharing the agenda, which is the property `loop.py` is most
   careful about everywhere else.
2. **Possibly, a decision about UNKNOWN in arithmetic.** `_Unknown` is a real third value in this engine
   and `ADD` is the only place it meets one. Propagating (unknown + 1 = unknown) would let the search
   *reason* about the branch instead of dropping it. We are not asking for that — it is a semantics
   decision and refusing loudly is defensible. Containment is the ask.

⚠ **Why we rate this highest.** It is not an edge case in a numeric domain, it is the *general* case:
the arithmetic that makes a domain worth planning over is exactly what crashes on the unknown that
sensing exists to resolve. As it stands, **a domain can be numeric or it can sense, not both**.

---

## 2. ⭐⭐ A divergence teaches the next attempt nothing, so the same irreversible action is taken again

**Severity: high for anything that acts on the world, and it is a safety property rather than a
performance one.**

**Measured.** An order that nobody fills. The divergence is caught exactly as designed — the declared
return type passes, and only the concrete expectation notices. Then the pursuit replans and places the
same order again, once per attempt.

```python
from ugm import asm, dispatch as DP, driver as D, intake as I, thread as T, types as TY
from ugm.graph import Graph

placed = []
DP.register("sell", lambda gr, t: placed.append("order"))     # nobody bids; nothing moves

g = Graph()
I.read(g, 'type desk:\n    kind_of = "desk"\n')
I.read(g, 'type funded_desk:\n    is a desk\n    cash >= 300\n')
asm.load_text(g, 'fn sell_rare(d: desk) -> funded_desk:\n    DISPATCH R(o) "sell" F(d)\n\n'
                 'fn sells_at_200(d: desk) -> funded_desk mocks sell_rare:\n'
                 '    ATTR R(c) F(d) "cash"\n    ADD R(c) R(c) 200\n    SET F(d) "cash" R(c)\n')
shop = g.mint("shop"); g.link("root", "has", shop)
d = g.mint("desk", kind_of="desk", label="desk", cash=120)
g.link(shop, "desk", d); TY.tag(g, d, "desk")

goal = I.read_goal(g, "goal raise_cash:\n    desk.cash >= 300\n")
r = D.carry_out(g, goal, T.open_thread(g), shop, attempts=3)
print("attempts:", r["tries"], "| irreversible orders actually placed:", len(placed))
```

```
attempts: 3 | irreversible orders actually placed: 3
```

**We think** `carry_out` is doing exactly what it documents, and the gap is one level up. Its docstring
is explicit and correct:

> *"Re-pursuing the goal is the only recovery that can mean anything, and it needs no new state because
> `pursue` opens a fresh workbench on the current real subject. Replanning is just going round the loop
> again."*

The reasoning holds. What is missing is that **going round again with identical inputs produces an
identical plan**, and the record of what just failed — `attempt.diverged`, already minted, already
readable, already carrying the step name — is not among those inputs. So the loop is not learning from
its own memory, which is unusual for this engine: everywhere else, the thing that just happened is data
the next step can read.

On a filesystem this is a wasted syscall. Here the third identical order is a third real order into a
market that has already refused two, and `loop.py` opens by saying the reversible/irreversible
asymmetry is *"the most important safety property in the design"*.

**Shapes we can see, smallest first — and the first may be all of it:**

- **Let the replan see the divergence.** `open_planning` already takes `allow=`. A pursuit that has a
  diverged attempt naming `sell_rare` could plan the next attempt with that operator excluded, or
  demoted, *for this pursuit*. That is data the pursuit already holds, and it needs no new concept.
- **Or: a repeated identical plan is itself a result.** If attempt *n+1* derives the plan attempt *n*
  just failed with, from a world that did not change, the honest outcome may be to stop and say so
  rather than spend the attempt budget discovering it — which is precisely the argument `loop.run`
  already makes for not spinning on a timer (*"stop rather than spending the rest of the budget
  discovering that again"*).
- ⚠ **What we do not want** is retry policy in the planner. Same instinct as your *"soft never"*
  warning: whether to try again is a decision the caller should be able to see and take, and our
  interest is in it being *visible* rather than automatic.

---

## 3. ⭐⭐ A value once known is known for ever — nothing re-observes, though the moment is recorded

**This is a design question, and it is the one we would most like an opinion on.**

**Measured.** The desk quoted a card at 200. The market moves 60 a trade. Three attempts later:

```
tools actually called: ('place_sell_order', 'place_sell_order')
one sale was planned to bring cash to: 320
the first sale actually brought it to:  260
the desk still believes the quote is: 200
the market is actually at:             80
```

`check_market` is registered `observes=True`, applicable to the subject, and sitting in the library. It
is never once called. `undetermined` asks only whether a slot is UNKNOWN, and a slot written once is
never undetermined again, so `blocked_on_ignorance` is `False` for ever after and the SENSING phase
cannot be reached.

⚠ **This scenario reports `done`, and that is the sharp end of it rather than a let-off.** The goal is
checked against reality, so the *outcome* is honest. The plan is re-derived against belief, so the
*reasoning* was wrong on every attempt — and it arrived only because an unplanned second order happened
to cover the gap. Nothing anywhere in the report says the numbers it planned with were four days old.

**We think** the missing half is already built, which is why we are asking rather than proposing.
`dispatch.service` stamps every observation with a moment, deliberately and with a comment explaining
why dating is not encoding; `clock.py` opens with *"everything observed or acted must have an absolute
timestamp"*; `forget.py` exists and sweeps. Every ingredient for *"this number is too old to plan
with"* is present. What is absent is anything that **consults** it — the staleness is recorded and
never read.

Three readings, and we genuinely do not know which is yours:

1. **Out of scope — a consumer decides freshness.** Perfectly defensible, and if so we would like it
   said, because the natural consumer implementation is *"call the look tool before pursuing"*, which
   puts a policy decision back in Python and re-creates a small `prohibitions()`. Given how §3 of the
   last round went, we would rather ask first.
2. **`undetermined` could be about confidence rather than presence.** A slot whose observation moment
   is older than some authored horizon is *effectively* unknown, and everything downstream —
   `blocked_on_ignorance`, SENSING, replanning — would then work unchanged. This is the shape we would
   pick, mostly because it adds no concept to the planner, exactly as `norm.apply` writing ordinary
   `never` constraints added none.
3. **It belongs to `forget.py`.** If an observation can age out of the graph entirely, the slot returns
   to UNKNOWN and the existing machinery does the rest. Cheapest of the three if the sweep can be given
   a per-slot horizon.

Whichever it is, the horizon must be **authored data** — *"a quote is stale after 15 minutes"* is
domain knowledge and belongs in a `type` or a `criterion`, not in a constant.

---

## 4. ⭐ Sensing considers only the pursuit's subject; planning searches *under* it — and the mismatch is silent

**Severity: medium-high, entirely because it is silent.** It cost us an afternoon, and we had already
read `_looker_for`.

**Measured.** The same world, the same goal, the same unknown. The only difference is whether the
pursuit's subject is the desk or the shop that holds it.

```python
from ugm import asm, dispatch as DP, driver as D, intake as I, loop as L, thread as T, types as TY
from ugm.graph import Graph, UNKNOWN

DP.register("count", lambda gr, t: gr.put(t, rares=5), observes=True)

def world():
    g = Graph()
    I.read(g, 'type desk:\n    kind_of = "desk"\n')
    asm.load_text(g, 'fn look(d: desk) -> desk:\n    DISPATCH R(o) "count" F(d)\n')
    shop = g.mint("shop"); g.link("root", "has", shop)
    d = g.mint("desk", kind_of="desk", label="desk", rares=UNKNOWN)
    g.link(shop, "desk", d); TY.tag(g, d, "desk")
    return g, shop, d

for as_container in (False, True):
    g, shop, d = world()
    goal = I.read_goal(g, "goal hold_three:\n    desk.rares >= 3\n")
    p = D.open_pursuit(g, goal, T.open_thread(g), shop if as_container else d)
    lp = L.open_loop(g); L.schedule(g, lp, p, why="x")
    out = L.run(g, lp, max_ticks=200)
    print(f"subject={'shop' if as_container else 'desk'}: sensed={g.attr(p, 'sensed')} "
          f"rares={g.attr(d, 'rares')} verbs={sorted({r['verb'] for r in out['did'] if r['verb']})}")
```

```
subject=desk: sensed=('look',) rares=5     verbs=['act', 'imagine', 'look']
subject=shop: sensed=None      rares=UNKNOWN verbs=['imagine']
```

**We think** both halves are individually right and the parameter is carrying two different meanings.
Planning searches *under* a subject — which is why our first probe passes the shop everywhere and is
correct to. Sensing selects *on* it: `_looker_for` walks `selection.candidates(g, subject)`, so a
container has no applicable single-parameter looker and can never look. Nothing is wrong with either
rule; what is wrong is that the same argument satisfies one and quietly fails the other.

And the failure is indistinguishable from a genuinely impossible goal:

```
why: 1 attempt(s) did not reach [desk.rares = 3]
```

That is the same silence as §1 of the last round, in a different place. Anything that names it would
do — a warning when a goal is `blocked_on_ignorance` and no looker applies **to the subject** while one
applies to something under it; or `_looker_for` searching under the subject the way planning does; or
simply saying so in `pursuit_report["why"]`. Our preference is the last one, because a refusal that
names the reason is worth more to a UI than a fix that guesses.

---

## 5. `blocked_on_ignorance` is all-or-nothing, and a desk is never wholly ignorant

**A design question, and closely related to §3 — an answer to one probably decides the other.**

**Measured.** Cash is known and short; stock is unknown. Nothing senses.

```
unmet        : ['desk.rares = 3', 'desk.cash = 300']
undetermined : ['desk.rares = 3']
blocked_on_ignorance: False
sensed: None
```

**We think** the current rule is well argued and we are not asking you to drop it. `goal.py`:

> *"The criterion for SENSE is that a plan bottoms out in ignorance, not that it touches it. A goal with
> one unknown slot and three genuinely false constraints still has world work to do; sensing on the
> strength of merely touching an unknown would make the system look in every box."*

Right — and the counter-case is not "look in every box", it is that **a real agent is permanently in the
mixed state**. A trading desk always knows its cash and never knows what the case is worth. Under
`all`, the box worth opening is never opened, and it is the *cheap* one: one observing dispatch,
reversible, against a slot the plan is about to reason over.

The distinction that seems to matter is not how many constraints are undetermined but **whether the
operator about to be chosen would act on an undetermined slot**. Looking in every box is choosing to
look with no bearing on the plan; looking at the number your next irreversible act depends on is not
the same act. Whether that is expressible in your frontier we cannot tell from outside — it may need to
know the operator before it can ask, which is the wrong order. If so, "no" is a fine answer and §3's
option 2 is the more promising direction anyway.

---

## 6. `ADD` is the only arithmetic, so a cost read from the world cannot be subtracted

**A scope question, and a sharper one than it looks.**

**Measured.**

```python
from ugm import asm, intake as I
from ugm.graph import Graph
g = Graph(); I.read(g, 'type desk:\n    kind_of = "desk"\n')
asm.load_text(g, 'fn pay(d: desk) -> desk:\n    ATTR R(c) F(d) "cash"\n'
                 '    ATTR R(q) F(d) "quote"\n    SUB R(c) R(c) R(q)\n')
```

```
line 4: unknown opcode 'SUB'. Known: ADD, ATTR, BACK, CALL, CLOSE, CONST, COPY, COUNT, DEREF, …
```

Same for `MUL`. A literal is the only operand that can be negative, so `cash -= ask` — where the ask is
a number *read from the world* — cannot be written. Our probe hardcodes the ask at 140 and the operator
silently stops being about the market it trades on. `position_value = count × price` is likewise
inexpressible.

**We think** this is worth a decision rather than a patch, because of which way it cuts against your own
rule. The standing discipline is *"Python for mechanism nothing reasons about; instructions for anything
that must be inspectable, generated, or learned"* — and a price, a fee, a spread and a margin are
exactly things a domain reasons about. The available workaround is a `NATIVE`, which puts domain
arithmetic in Python, and `native.py` is explicit that natives are substrate and their contents must not
be business. So the workaround is the thing the design forbids.

Two honest possibilities:

1. **`SUB` and `MUL` are simply missing** — three lines beside `ADD`, no new concept, and the closed set
   stays closed. `ADD` being alone reads like where the work stopped rather than a decision, and the
   opcode table is one of the places where "we chose exactly these" is otherwise very visible.
2. **Arithmetic beyond counting is deliberately out of scope**, and a domain that needs money should
   keep money outside the graph and let the tools compute it. Also coherent — but then a `mocks` cannot
   predict a numeric effect, and divergence on quantities stops being checkable, which costs §2's
   machinery its teeth in exactly the domains where acting is expensive.

We would rather have either answer than guess. If it is (2), a line in `docs/limits.md` would save the
next consumer the same afternoon.

---

## 7. `describe_constraint` renders every comparison as `=`

**Severity: low to fix, high in how often a human reads it.**

**Measured.** The operator is stored on the constraint and dropped when it is described.

```python
from ugm import goal as G, intake as I
from ugm.graph import Graph
g = Graph(); I.read(g, 'type desk:\n    kind_of = "desk"\n')
d = g.mint("desk", kind_of="desk", label="desk", cash=120); g.link("root", "has", d)
goal = I.read_goal(g, "goal raise_cash:\n    desk.cash >= 300\n")
c = G.constraints(g, goal)[0]
print("stored :", {k: v for k, v in g.attrs[c].items() if k in ("key", "op", "value")})
print("shown  :", G.describe_constraint(g, c))
```

```
stored : {'key': 'cash', 'op': '>=', 'value': 300}
shown  : desk.cash = 300
```

`goal.py:670` formats `{key} = {value!r}` unconditionally; `op` is right there on the node.

**We think** it is one line, and worth it because of where the string surfaces: it is what
`pursuit_report["why"]` says when a pursuit fails —

```
why: 3 attempt(s) did not reach [desk.cash = 300]
```

— which reads as *"we needed cash to be exactly 300"*. Comparison operators in goals are recent
(2026-08-02, per the last round's §8.4), so this is presumably just the renderer not having caught up.
Every one of our findings above quotes a `why` line, and every one of them misreports the goal.

---

## 8. What we are doing with this

The probe is `experiments/cards_market_desk.py`, twelve scenarios, and it runs in a couple of seconds.
Six are deliberately `stuck`, crashing or looping — they are the measurements above, and we would like
them to start failing. `python experiments/cards_market_desk.py` prints what each one measured.

We are **not** building a trading domain; it is an instrument, and if you would like a different one for
any of these we will build that instead. What we *are* taking from it is §0's third point: `verb_of`
answering *before* the step is the seam where a human sees the plan and decides whether an order goes
out, and that is the first screen in this repo worth building.
