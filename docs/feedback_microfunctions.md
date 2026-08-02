# Feedback from HarneSkills — the `microfunctions` engine

Collected 2026-08-02 while assessing HarneSkills' migration onto `microfunctions/`. Engine at
`581de14`, `universal-graph-machine` 0.3.0, installed editable, Python 3.13, Windows. Same spirit and
format as `../pystrider/docs/feedback_microfunctions.md`: every item has a minimal repro that imports
**only** `microfunctions`, ordered by what it would be worth to us.

**Stated as hypotheses, not findings.** We reason from the outside. Each item separates *what we
measured* — a repro output we stand behind — from *what we think it means*, which you should check.

⚠ **Measured against your WORKING TREE, not `581de14`.** Our editable install resolves from source, and
your tree had uncommitted modifications to `guideline.py`, `intake.py`, `criterion.py`, `method.py`,
`goal.py`, `thread.py` and `cnl.md` when we ran. Since §1 and §2 are about `guideline` and `intake`
specifically, that is worth knowing in both directions: they are **not** already fixed in your
uncommitted work, and if you are mid-change on either, these may be about something you are already
moving.

**Context, and it has changed.** HarneSkills is being re-scoped to what it was always meant to be
after the carve-out: **a UI/UX layer over UGM** — a TUI, a REPL, session and profile management, and a
language model at the border turning fuzzy human intent into your CNL. It owns no reasoning and no
domain. That makes us a different kind of consumer from pystrider: we lean on `intake`, `query`,
`thread`, `loop` and the *diagnostics*, and barely at all on `isa` or `establishes`. Most of this
document is therefore about the **border** — which is the surface you have most deliberately closed,
and where a UI has to render every refusal to a human who did not write the parser.

Evidence base: `experiments/cards_on_microfunctions.py` in our repo — the card-trader domain from our
old corpus, re-expressed on the new engine. **9 of 9 scenarios reproduce their recorded outcomes.**

---

## 0. What worked, because a bug list is a biased sample

Worth saying plainly, since we are about to list three problems and you cannot tell from a defect
report whether the thing is any good.

- **The signature *is* the causal knowledge, and that removed a whole layer of ours.** `buy_at_shop
  needs money` / `buy_at_shop produces have_rare_card` were two authored facts a rule bank had to
  interpret. They are now `fn buy_at_shop(t: funded_trader) -> card_holder`, read off the stored body,
  with nothing interpreting them. Our causal domain went from **1,190 lines** of Python and CNL to
  **21 authored lines**. Backward chaining then found a two-step plan we used to run a 591-line
  planning module to get.
- **`refused` is what made our results honest.** Four of our nine scenarios land on the same operator
  an *unconstrained* run picks, so the plan alone cannot distinguish "the norm pruned the
  alternatives" from "nothing happened and the default won". Being able to read what was refused, and
  why, is what turned those from vacuous passes into results. We would not have caught the problem in
  §2 without it.
- **The CHANGELOG did its job.** We pinned `>=0.3.0` and read the migration notes to size the work
  rather than bisecting. The `types.attrs_of` entry in particular told us in one line what a shape
  change cost a consumer. It is worth the sentence per change.

---

## 1. ⭐ A guideline is silently inert unless the caller passes `rank=` — the one that cost us a wrong answer

**Severity: high for us**, because it is a *silent* wrong answer on the surface a language model writes
to, and that is the exact failure mode the closed CNL exists to prevent.

**Measured.** A `prefer` block parses, mints a `guideline` node, sits in the graph — and changes
nothing, unless `pursue` was called with `rank=guideline.ranker(g)`. Same graph, same goal, same
advice; only the call differs:

```python
from microfunctions import asm, driver as D, guideline as GL, intake as I, thread as T, types as TY
from microfunctions.graph import Graph

def world():
    g = Graph()
    I.read(g, 'type thing:\n    kind_of = "thing"')
    I.read(g, 'type done_thing:\n    is a thing\n    done = true')
    asm.load_text(g, 'fn alpha(t: thing) -> done_thing:\n    SET F(t) "done" true\n\n'
                     'fn beta(t: thing) -> done_thing:\n    SET F(t) "done" true\n')
    box = g.mint('box'); g.link('root', 'has', box)
    it = g.mint('thing', kind_of='thing', label='it')
    g.link(box, 'thing', it); TY.tag(g, it, 'thing')
    return g, box

for wired in (False, True):
    g, box = world()
    verb, gl = I.read(g, 'prefer beta:\n    action beta\n    because we like it')
    goal = I.read_goal(g, 'goal finish:\n    it.done = true')
    kw = {'rank': GL.ranker(g)} if wired else {}
    r = D.pursue(g, goal, T.open_thread(g, 't'), box, **kw)
    print(('rank= PASSED' if wired else 'rank= OMITTED'), '->',
          D.plan_bindings(g, r['plan'])[0][0], '| node kind:', g.kind(gl))
```

```
rank= OMITTED -> alpha | node kind: guideline
rank= PASSED  -> beta  | node kind: guideline
```

