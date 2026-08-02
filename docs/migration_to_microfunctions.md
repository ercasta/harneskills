# Migration — HarneSkills onto UGM's microfunctions engine

> **Status: ASSESSMENT + PROPOSED STRATEGY (2026-08-02).** Supersedes the "NEXT STEP" section of
> `docs/implementation_plan.md`, which is now historical: it plans Layer-2 work against an engine
> that no longer exists. Read this first.
>
> **Verdict: REBUILD, not port — and rebuild *beside*, in this repo, not from a blank one.**
> Reasoning below; the short version is that the upstream change deleted the execution model
> HarneSkills was built on, but *kept and absorbed* most of what HarneSkills used that model to build.
>
> **⭐⭐ SCOPE, RATIFIED BY THE USER 2026-08-02 — read this before anything else here.**
> **HarneSkills is a UI/UX layer over UGM. Nothing else.** UGM was carved out of HarneSkills
> *precisely to separate these concerns*, and the drift this document originally described — a
> harness owning planning banks, deontic arbitration, domain corpora and a code-property-graph
> stack — is that separation not having been finished, not a scope to restore.
>
> So the test for every item below is one question: **is this how a human sees, drives, or authors
> for UGM?** If not, it is not ours. That deletes more work than the engine change does — see §3a,
> which rewrites §3's conclusion and shrinks slice 2 to almost nothing.

---

## 1. What actually changed upstream

`../ugm` retired the `ugm/` package outright (and `units/` with it) and replaced it with
`microfunctions/` — ~3,600 lines, no dependencies, verified by `python -m microfunctions.selftest`
rather than pytest. From their `HANDOFF.md`:

> The bet was always **content as data**. It was never **pattern matching as the execution model**.
> Those two had been welded together since the beginning, and essentially all of this project's
> accidental complexity came from the weld.

Concretely, for us:

| old model | new model |
|---|---|
| production rules with `when` clauses, matched against the world | **nothing fires** — a rule is a typed function you *point at* arguments |
| forward chaining to a fixpoint (`run_rules`, `run_bank`, `stratify`) | backward chaining over **return types** into a lazy plan |
| open CNL: assertions, rules, universals, coref, determiners | a **closed 8-verb block CNL** — `goal`/`ask`/`why`/`plan`, `type`, `prefer`/`avoid`, `method`/`procedure`, `criterion`/`directive`, `what`/`where`/`when` |
| precondition/effect authored as facts (`X needs Y`, `X produces Y`) | precondition = **parameter type**, effect = **return type**; a rule is a cast |
| `ugm.world_model.Graph` — label-less attribute graph | `microfunctions.graph.Graph` — named edges, ordered targets, edge properties, reverse index, undo journal |

The two CNL-surface regressions we filed in `docs/ugm_surface_regressions.md` (determiner
normalization, `every X is a Y`) are **moot**: that whole surface is gone by design. That document
should be marked closed-as-obsolete rather than chased.

## 2. Blast radius, module by module

14 of our 16 `harneskills/` modules import dead APIs. Nothing imports today — the shared
`../ugm/.venv` no longer resolves `ugm`, `microfunctions`, `harneskills` *or* `textual`, so the suite
is **0-collectable**, not "24 passed / 38 failed" as the implementation plan records.

**Old imports, and whether anything succeeds them:**