**We think:** this is the one place the refusal discipline stops at the parser. Everywhere else in
this engine, authored text that will not do anything is refused loudly — a guideline naming neither an
action nor a thing, a type demanding nothing, a method with no steps. Here the text is *accepted*, the
node is *built*, and the advice is inert because of a keyword argument at an unrelated call site the
author never sees. From the outside it is indistinguishable from the advice being consulted and
losing, which is a legitimate outcome — so there is nothing to notice.

We are not proposing you make `rank=` implicit; the composition is presumably deliberate and a caller
may want its own ranker. Two smaller shapes would each have saved us:

- `pursue` warns (or refuses) when guidelines exist in the graph and no ranker was supplied — "3
  guidelines declared, none consulted; pass `rank=guideline.ranker(g)`".
- or `intake.read` returns something that says "this is inert until you wire it", so the border stays
  the one place a consumer must look.

⚠ We hit this through the CNL, which is the path you have said a language model will write. A model
that emits a perfectly good `prefer` block and sees no effect has no way to tell it was ignored.

---

## 2. A multi-block `read` is refused with a diagnostic that blames the wrong thing

**Severity: medium.** Cheap to fix, and it is on the border a human reads.

**Measured.** `intake.read` takes one block per call — documented in `cnl.md` §0, and we accept the
design. But a second, *well-formed* block header is reported as though its **content** were outside the
closed vocabulary, identically to actual garbage:

```python
from microfunctions import intake as I
from microfunctions.graph import Graph

g = Graph()
try:  I.read(g, 'type a:\n    x = 1\n\ntype b:\n    y = 2\n')
except Exception as e: print('MULTIBLOCK:', e)

g2 = Graph()
try:  I.read(g2, 'type a:\n    frobnicate the widget\n')
except Exception as e: print('BADLINE  :', e)
```

```
MULTIBLOCK: line 4: cannot read 'type b:' — the type vocabulary is closed (is a T | has <count> ...)
BADLINE  : line 2: cannot read 'frobnicate the widget' — the type vocabulary is closed (is a T | ...)
```

**We think:** the two cases deserve different messages, because the corrective action is completely
different — "you wrote a line I don't have a form for" versus "you passed me two blocks and I take
one". The parser already knows it is looking at a line matching `^\w+ .*:$` at zero indent, which is a
block header and never a body line. Naming it — *"'type b:' looks like a second block; `read` takes
one block per call"* — is a one-line diagnostic that turns a puzzling refusal into an instruction.

This cost us minutes rather than hours, but every consumer feeding you authored files will hit it on
their first multi-block file, and a UI has to render this message to someone who has never seen
`intake.py`.

---

## 3. ⭐⭐ The design question: is there a home for a DEFEASIBLE prohibition?

**Not a bug — a question, and the only thing our probe found that did not survive the move.**

**What we measured.** Re-expressing our card-trader domain, everything landed as data except norm
arbitration, which became **~17 lines of Python** on the authoring path. The domain has three
standing pieces:

- standing house norms of differing strength — `don't sell` (a default stance), `law never counterfeit`
  (inviolable);
- transient daily instructions — `today it is good to sell`;
- an authority ranking — `today outranks standing`, and **nothing outranks `law`**.

So `don't sell` normally prohibits, and is *defeated* when a higher-ranked source says otherwise —
while the law norm stands no matter what the day says. Both behaviours are load-bearing, and both
reproduce correctly on your engine. But they reproduce because our Python composed the `never` lines
before building the goal, and we can find no place upstream for that composition:

| | why not |
|---|---|
| `never f` | prunes absolutely — correct for `law`, wrong for a defeasible default |
| `prefer` / `avoid` | can only ever reorder, deliberately — "advice quietly becoming a correctness rule" is what you built it to prevent, and we agree |
| `criterion` / `directive` | names an action to **take**; there is no `do not` |

The loss is specific: it used to be **auditable**. Our old engine answered *"why is buying not
excluded?"* by tracing to the outranking encouragement, because the override was rules over facts.
It is now opaque Python that runs before your engine sees anything.

**We think** — and this is genuinely a question, since the answer may well be "out of scope":

1. **Is a defeasible prohibition in scope for this engine at all?** A principled "no" is a fine
   answer, and we would rather have it stated than discover it later. Your `never`/`avoid` split is
   sharp and we do not want it blunted to accommodate us.
2. **If the answer is "compose it at authoring time"** — which is what we did, and it works — then the
   follow-up matters more than the first question: *should that composition be data your engine reads,
   rather than each consumer's Python?* Every consumer with policy of differing strength will write
   this same function, differently, and its reasoning will be invisible to `why`.

⚠ **Flagging one shape we thought of and do not want**, in case it is tempting: a "soft never" that
prunes unless outranked would put arbitration inside the planner, and we think that is the wrong
place — the whole reason our version works is that arbitration happens *before* the goal exists, when
all the norms are in hand and none of them is about a search state. If anything belongs upstream it is
a way to **author** the arbitration, not a fourth force in the frontier.

---