| old import | successor |
|---|---|
| `ugm.world_model` (`Graph`, `WorldModel`) | `microfunctions.graph.Graph` — **different data model**, not a rename |
| `ugm.intake` (`ingest`, `converse`, `Outcome`, `Event`) | `microfunctions.intake` (`read`, `read_goal`, `respond`) + `thread.py` — different shapes |
| `ugm.cnl.query.ask` | `microfunctions.query.ask` / `settle` / `account` — different verdict shape |
| `ugm.dispatch`, `ugm.external` | `microfunctions.dispatch` — the one door effects leave by; re-derive, don't port |
| `ugm.production_rule` (`Pat`, `Rule`, `Firing`, `is_var`, …) | **none — deleted** |
| `ugm.cnl.authoring` (`run_rules`, `load_facts`, `load_rules`, `load_corpus`, `stratify`) | **none — deleted** |
| `ugm.lowering.run_bank` | **none — deleted** |
| `ugm.cnl.forms` (`FORM_RULES`, `tokenize`, `declared_*`) | **none — deleted** |
| `ugm.cnl.machine_rules.load_machine_rules` | **none — deleted** |
| `ugm.cnl.rule_graph`, `ugm.cnl.surface`, `ugm.cnl.universal` | **none — deleted** |

Every one of our 16 `corpus/*.cnl` files is written in the deleted language, and `PLANNING_RULES` /
`EXECUTION_RULES` / `TEARDOWN_RULES` / `SOLVE_RULES` / `DETECT_DIVERGENCE` / `REQUEST_RULES` /
`PROCEDURE_RULES` are rule banks in it too.

**This is why it is a rebuild and not a port.** Our standing rule — *domain logic ONLY in banks,
never in Python* — rode on pattern matching, exactly as pystrider's central bet did. A pointed
program cannot be run backwards, so the bank has no translation; it needs a new home.

## 3. The finding that should shape the plan: the engine absorbed most of HarneSkills

This is the important part of the assessment, and it is good news wearing bad news' clothes. Nearly
every subsystem we hand-built as a rule bank now exists upstream, by name, as a first-class feature:

| ours | upstream now |
|---|---|
| `planning.py` (591 lines) + `corpus/planning*.cnl` — plan/act/check/replan, divergence, teardown | `driver.pursue` / `carry_out`, `loop.py`, `execution.py` — divergence, resume, replan, contingencies |
| `planning_kb.py` — operators as `X needs Y` / `X produces Y` | a microfunction signature: `fn seal(j: jar) -> sealed_jar` |
| `procedure.py` + `corpus/procedure.cnl` — named compositions, gap-filling | the `method` / `procedure` verbs (`procedure` refuses rather than falling back to search) |
| `deontic.py` + `corpus/policy.cnl` — forbidden/encouraged, class scoping | `never f` / `never touch x` / `must f` goal constraints (now inherited down the goal ancestry), plus `prefer` / `avoid` guidelines and `criterion` / `directive` |
| `planning.rank_by_cost`, `_mint_chosen` — the ranked-commitment picker | `driver.relevance` + the frontier key + `criterion`'s `do f a = x` |
| `session.py` — recognition loop, contradiction detection, explain | `intake.respond` + `thread.py` + `query.settle` / `account`; `conflict.py` for contradiction and interference |
| `lint.py` — stratification checks | no strata to check; the closed CNL **refuses loudly** at intake, inside a savepoint |
| `interaction.py` — oracle, clarification | `dispatch.py` (the door) + the ask/purity bar |

`H-2`, `H-3`, and most of `H-4` in the implementation plan are therefore **not work items any more —
they are upstream features**. Continuing to build them here would be re-implementing the engine.

### So what is HarneSkills, after this?

Sharper and smaller, and it is exactly the two things our own README already claims:

1. **The SLM at the border** — fuzzy intent → CNL, and reading arbitrary tool output. The new CNL
   makes this *better*, not worse: "a model may write this text; the parser then accepts or refuses
   it deterministically." That is a free, exact grader for SLM output — a far stronger oracle than
   the fuzzy round-trip eval in `scripts/eval_nl2cnl.py`.
2. **The interactive authoring environment** — the TUI, the REPL, session/profile management, and
   domain KBs authored as data.

Plus the domain content and the measurement harness. That is a real product; it is just no longer
one that contains a reasoner.

## 3a. Re-scoped — HarneSkills is the UI/UX layer, and that is the whole of it

§3 above arrived at "the SLM border plus the authoring environment" by asking *what did the engine
not absorb?* The ratified scope reaches the same place by a better route — *what is a user interface
for?* — and then goes further, because the leftovers §3 was still holding are not ours either.

> **⭐⭐⭐ SHARPENED 2026-08-02 (same session, after the ratification below).** The user narrowed it
> once more, and this is the operative statement: **HarneSkills' main responsibility is simplifying
> INTAKE — autocompletion, the SLM, and everything else that makes UGM's closed CNL writable.**
> §3b is the reorientation; the three-part split below stands, but *authoring is primary and the
> other two exist to serve it*. Read §3b before planning any work.

**In scope. Three things, and they are all "how a human sees, drives, or authors for UGM".**

1. **Seeing.** UGM is unusually worth looking at: a plan is a path of frames, a search has a
   frontier and a refusal list, a `why` is a real derivation, a thread is materialised memory, and
   the graph is one uniform substrate all the way down. Today the only way to see any of it is a
   `print()` in a probe. ⭐ Our slice-0 experience is the argument: we could not tell a real result
   from a vacuous one until we rendered `refused` next to the plan, and that is a *presentation*
   problem, which is exactly our job. `driver.step` and `loop.tick` make a search pausable and
   inspectable mid-flight — that is a UI affordance upstream built and nobody has surfaced.
2. **Driving.** Sessions, threads, profiles, a REPL, a TUI. Opening a thread, posing a goal, watching
   a pursuit tick, seeing a divergence and choosing resume-or-replan. The plan-act-check loop is
   upstream's; presenting it and taking the human's decision is ours.
3. **Authoring.** Writing CNL and `.mf` with the parser's refusals rendered usefully — the refusal is
   upstream's, making it legible is ours. This is where the SLM sits: fuzzy intent → CNL is an *input
   method*, the way voice or autocomplete is, and the parser remains the sole authority on what is
   accepted. ⚠ It is worth being explicit that this is the reading under which the SLM stays in
   scope; if the user means UI/UX to exclude a model entirely, slice 5 drops and this document should
   say so rather than quietly keeping it.

**Out of scope, and this is the part that saves work.**

- **Domain content is not ours.** The corpora (cards, coffee, barista, policy, risk) stop being
  assets we maintain and become **demo fixtures for the UI** — the smallest thing that makes a screen
  worth looking at. We do not re-author 16 corpus files; we author roughly one.
- **⭐ The `prohibitions()` problem is not ours to solve.** Slice 0 found that defeasible norm
  arbitration has no home upstream and cost ~17 lines of Python. Under this scope we do not write
  those 17 lines *anywhere* — a UI layer arbitrating a policy would be precisely the concern-mixing
  the carve-out existed to end. It is now purely §7.2, an upstream question, and it is filed.
  This is the clearest evidence the re-scope is right: the one thing that did not migrate cleanly is
  also the one thing that was never ours.
- **No planning, no deontics, no reasoning of any kind.** Already true after the engine change; now
  it is a rule rather than an accident.
- **No code intelligence** — decided separately in §7.1, and this scope independently confirms it.

**What this changes downstream.** Slice 2 shrinks from "re-author the domain" to "one fixture good
enough to demo". The centre of gravity moves to slices 3 and 4, which were the tail of the plan and
are now the product. And the acceptance question for the whole migration becomes a UI question:
*can a person open a thread, pose a goal, watch it get planned, see why a branch was refused, and
author a fix — without reading `microfunctions/` source?* Nothing today can do that.

## 3b. Reorientation — intake is the product

**The responsibility, stated once:** UGM's CNL is *closed, and refuses*. That is upstream's central
design commitment and it is right — it is what makes a language model safe at the border, because
the parser is the sole authority on what is accepted. But it is also a brutal thing to write against:
every vocabulary is finite, unstated, and unforgiving, and a refusal is all you get. **HarneSkills
exists to close that gap.** Not to soften the refusals — to make the language *writable*.