## 4. Housekeeping — `ugm_surface_regressions.md` is obsolete, please close it

We filed `docs/ugm_surface_regressions.md` on 2026-07-12 against `08cc3c8`: determiner/multiword-NP
normalization missing from the intake path, and `every X is a Y` recognizing but not deriving.

**Both are moot** — that CNL is gone by design, and the surface they were about no longer exists.
Neither needs triage. Closing them explicitly so they do not sit in your queue looking open, and so
nobody spends an afternoon reproducing a regression against a deleted parser.

---

## 6. ⭐⭐ Expose the per-family body-line FORMS as data, so completion cannot rot

> **§6 and §7 were added 2026-08-02, after our scope sharpened, and they are now our highest-value
> asks — above §1.** HarneSkills' job is **making your intake surface writable**: autocompletion, a
> language model drafting CNL, live validation, name pickers. Everything below follows from that one
> responsibility, and both items are small.

**The good news first, because it is most of the story.** We can already build live validation with
**no change from you**, and it is the foundation of everything we want to do:

```python
def check(g, text):
    """Parse WITHOUT committing — the verdict a live editor needs, leaving nothing behind."""
    sp = g.savepoint()
    try:                 return True, I.read(g, text)[0], None
    except Exception as e:  return False, None, str(e)
    finally:             g.rollback(sp)
```

```
VALID   'type car:' | type
REFUSED 'type bad:' | line 2: cannot read 'frobnicate it' — the type vocabulary is closed (…)
REFUSED 'goal g:'   | line 2: nothing here is called 'a'
nodes before/after: 0 0  -> speculative parse left 0 nodes
```

⭐ That works because `read` is savepoint-scoped and never commits — a property you built for
*failure* which turns out to make **parse-as-you-type** safe and free. Worth knowing that a consumer
is depending on it; we would like it not to become a commit.

**What we cannot do without you.** Completion needs the legal *next* forms, per family. `VERBS`,
`GOAL_VERBS`, `TYPE_VERBS`, `CRITERION_VERBS` are all exposed as data — thank you, verb completion is
free. But the **body-line** vocabularies exist only as display strings inside the error paths:

```python
_SHAPE_FORMS = "x l y | x l+ y | x.k = v | x.k known | x is a T | x is there"    # intake.py:245
# ...and four more, inline in the raise sites at 469, 484, 584, 664
```

To complete inside a block we must re-type all six vocabularies into our code — a second copy of your
grammar, in another repo, with nothing checking it. `cnl.md`'s own opening says why that is a bad
idea: *"documentation that is merely checked by a human rots exactly like a comment does"*, and it
says so about a module docstring that had already gone stale on a whole verb family.

**We think:** a module-level mapping — `FORMS = {"goal": (...), "type": (...), "criterion": (...)}` —
with the raise sites rendering *from* it. Then the error message and the completion list are the same
object, your `check_the_CNL_GUIDE_parses` self-test covers both, and a new form appears in our UI the
day you ship it rather than the day we notice. Machine-readable shape is better than the current
prose (`x l y | x.k = v`), but even the strings as a dict would be a large improvement on us copying
them.

⚠ We are **not** asking for a parser API, an AST, or partial-input parsing. Just the closed sets you
already have, reachable by name.

---

## 7. ⭐ `resolve` should carry its candidates on the ambiguous refusal

**Severity: high for us, tiny for you** — and there is precedent, since you did exactly this for
pystrider's unresolved-roles case (their §3).

**Measured.** `intake.resolve` refuses both ways, correctly:

```
nothing here is called 'a'
'salt' is ambiguous — 2 things are called that; a name is not an identity
```

The second is the harshest refusal on the surface, and it is the one where the system **already knows
the answer set** — `hits` is right there in the frame — and drops it to report a count.

**We think:** attach them to the exception (`e.candidates = (...)`, or a small `Ambiguous(Unreadable)`
subclass). For us that is the difference between telling a user *"'salt' is ambiguous, 2 things are
called that"* and showing them the two things so they can **pick one**. A closed language refusing an
ambiguous name is exactly right; a UI that then makes the human guess which two nodes it meant is not.

⚠ This does **not** weaken "never identify by name alone" — the engine still refuses, and the
disambiguation is a *human* choosing, above the border, which then writes an unambiguous reference.
That is the same division you draw for a language model: we may draft, your parser decides.

---

## 5. Small notes, no action requested

- `pursue`'s report says `found`; `carry_out`'s says `done`. Both read naturally in place; we mention
  it only because we wrote `report["done"]` against `pursue`, got `None`, and read it as "stuck" — our
  bug, and a two-minute one, but the failure was silent rather than a `KeyError`.
- `plan_bindings` versus `plan_steps` — your docstring already warns about the shadowing that bit
  pystrider. It was the first thing we looked for and the warning was where we needed it. Thanks.
- Retiring pytest for `selftest` is clearly right for you and we are not adopting it — our layer is a
  TUI over a library, where the interesting failures are interaction shapes rather than engine
  invariants. Noting it so a difference in verification style does not read as drift.