⭐ **This is a better-defined product than "a UI over UGM", and it inverts what leads.** Seeing and
driving (§3a.1, §3a.2) do not go away, but they stop being ends: you render a plan **because the
author needs to know their text did what they meant**, and you run a goal **because that is the only
honest confirmation**. The loop is *write → validated → ran → saw → fix*, and every stage exists to
serve the first.

⭐⭐ **The closed grammar, which is what makes this hard, is also what makes it tractable.** Completion
for a general-purpose language is heuristic ranking over an open set. Here the set of legal next
tokens is **finite, enumerable and knowable**, so completion can be *exhaustive and correct* — a
guarantee no ordinary editor can offer. The property that makes UGM harsh to write is exactly the
property that makes tooling for it possible. That is the bet of this project, and it is a much more
interesting one than "put a TUI on it".

### The intake ladder — five rungs, in dependency order

1. **Live validation.** Parse-as-you-type, per block, with the verdict shown before submit.
   ✅ **Buildable today, verified** (`docs/feedback_microfunctions.md` §6): `read` is savepoint-scoped
   and never commits, so `savepoint()` → `read` → `rollback` gives an exact accept/refuse verdict and
   leaves **zero nodes** behind. This is the foundation and it needs nothing from upstream.
2. **Legible refusals.** Render the refusal *at the token*, with the legal alternatives for that
   position. The parser already reports line numbers and names the closed vocabulary; the work is
   presentation. ⚠ Our own feedback §2 is an instance of this — a diagnostic that blamed the wrong
   thing cost us minutes, and a user without the source has no recovery at all.
3. **Completion.** Verbs are free (`intake.VERBS` and the per-family tuples are exposed data). Body
   lines are **blocked on upstream** (feedback §6): the per-family forms exist only as display strings
   inside the raise sites, so completing inside a block means re-typing UGM's grammar into our repo
   with nothing checking it — the exact rot `cnl.md` warns about. **Asked for; do not build the copy.**
4. **Name resolution and picking.** The second refusal class, and the harshest: *nothing is called
   that* / *more than one thing is called that*. Both are knowable before submit. Ambiguity should be
   a **picker**, not a rejection — the engine still refuses, a human still chooses, and what gets
   written is unambiguous. **Partly blocked on upstream** (feedback §7): `resolve` knows the
   candidates and drops them to report a count (verified — the exception carries no attributes).
5. **The SLM, as a drafter.** NL → CNL draft, adjudicated by the parser. ⭐ The grader is now
   *deterministic* — accepted or refused, with a reason — so this becomes generate-validate-retry with
   the refusal fed back, instead of the fuzzy round-trip match `scripts/eval_nl2cnl.py` did. That is a
   strictly better training and evaluation loop than the one we had, and it is the rung that most
   justifies keeping a model in the project.

⚠ **Rungs 1, 2 and 5 are unblocked; 3 and 4 are waiting on two small upstream asks.** That ordering
is the schedule: build 1–2 now, 5 when the grammar settles, and 3–4 when the asks land. Do **not**
route around 3 by copying the grammar — a stale completion list teaching a wrong surface is worse
than no completion, and worse still if a model is trained on what it suggests.

### ⭐ The TUI is already the right shape, which was not guaranteed

Worth checking before planning around it, so: `harneskills_tui/screen.py` is a single-screen CLI —
`CommandInput`, `CommandSuggestions`, `?`-triggered completion, Tab-completion, a live
`TextArea.Changed` handler, and a multiline mode. It is **already an autocomplete-first authoring
surface**; what it completes against is stale, and the plumbing is not. That materially strengthens
§5's "stay in this repo" and re-points slice 4 from "restore a dashboard" to "re-point a completer".

### What this de-prioritises

Rendering the frontier, the thread, divergence resume/replan, pursuit dashboards — all still §3a.1
and all still ours eventually, but **none is on the critical path**. The minimum that closes the
authoring loop is: it parsed, it ran, here is the plan, here is why the alternative was refused.

## 4. What survives, what goes to the attic

⚠ **Revised for the §3a re-scope.** The original version of this section kept the corpora, the
benches and the Joern work as assets. Under a UI-only scope most of that is not ours, and the
surviving list is much shorter — which is the point.

**Survives (port or keep):**
- `harneskills_tui/` (~1,600 lines) — **the asset, and now essentially the product.** Textual layout,
  widgets, modals, profiles are engine-agnostic; what changes is its session backend and what the
  panes show.
- `harneskills/slm.py`, `slm_data.py`, `scripts/*` — the SLM as an *input method* (§3a, and gated on
  the scope question there). Constructs regenerate; the generator/eval structure holds.
- `harneskills/repl.py` — the other driving surface, and the cheapest way to exercise slice 3 before
  slice 4 exists.
- **One** corpus file, as a demo fixture — not the sixteen. See slice 2.
- `docs/` — as history; this file is the live plan.

**To the attic (`docs/attic/` precedent already exists):**
`planning.py`, `planning_kb.py`, `procedure.py`, `deontic.py`, `driver.py`, `kb.py`, `lint.py`,
`session.py`, `scenarios.py`, `interaction.py`, `cpg.py`, and the tests that pin them — plus, newly
under the re-scope, `bench/` and the 15 corpus files we are not keeping. None of it is deleted; the
attic is exactly so that "not ours to maintain" does not have to mean "gone".

⚠ **We do not keep the old suite as an oracle, and this is where we differ from pystrider.** They
kept `pystrider/` running beside `strider/` because the old suite was the only evidence the new code
did what the old one did. Ours cannot run at all — the engine under it is deleted from the repo. It
has zero oracle value, so keeping it live buys nothing. The corpora and the *documented scenario
outcomes* are the oracle instead.

## 5. Why not a fresh repo

The user asked whether rebuilding from scratch is easier. It is not — though ⚠ **the re-scope
narrowed this margin and the honest answer is now "barely"**, so it is worth restating rather than
inheriting.

The original argument was inventory: TUI, SLM, corpora, benches, Joern, history and docs, ~40% of the
line count, none of it invalidated. §3a disclaimed the corpora, the benches and the Joern work, so
that argument is mostly gone. What remains is narrower and still decisive: **`harneskills_tui/` is
~1,600 lines of Textual that a UI-only project would otherwise write again, first**, and under the new
scope it is not a surviving fragment — it *is* the product. Add the git history and the docs that
record why every one of these decisions was made, and staying is right. But it is right because of
the TUI, not because of a line count.

**So: same repo, new package beside the old one**, mirroring what ugm did to itself and what
pystrider did downstream. Working name `harness/`; `harneskills/` is moved to `attic/` in slice 1
rather than deleted, so git history and the docs' cross-references stay meaningful.

## 6. The plan

**Slice 0 — the decider probe. ✅ DONE 2026-08-02 — `experiments/cards_on_microfunctions.py`. VERDICT: GO.**
See §6a below for the results and the one thing it found.

**Slice 0, as originally specified —**
Take one domain we already know cold — the card trader (`corpus/cards_kb.cnl` + one scenario from
`corpus/cards_scenarios.txt`) — and re-express it entirely on the new engine: trading actions as
microfunctions in a `.mf` file, the KB shape as `type` blocks, the norms as `never`/`must` +
`prefer`/`avoid`, one scenario as a `goal` block, run through `driver.carry_out`. Measure two
things: **(a)** how much of the domain stays *data* rather than becoming Python — that is our
standing rule, and it is the actual bet under test; **(b)** how the answer compares to the recorded
old-generation outcome, under the 2026-07-10 ratification (different-but-sensible is fine;
nonsensical is a bug). Deliverable: `experiments/cards_on_microfunctions.py` + findings written
here. **This is a go/no-go, and it sizes every slice after it.** Half a day to a day.

## 6a. Slice 0 results — the card trader on microfunctions

`python experiments/cards_on_microfunctions.py`, against `universal-graph-machine` 0.3.0 installed
editable from `../ugm`. **9 of 9 scenarios reproduce their recorded outcomes**, including the two-step
plan (`buy_at_shop` → `sell_rare`), the honest `stuck`, the risk cut, and both halves of the
soft/hard distinction.

```
acquire_default              done   plan=('buy_at_shop',)                refused=('counterfeit_card',)
cautious_no_buying           done   plan=('trade_at_club',)              refused=(buy_at_shop, buy_online, counterfeit_card)
hold_the_line                stuck  plan=()                              refused=(counterfeit_card, sell_rare)
sell_today                   done   plan=('buy_at_shop', 'sell_rare')    refused=(counterfeit_card)
law_holds                    done   plan=('buy_at_shop',)                refused=(counterfeit_card)
play_it_safe                 done   plan=('buy_at_shop',)                refused=(buy_online, counterfeit_card, trade_at_club)
prefer_encouraged            done   plan=('trade_at_club',)              refused=(counterfeit_card)
demote_discouraged           done   plan=('trade_at_club',)              refused=(counterfeit_card)
discouraged_is_last_resort   done   plan=('buy_at_shop',)                refused=(counterfeit_card, trade_at_club)
```

⚠ **Refusals are printed on success too, and that is not decoration.** Four scenarios land on
`buy_at_shop`, which is also what a wholly unconstrained day picks — so the plan alone cannot tell
"the norm pruned the alternatives" from "nothing happened and the default won". The refusal list is
what makes each of those a real result. Likewise `demote_discouraged` exists only as the contrast that
makes `discouraged_is_last_resort` mean something: same advice, nothing banned, and the plan must move
*off* the default. The pair proves both halves — advice reorders, and `avoid` still yields to necessity
instead of excluding the way `never` does.

**What the engine gave us for free.** Backward chaining found the two-step cash plan with no planner
of ours involved; `never` pruned and reported *why*; goal constraints and guidelines both landed
straight off the CNL. `planning.py`'s 591 lines, `planning_kb.py`'s 168, and `corpus/planning.cnl`
have no successor here because they have no job.

**Measurement (a) — how much stayed data.** The causal domain is **21 authored lines** — four `type`
blocks and five `fn` signatures — against **1,190 lines** of Python and CNL that carried the same
domain before. The operator surface is the clearest win: `buy_at_shop needs money` / `buy_at_shop
produces have_rare_card` were two facts a rule bank had to interpret; they are now the parameter type
and the return type, read off the stored body by the engine, with nothing interpreting them.

**⚠ The one place the bet did NOT survive: defeasible norms.** `prohibitions()` in the probe is
**~17 lines of genuine arbitration logic in Python** — standing norms, today's instructions, the
`outranks` table, and the risk alpha-cut, composed into `never` lines before the goal is even built.
That was `corpus/policy.cnl` + `corpus/risk.cnl` before, as rules, and the override was *auditable*:
`why is buy not excluded` traced to the outranking encouragement. It is now opaque Python, and no
upstream verb can hold it — `never` prunes absolutely, `prefer`/`avoid` can only reorder (by explicit
design), and `criterion` selects an action rather than banning one.

This is a **real and bounded** loss: one function, on the authoring path, not in the planner. It does
not change the GO verdict, and it sharpens open question §7.2 from "worth a written question" into a
specific upstream ask — *is there a place for a defeasible prohibition, or is composing it at
authoring time the intended answer?* Worth asking before slice 2 commits to a shape, because if the
answer is "compose it yourself" then that composition should at least be **data the harness reads**
rather than a Python function, and that is a design decision, not a detail.

**Two smaller findings, both recorded in the probe:**
- `intake.read` reads **one block per call**; a multi-block string is refused at the second header.
- Guidelines are consulted **only** through `pursue(..., rank=guideline.ranker(g))`. Omit it and
  `prefer`/`avoid` parse cleanly, sit in the graph, and silently say nothing. That cost this probe one
  wrong answer before it was wired, and it is exactly the failure mode the closed CNL exists to
  prevent — worth reporting upstream, since the refusal discipline stops at the parser here.

**Slice 1 — the seam and the skeleton.**
`harness/mf.py` as the single import surface onto `microfunctions` (pystrider's `strider/mf.py`
pattern — one file absorbs upstream churn, which given a CHANGELOG this active is not optional).
`harneskills/` → `attic/`. `pyproject.toml`: bump the `universal-graph-machine` floor to `>=0.3.0`,
drop the `[asp]` extra (gone upstream), retarget `packages`. Rebuild a venv that actually resolves
`microfunctions` + `textual` — today none does. Pin upstream by **version, not by branch**, and
watch `../ugm/CHANGELOG.md`, which exists precisely because a consumer's pin went red.

**⚠ Slices 2–6 were written before the §3a re-scope and the §3b reorientation, and are restated
accordingly.** Slice 2 mostly evaporates; the weight moves to 3 and 4. ⭐ **Under §3b the ORDER also
changes: the first thing built is the validator, not the session.** Rung 1 of the intake ladder needs
nothing but a graph and `intake.read`, so it can land before any session exists — and it is the piece
every other rung stands on. Build it first, and let the session be shaped by what the editor needs
rather than the other way round.

**Slice 2 — ONE demo fixture.** *(was: "the domain, re-authored")* The card trader from slice 0 is
already it — 21 lines of `type` + `fn`, and it plans. Promote it out of `experiments/` into a
fixture the UI can load, and stop. We do **not** re-author coffee/barista/policy/risk: domain
content is not ours (§3a), and one fixture that exercises plan, refusal, `why` and a two-step chain
shows every screen we need to build. ⭐ Deliberately excluded: the `prohibitions()` arbitration from
slice 0 — the fixture keeps whatever `never` lines it needs as *authored text*, and nothing in
`harness/` composes them.

**Slice 2.5 — ⭐ THE VALIDATOR (new, and it comes before the session).** `harness/intake.py`: the
savepoint/rollback `check()` verified in feedback §6, plus refusal parsing into something a UI can
place — line, offending text, which closed vocabulary, and the legal forms for that position where we
can get them. Rungs 1–2 of the ladder. **Depends on nothing but `microfunctions.intake` and a
`Graph`**, so it needs neither the session nor the TUI, and both are easier to design once it exists.
⚠ Pin its refusal-message parsing behind one function — those strings are not an API, and upstream
may well improve them (we asked them to). Testable in plain pytest against a corpus of good and bad
blocks, which makes it the first thing here with a real suite since the split.

**Slice 3 — the session.** `harness/session.py` over `intake.respond` +
`thread` + `loop.tick`. The contract this exposes is the whole design problem of the project, because
everything a screen can show is decided here. It must surface, as first-class results rather than
strings: the **verdict** (`yes`/`no`/`unknown` — three, and the third is not a failure), the **plan**
with its bindings, the **refusals with their reasons**, the **derivation** behind a `why`, the
**thread**, and a **divergence** with its resume-or-replan choice. ⚠ Design it against
`driver.step` / `loop.tick` — one primitive step at a time — not against `pursue`/`carry_out`, which
run to completion and leave a UI nothing to render mid-flight. Retro-fitting a streaming surface onto
a blocking one is the mistake the old plan was about to make with `converse`.

**Slice 4 — the TUI, re-pointed at the validator.** Not "restore a dashboard": `screen.py` is already
an autocomplete-first CLI (§3b), so the work is wiring `CommandInput` / `CommandSuggestions` to slice
2.5 and rendering refusals where the caret is. Rung 2 becomes visible here. The acceptance question
from §3a lands here too, but the *first* question is narrower and comes sooner: **can someone write a
valid `type` block they did not already know how to write?**

**Slice 5 — completion and picking (rungs 3–4). ⚠ BLOCKED on upstream.** Body-line completion needs
the per-family forms as data (feedback §6); the ambiguity picker needs `resolve` to carry its
candidates (feedback §7). Both asks are filed and both are small. ⚠ **Do not route around either by
copying the grammar into this repo** — a stale completion list teaches a wrong surface, and if slice 6
trains on what it suggests, the error compounds. Verb-level completion is unblocked and can ship in
slice 4.

**Slice 6 — the SLM, as a drafter.** New `CONSTRUCTS` against the current grammar, and — the real
change — the eval becomes **generate → `check()` → retry with the refusal as feedback**, using slice
2.5. Deterministic accept/refuse replaces the old fuzzy round-trip match, which is a strictly better
loop than we ever had. ⚠ **Gate on CNL stability**: `criterion`/`directive` and the `type` schema
language landed 2026-08-01/02 and upstream still lists open slices; training early buys the debt
`H-1` recorded. ⚠ **And gate on slice 5** — training a drafter before completion is settled means the
model and the editor teach different surfaces.

**Slice 7 — docs and close-out.** Rewrite `docs/implementation_plan.md` around this document; mark
`docs/ugm_surface_regressions.md` obsolete (done — see `docs/feedback_microfunctions.md` §4).
⚠ The `README.md` architecture diagram now describes a system that does not exist and claims a scope
we have just disclaimed; it needs rewriting to "a UI over UGM", not patching.

**Verification.** Keep pytest here — upstream dropped it because 92 of 94 files tested the deleted
engine, which is their reason and not ours. ⚠ The grade changes with the scope: the old benches
measured *reasoning quality*, which is upstream's to measure now. Ours measures **whether the
interface tells the truth about the language** — starting with slice 2.5's corpus of blocks that must
be accepted and blocks that must be refused, which is a real suite and the first one this repo will
have had since the split. ⭐ The eventual product metric follows from §3b and is worth naming now:
**how many attempts does it take a person to write a block they did not already know how to write?**
That is what an intake layer is for, and nothing we have ever measured here has measured it.

## 7. Open questions

1. ~~**CPG scope.**~~ **DECIDED 2026-08-02: dropped entirely.** Code reasoning leaves HarneSkills'
   scope and `../pystrider` owns it — it is already doing this on the new engine with a worked-out
   pattern (`strider/patterns.py`: recognition as *casts* over existing nodes, so provenance
   survives). `harneskills/cpg.py`, `bench/cpg_scaling.py`, `bench/joern_corpus.py` and the three
   `test_cpg_*` / `test_joern_*` files go to the attic in slice 1 and are **not** rebuilt. This also
   retires `H-6` and the live-Joern test fragility risk outright. ⭐ Consequence for the sharper
   product statement in §3: HarneSkills is the SLM border + the authoring environment, and nothing
   about code.
2. **Defeasible priority is a real gap — now measured, see §6a.** `outranks` — a transient advice
   defeating a standing norm by source rank — has no home upstream: `never` prunes absolutely,
   `prefer`/`avoid` can only ever reorder by explicit design ("advice quietly becoming a correctness
   rule" is the thing they built it to prevent), and `criterion` names an action to take rather than
   one to ban. In the probe it cost **~17 lines of Python on the authoring path**, replacing rules
   that used to be auditable. **Ask upstream before slice 2**, and phrase it as the two-part question
   it is: is a defeasible prohibition in scope at all, and if the answer is "compose it at authoring
   time", should that composition be data the harness reads rather than a Python function?
3. **SLM timing** — retarget now against a moving grammar, or hold until the upstream handoff's open
   slices close? (Recommendation: hold; do slice 0–4 first.)
4. **`converse` / streaming.** The old plan wanted the non-blocking generator for the TUI's live
   event stream. `loop.tick` + `driver.step` (one search iteration, pausable and inspectable) is the
   new shape for that, and it is strictly better. Worth designing into slice 3 rather than bolting
   on later.
