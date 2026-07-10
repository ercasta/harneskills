# The Harneskills Vision — Applying the Substrate to Code, Business Semantics, and SLMs

> **Status: CANONICAL DIRECTION (2026-07-04).** Companion to `docs/vision.md` (the
> one-substrate philosophy) and `docs/architecture.md` (the engine as built). Where
> `vision.md` says *what the substrate is*, this document says *what we point it at
> and why* — the outward-facing application arc: reasoning over code, over business
> semantics, and serving small language models (SLMs) in agentic settings. 

Every section below is a consequence of one commitment carried over from `vision.md`:
**reasoning, parsing, and pattern-matching over code are the same operation — matching
typed tuples against a pattern with variable binding — so there is one substrate and
one engine, and everything else is either a *surface* onto it or a *calculator* beside
it.**

---

## 1. The substrate is the reasoner the field keeps re-deriving

Strip the Socratic scaffolding from the discussion and it lands on five claims. We
have built four of them:

| Independently-derived conclusion | harneskills as built |
|---|---|
| One relational substrate; "parsing and reasoning are the same operation = matching typed tuples with variable binding" | The one-substrate vision. `rewriter.py` matching *is* this. |
| CNL is surface syntax; reason on the graph; render to CNL only for humans (the Attempto ACE/RACE layering) | Already the design: `forms.py` → graph → answer. Nobody runs the reasoner on the English string. |
| Concepts = opaque frame IDs + typed role-edges, reified as `holds(frame, role, filler)` triples | Our `S P O` triples with predicate-as-name + `is_a` typing **are** reified role-triples. |
| Tools as calculators on opaque nodes: scope a region, hand it to a specialized engine, fold results back | `dispatch.py` materialized `<call>`. This is the integration seam for §3 and §4. |
| Two engines over the substrate: graph-pattern (topology) **+ ASP (closure / defeasibility / model enumeration)** | We have **one** engine. This is the only real gap — see §3. |

So the strategic posture is **not** "adopt clingo / Neo4j / GrGen / ACE." It is the
same logic the discussion applies to ACE itself: *since you already own the parser and
the substrate, target them directly; do not bolt on a foreign formalism that reopens a
seam.* The substrate already realizes the thesis. External systems enter only as
scoped calculators (§3) or as fact producers (§4), never as the engine.

**On typing.** The discussion assumes *typed* frames with named roles; we chose
*untyped edges* (deliberately — the quantification-vs-typing decision). These do not
conflict: a predicate-name plus an `is_a` fact carries the "type," satisfying the
"typed, not string-labeled" requirement. The one place to be deliberate is code:
define a small explicit **frame ontology** as `is_a`-typed nodes with named-predicate
roles (§5). That is where untyped-substrate and typed-frame meet without a seam.

---

## 2. The boundary is the only place a model lives

An agentic system cannot demand its environment speak CNL back to it. The discussion's
central architectural line — validated against belief-revision benchmarks showing
models (especially small ones) *fake* defeasible reasoning via surface pattern-matching
and collapse on deep rule-conflict chains — is:

**Inside the controlled surface, symbolic reasoning replaces the model entirely
(determinism, auditability, no pattern-matching masquerading as inference). A model
lives ONLY at the boundary.**

Concretely, the model (an SLM — see §9) does exactly two jobs, both irreducibly
open-world:

- **Fuzzy intent → CNL.** Turning "make checkout handle partial refunds better" into a
  well-formed CNL statement. A closed grammar cannot parse phrasing it was never given;
  hand-authoring coverage for arbitrary human phrasing is the Cyc knowledge-acquisition
  bottleneck. This is the model's job by construction.
- **Reading arbitrary tool output** — error messages, stack traces, API responses,
  legacy code with no provenance to our rules. Unconstrained text understanding, full
  stop.

Everything else — parsing the CNL, unifying against the KB, defeasible arbitration,
graph rewriting into code, pattern / anti-pattern matching, comprehension via
provenance — is the substrate. The line is **the boundary of what is controlled**, not
an arbitrary preference. Inside it, a model was never earning its keep; dropping it is
a clear win. Outside it, the open long tail is exactly what neural interpolation was
built for and symbolic systems have never solved.

This is the whole value proposition for SLMs: they are weak precisely at multi-step
defeasible reasoning, which is exactly where the substrate is strong. **harneskills is
the symbolic exoskeleton that lets a small model reason far above its own weight** by
carrying the part it cannot do.

---

## 3. One engine is primary; external reasoners are scoped calculators

Our engine already does both jobs the discussion assigns to an external ASP solver:
forward-chaining fixpoint = closure; `decide` / `completion` / `defeat` / `retraction`
as rules + CWA-default with a per-predicate OWA opt-in (`decision-cwa-default`) = defeasibility. The engine *is* the substrate thesis
realized. A foreign reasoner is not.

There are exactly three things our stratified, single-fixpoint engine cannot express
and an ASP solver (clingo) uniquely can:

1. **Multiple stable models / world-splitting** — we compute one fixpoint; ASP
   enumerates all models.
2. **Constructive disjunction & "exactly-one"** — case analysis / covering axioms
   (the "hardest" item already on the roadmap; it strains the monotone fact layer).
3. **Optimization** — weak constraints / `#minimize`: cheapest consistent set,
   configuration, scheduling.

(The genuinely non-stratifiable negation cycles we already deliberately refuse belong
here too, but that refusal is a standing design choice, not a gap to close casually —
`vision.md` §11.)

**Decision: do not adopt clingo as the engine. Expose it as one more materialized
`<call>` calculator** (a `dispatch.py` handler), invoked only for an already-scoped,
already-grounded sub-region when a rule needs disjunction / exactly-one / optimization.
This:

- keeps the monotone fact layer clean — world-splitting stays behind a tool boundary;
- respects the standing constraint against casual well-founded / stable semantics in
  core;
- sidesteps ASP's grounding-blowup failure mode, because the solver only ever sees a
  narrow, pre-pruned problem — the System-1 → System-2 seam (§7).

For ordinary defaults-with-exceptions ("free shipping *unless* order < \$20 *unless*
promo period"), **stay native**: add explicit rule **priority / specificity as data**
(defeasible-logic style — cheap, since defeat is already rules). Only the
non-stratifiable residual, or genuine model-enumeration, is delegated. Same content,
two engines, one substrate — exactly the "project a region into the specialized
engine, import results back as facts" pattern, not a translation boundary with loss.

---

## 4. Joern is a fact producer, never a second engine

A Code Property Graph (AST + control-flow + data-flow, merged) is *our relational
substrate in a different serialization*. Loading a Joern export is therefore mechanical
re-serialization, not a semantic bridge. This makes Joern the single most drop-in
piece of the whole stack, and it composes cleanly:

- Wrap `joern-export` as a **`dispatch.py` tool**. Its output (AST / CFG / PDG edges)
  folds into the graph as plain `S P O` facts.
- **Joern does zero reasoning.** Design-pattern detection (positive subgraph queries),
  anti-pattern detection (NAC queries — "resource acquired, no release reachable in
  CFG"), and business-semantic linkage all become ordinary rules over the folded-in
  facts, in the existing engine.
- Joern is the **ground-truth structural extractor**: it reflects *actual code*, not a
  model's belief about it. That is what makes it safe to trust for localization even
  when everything else in the loop is uncertain (the Repograph-feeding-Agentless
  precedent — structural indexing bolted onto an agent's localization step).

Joern feeds the substrate; the substrate reasons; the SLM reads the boundary. No piece
competes with another.

---

## 5. Frames are the join — do not write a CPG↔CNL translator

The concept "loop" is not one CPG shape (`for`, `while`, comprehension, and a recursive
walk are four structurally different subgraphs that mean the same thing) and it is not
one CNL phrase. **They do not bridge to each other. They both bridge to a shared typed
frame in the substrate**, and "matching" means two independent projections landed on
the same frame.

The discipline:

1. **Define the frame once, as schema, not as a mapping rule.** `Iteration(collection,
   element_var, body, condition?)` — an `is_a`-typed node with named-predicate role
   edges pointing at *other* nodes (identity + role-edges, never inlined copies). This
   is the small **code frame ontology** (`Iteration`, `Mutation`, `Call`, `Resource`,
   …) — a few dozen types for a real domain, not thousands.
2. **Write two independent recognizers, each targeting that frame — they never
   reference each other.** A CPG-side rule matches the structural shape (a CFG back-edge,
   a `FOR`/`WHILE` node, a comprehension, a recursive call — many-to-one) and
   materializes an `Iteration` frame whose roles point at the actual CPG regions. A
   CNL-side production matches "for each X in Y, do Z" and materializes an `Iteration`
   frame too, pointing at text spans / KB entities.
3. **"Matching" = do the two frame instances unify** — same type, role bindings
   resolving to the same or structurally-equivalent targets. Ordinary graph unification
   over the shared substrate. Bidirectional translation (code → CNL comprehension,
   CNL → code generation) then falls out *for free* because both sides target the same
   frame; it is never a separate pass to build.

Two wrinkles to respect: this is **many-to-one** (recursion-as-iteration is the sharp
case — structurally nothing like a loop, semantically identical at the frame level; if
the recognizer set omits it, that is a *coverage gap*, not a bug), and a **role often
binds a whole subgraph region, not a single node** (`body` is a block). This is the
paraphrase-collapse property the substrate already has for language via
`coref` / `same_as` / `canonicalize`; here it is reused for code shapes.

---

## 6. Coverage is bounded by rule generality, not rule count

The single highest-leverage authoring decision, and the answer to "can the reasoner
handle edge-case bugs it has no rule for": **yes, by deductive composition — for a
novel manifestation of a known mechanism; no — for an absent premise.**

- A reasoner with "queryset evaluation is lazy" and "mutating a collection during
  iteration over it is unsafe" composes those two to flag a queryset consumed inside a
  mutating loop that *nobody wrote a rule for*. This is exactly what the graph-rewriting
  engine (chained rule application) is built to do. The existence proof is type systems
  and abstract interpretation: a type checker's author never saw your code, yet catches
  errors in it, because type rules compose deductively over arbitrary new syntax.
- **Induction cannot be conjured by the reasoner.** A deductive engine derives only
  what its rules and facts entail; it does not invent a missing premise. A bug whose
  root cause is a domain fact encoded at *no* level of abstraction is unreachable by
  composition — that gap closes only by a human writing the rule, or by statistical
  induction over a corpus (§7 / §10).

The design lever this hands us: **author rules at the causal / mechanism level, not the
surface-pattern level.** "Iterator mutation during iteration is unsafe" is one rule
that composably covers every call site forever, including ones written after it.
"Don't mutate `self.queryset` in `get_context_data`" covers exactly one site. The
authoring effort that matters is not "how many patterns can we enumerate" but "how
few, sufficiently general mechanism-level rules compose to cover the most ground." That
is a materially smaller and more tractable task — and it is a KB-authoring discipline,
not an engine change.

---

## 7. Two systems, not one dial — statistical scope, then exact derivation

Humans solve most bugs without a computer's search power because a fast pattern-retrieval
system proposes a tiny hypothesis set and slow deliberate reasoning only ever touches
that set (chunking, recognition-primed decisions, dual-process). The architectural
consequence, which resolves every tractability caveat in the discussion (ASP grounding
blowup, subgraph-isomorphism cost, ILP hypothesis-space explosion):

**"Pruning by experience" is a second, different system whose whole job is scoping,
sitting upstream of a first system whose job is exact verification within that scope.
Do not build one system that tries to be both fast-broad and exact-narrow — that is the
tractability wall.**

- **System 1 — propose / rank / prune.** Narrow a combinatorial candidate space (which
  CPG region, which KB rules) down to a shortlist. In harneskills this is the
  **metareasoning layer** (`vision.md` §14): content-blind structural statistics — df /
  name-frequency selectivity, walker fuel, fire counts. It stays content-blind; that is
  the §14 guardrail that keeps the rejected smart planner out.
- **System 2 — verify.** The exact engine (composition / derivation, and the clingo
  calculator of §3) runs *only inside the narrowed scope*, with its soundness /
  completeness / attributability intact, because by then we have committed to a scoped
  candidate rather than a distribution over many.

The **threshold/commit step** where a graded score becomes a discrete "use this frame"
fact is *one* option at the seam between the representations — the point where completeness
is traded for tractability. But committing to a crisp fact is **not mandatory**: reasoning may
stay **graded through to a graded conclusion** (an α-cut fires a rule; a possibilistic degree
ranks the answer), which is often the honest thing in a messy domain where forcing a crisp
commit would fake a certainty the KB does not have. Where several candidates survive —
competing means for a subgoal (§9), rival frames — resolve by **authored graded preference**
(argmax over the satisfied alternatives by aggregate degree), not by an early discretization.
Design the step explicitly (what cutoff, what happens on ties); do not let it default to
"whatever scored highest," and do not treat "commit to a crisp fact" as the only move.

When localization / disambiguation eventually becomes the bottleneck, the *principled*
way to strengthen System 1 is a **transparent, corpus-scoped statistical ranker** —
weighted-rule / DOP-fragment frequency counts attached to the rules we already have
(the "trainable but inspectable, random-forest-not-deep-net" axis) — **not** embeddings
or an LLM, unless a genuinely open-vocabulary case forces it. Every count stays a
literal, nameable, printable pattern. This is consistent with the graded layer already
first-class in `vision.md` §13; §14 keeps the *effort* dial content-blind while §13
carries the authored *content* degrees.

---

## 8. Defeasibility: stratified primary, priority-as-data, ASP residual

Business rules are non-monotonic by nature. Our stance, unchanged in principle from
`vision.md` §11 but sharpened for the business-rules domain:

- **Stratified negation + `decide`/`completion`/`defeat` is the primary mechanism** —
  it covers defaults-with-exceptions whenever the rule set is stratifiable, which is
  most real business rules.
- **Priority / specificity is DATA** (defeasible-logic style), authored as facts, so a
  more specific rule defeats a more general one via the existing defeat machinery — no
  new engine semantics.
- **Gradedness is possibilistic and authored through natural hedges.** "very / always /
  sometimes / usually" map to fixed degrees declared as KB facts (`very is 0.8`), turning
  `alice is very urgent` into a graded attribute and `?c is very urgent` into an α-cut rule
  condition — **already built** (`authoring.py`, `degree_thresholds`/`graded_rules`/
  `degree_grammar_forms`), exercised in `corpus/icecream.cnl` and the contract suite. This is
  *soft preference ordering*, not probability — no joint distribution, no calibration — which
  matches how humans reason in the mess (and survive). It is also the mechanism for **ranking
  competing means for a subgoal** (§9): when more than one authored means could satisfy a
  goal, the substrate leans on the higher aggregate degree (an argmax to add on this
  foundation). The degrees stay **anchored** — authored hedge-words or rule-derived from
  gradable attributes, never opaque tuned weights, so a preference is as debuggable as a fact.
- **Genuine equal-priority mutual defeat, constructive disjunction, and model
  enumeration go to the clingo calculator (§3)**, scoped. We do not adopt well-founded
  / stable-model semantics into core casually — that would revisit the whole §5
  retraction discipline.

The target formalism matters and we have already chosen well: CNL grounding out in our
own stratified substrate (with the ASP calculator for the residual) gives default
negation where FOL/OWL would force monotonicity. The lesson from the field — do **not**
let a model arbitrate defeasible conflicts (it fakes them) — is honored by keeping
arbitration entirely symbolic.

---

## 9. The SLM is a scoped transducer, not the loop — the substrate drives

**The inversion (revised 2026-07-04).** The earlier framing here — "SLM proposes, tests
dispose," the substrate a bolt-on critic hanging off an SLM agent loop — is **inverted**.
The **substrate owns the loop**, and the **SLM is one `<call>` tool invoked at a single
boundary**: fuzzy natural-language intent → CNL. This is not a retreat from the
one-substrate vision; it *is* the vision taken literally — the model is a calculator on
opaque nodes (§8), exactly like clingo (§3) and Joern (§4), serviced by the same
dispatcher, its output folded back as facts. The design target is a **deterministic,
auditable core with a single thin stochastic input transducer**: maximize what is derived
and checked, minimize and isolate what is guessed. The system is a *flexible support tool
for a human working in a narrow domain* — the framework ships the domain-independent
machinery; the human plugs in domain knowledge.

**The control plane is authored in CNL as subgoals, and the substrate has bounded agency.**
*How* the substrate drives — understand → derive/render → run → observe → decide-next →
repeat — is **domain knowledge the human authors as CNL procedures**, but a procedure is a
**decomposition into subgoals, not a rigid script**: `to NAME: achieve s1 then achieve s2 …`
declares *what to accomplish*, and the substrate decides *how* to accomplish each subgoal by
goal-directed reasoning over the KB (a rule, a sub-procedure, a `<call>` tool — whatever the
KB affords), backtracking and re-deriving when a subgoal is unmet. So the substrate exercises
**genuine agency — but bounded by the KB** (it pursues only KB-afforded means; "not in the
knowledge = does not exist" caps it) and **auditable** (every choice traces to a fact / rule /
procedure via provenance, and the *effort/search* policy is the content-blind §14
metareasoning layer, and *which* satisfied means is preferred is **authored graded domain
preference** (§8) — content-*ful* and anchored, not content-blind meta). The engine is **deterministic** (reproducible given
KB + state + policy) yet the behavior is a **planner, not a script interpreter** — this is what
`corpus/planning*.cnl` already is (`planning.py` has zero Rule literals). The break from a
typical LLM agent thus *sharpens*: the **substrate** chooses the next action by symbolic goal
resolution over the KB — **never a stochastic model**. Knowledge has **three authoring
categories** — facts (what is), rules (what follows), procedures (what to achieve) — and the
DEFAULT-machinery / authored-knowledge split applies to all three. Linear `then`-ordered
subgoals are followed today; the concrete build that turns goal-directed planning into a full
agent *loop* is **subgoal-satisfaction over observed `<call>` results with bounded, §14-budgeted
retry** ("the subgoal *tests-pass* is unmet → pursue KB-afforded means → re-check → stop on
success or budget").

**Generation needs no language model — because we generate artificial languages.** Python,
bash, SQL, a config — all have formal grammars. Producing such an artifact from a
fully-determined specification is **deterministic rendering**: spec-frame → target syntax
tree → source text, the exact reverse of parsing and the §5 frames-as-join run backward
(we already render graph → CNL; rendering graph → Python is the same operation against a
*formal* — hence easier — grammar). Where generation needs *search* over the space of
valid programs (a "smallest artifact satisfying these constraints"), that is symbolic
search delegated to a `<call>` calculator (clingo, §3), still not a model. A language model
is required only when the *target* is a natural language (no formal grammar) or the *source*
intent is fuzzy — never for emitting an artificial language. The hard part is not rendering
the grammar; it is having the **knowledge that determines the artifact**, which is displaced
onto domain authoring — accepted by design (next point). The real builds this implies are
deterministic engineering, not modeling: the frame→source renderer (the reverse of `cpg.py`)
and effectful `<call>` tools with error/timeout semantics.

**"Not in the knowledge = does not exist" is the deliberate bound, not a gap.** The
substrate covers exactly what the domain KB determines; open-ended synthesis of code no
rule entails is *out of scope by construction* — want more coverage, provide more knowledge.
This is what makes the tool auditable and a bounded domain tractable where the open world is
not (§12). It also means there is **no "SLM writes code" boundary at all**: the second
boundary the conservative framing worried about is closed by fiat, buying a smaller, exact
system.

**Tool output returns through adapters, not a model.** Reading test results, exit codes,
structured logs, stack traces is fact-production — the Joern pattern (§4) generalized to any
tool: a deterministic adapter normalizes output to `S P O` facts. Most tool output is
structured or regular enough for a parser, and an adapter is *auditable* where a model
reading output is not, so adapters are strictly preferred wherever feasible. A genuinely
free-form residual (prose diagnostics) *may* use an SLM, but that is a shortcut, not a
technical necessity.

**The one boundary — NL → CNL — is the tractable model piece, and harneskills owns both
halves of its training loop:**

- **A small model suffices, because the task is closed-target translation, not open
  generation.** Structurally identical to NL-to-SQL / NL-to-regex. Fine-tuned 3–4B
  models match far larger teachers on narrow structured-output tasks; sub-1B is
  plausibly enough for the *shallow* constructs (construct-dependent, decided
  empirically per §10).
- **Strip vocabulary from the model's job.** Treat an unknown word as a *KB* failure,
  not a model failure. The model's only jobs are (a) map sentence structure to CNL
  slots and (b) **copy an unrecognized token through verbatim** (pointer/copy behavior)
  rather than "helpfully" normalizing it into something that happens to parse. This
  drops the data need from thousands to *low hundreds*, splits into two pools
  (construct-coverage with arbitrary/nonsense vocabulary — the "colorless green ideas"
  separability — and copy-behavior with deliberately novel tokens), and runs on
  free-tier hardware.
- **Grammar-constrained decoding makes invalid CNL unreachable.** The model learns only
  the semantic slot-mapping, not well-formedness.
- **The parser is the free, exact reward signal.** Feed the model's CNL back through
  the harneskills parser: parse-success plus frame-graph match against ground truth is
  a cheap, automatic, exact grade — enabling rejection sampling / preference pairs, not
  just supervised fine-tuning. The CNL grammar *is* the synthetic-data generator (sample
  CNL → back-translate to NL). We own both ends, so no hand-labeling and no external
  eval loop.
- **Round-trip / "active-listening" checks** (NL → CNL → deterministic NL′, compare) are
  a cheap production-triage net for *unlabeled* input, catching confidently-wrong
  parses the frame-graph check cannot see in production. But: judge with embedding
  similarity or a *different* model, never the model judging itself; and iterated
  round-tripping proves *stability of the parse*, not *truth* — classify short-cycle
  oscillation as a **grammar-confusability defect worth fixing once**, not as
  per-instance low confidence.
- **Ambiguity is resolved by asking the human, not by the model guessing.** This is a
  support tool for a human in the loop, so a low-confidence or ambiguous parse surfaces
  as a clarification, further shrinking the stochastic surface rather than papering over
  it.

The realistic shape, then, inverts the old one: **the substrate follows an authored CNL
procedure, derives or renders artifacts from domain knowledge, runs them through effectful
`<call>` tools, ingests results through adapters, and checks every step against
mechanism-rules (§6) with an *attributable* verdict ("violates rule R")** — while the SLM
only transduces intent *in*. The genuinely novel contribution stands and sharpens: not "an
agent with a symbolic linter," but a **deterministic reasoning-and-generation core over a
human-authored KB, with the language model shrunk to a single thin intent boundary.**

### The agentic loop — triage is its front door

Everything the substrate does is **triggered by something** — user intent (via the intent
transducer), a scheduler tick, a tool-completion event, a file change. The trigger enters the
graph as a **request frame** (plain `S P O` facts), and one turn of the loop is goal-directed
planning over it:

1. **Trigger → request frame.** Whatever fired lands as facts. The only fuzzy step is when the
   trigger is natural language (the §9 transducer); a scheduler or event trigger is already
   structured, so it needs no model at all.
2. **Triage — the first step, and it is *derivation*, not classification.** Rules match the
   *shape* of the request frame against the KB (declared capabilities, procedures, domain
   membership) to **derive which goal/procedure it activates**. A novel request routes by its
   structure, not a memorized `request → label` table; an unmatched one produces an
   **attributable gap** ("no procedure handles this shape"), never a confident mis-route.
   Triage may start trivial (one procedure) and grow by adding *general* routing rules and
   *whole capability classes as data* — never by enumerating requests (the §6 / §12 lesson).
3. **Plan — decompose into subgoals.** The activated CNL procedure expands to subgoals
   (`to NAME: achieve s1 then achieve s2 …`). Where several authored means could satisfy a
   subgoal, **graded preference (§8) ranks them** and the substrate leans on the best fit.
4. **Act — three kinds of means, at most one stochastic.** Satisfy a subgoal by (a) deriving a
   fact from rules, (b) **rendering** an artificial-language artifact from a determined spec
   (deterministic — no model), or (c) invoking an **effectful `<call>` tool** (run tests, edit a
   file, hit an API).
5. **Observe — tool output back through adapters.** A deterministic adapter (the Joern
   fact-producer pattern of §4 generalized) normalizes results to facts. When the world actually
   *changed* (a file edited, a test now green), this is retraction-heavy — the TMS re-opens
   settled facts, and monotone propagation must not fight the retraction (the known §5 hazard).
6. **Decide-next — satisfaction, branch, bounded retry.** An unmet subgoal drives the substrate
   to pursue more KB-afforded means and re-check; *how hard to retry* is the content-blind §14
   budget. Stop on success or exhaustion; then the next trigger.

The break from a typical LLM agent holds at **every** step: the model never triages, plans,
picks a means, or arbitrates — the **substrate** does, symbolically and with provenance. Two
pieces are the real builds this loop needs and does not yet have: **effectful tools** (the
`<call>` dispatcher is a pure calculator today — world-mutating tools need error/timeout
semantics, results-as-facts, and a disciplined retraction path for the changed world) and the
**frame→source renderer** (the reverse of `cpg.py`). Graded means-selection (step 3) is the
smallest first slice and sits on live machinery (§8).

---

## 10. Evaluate the substrate before building the machinery around it

Decouple the two risks: *is the representation expressive and tractable enough for the
reasoning I want* versus *can I build a reliable extractor that produces it*. Test the
first without touching the second. harneskills is the rare project that can run Stage 1
today with no new machinery, because it already reasons over hand-authored CNL.

1. **Stage 1 — hand-author the substrate, skip extraction.** Write 3–5 real cases (the
   queryset-mutation-during-iteration hazard is the canonical one) as CNL frames *as if*
   extraction had run, plus the mechanism-level rules, and confirm the existing engine
   derives the hazard. An afternoon, not a pipeline.
2. **Stage 2 — adversarial near-misses.** For each rule, a structurally-close case that
   must **not** fire (queryset consumed but never mutated; mutation on a different
   variable). Compositional rules over-generate before they under-generate; this is the
   cheap place to catch it.
3. **Stage 3 — synthetic scale.** Mechanically emit hundreds/thousands of schema-valid
   frames, feed the engine, watch solve time / grounding size. Isolates tractability
   from correctness.
4. **Stage 4 — one vertical slice.** Only now build the Joern → frame bridge, for *one*
   frame type against a handful of real files, and check the extracted frames match
   what Stage 1 hand-authored.

For the graded layer: hand-assign scores to synthetic candidates and check the
aggregation ranks them as a human would — testing the scoring logic before any
extraction feeds it real numbers.

**Question-answering is a separate evaluation axis, not a variant.** Rule-detection
tests *derivation*; most code QA ("what calls X", "where is Y defined") tests
*retrieval* — a schema-completeness check (does the extracted graph contain what a
natural question needs an edge for), distinct from anything Stages 1–3 cover. Keep test
questions in CNL / templates so a failure reads as "the reasoner is wrong" rather than
"the question parser misunderstood."

---

## 11. Rule induction — later, and split by half

To *evolve* rules from examples rather than hand-author them all: **Inductive Logic
Programming (ILASP)** is the ASP-native match for the **KB / defeasible-rule** half —
it learns defaults and exceptions, tolerates noisy examples, guarantees an *optimal
(minimal)* hypothesis (not just any fit), and reuses the very positive/near-miss pairs
built for evaluation (§10) as its training input. Its cost — hypothesis-space
explosion — is controlled by the same lever threaded through this whole architecture:
**tighten the declarative bias / constrain the searchable rule shapes before searching**.

Two honest boundaries: ILASP fits the discrete ASP side, so a **gradable score must be
discretized (bucketed into named predicates) before ILASP sees it** — that bucketing is
the deliberate System-1 → System-2 commit of §7, with ILASP entirely on the System-2
side. And ILASP does **not** learn the scoring function itself (a separate regression /
weight-fitting problem, upstream). The **CPG-recognizer** half (structural frame shapes)
is graph-grammar-shaped, not ASP-fact-shaped; inducing *those* wants split-merge /
EM-style grammar induction, a different tool. Two induction techniques for the two
halves — consistent with "two specialized engines over one shared representation." All
of this is a *later* arc, gated on the substrate proving out via §10; it is recorded
here so the evaluation artifacts are built in a shape that feeds it.

---

## 12. What the Cyc bottleneck does and does not fall to

Naming this precisely, because it bounds every claim above. The knowledge-acquisition
bottleneck that sank Cyc was never "typing rules is hard"; it was *knowing what the
rule should be* and vetting each against everything already encoded, a cost growing
with the KB's size.

- A cheap NL → CNL model (§9) makes authoring **more accessible** (domain experts, not
  ontologists, can contribute) — a real but *secondary* mitigation. It does nothing for
  authoring **correct**.
- **Bounded domain scope** caps the combinatorial consistency cost at a domain-sized N
  rather than an open-world N — a structural improvement, and why a well-modeled single
  library (Django, sympy) is a reasonable bet where "the world" is not.
- **Extraction from authoritative existing documentation** converts the hard part
  (inventing and vetting knowledge) into a genuinely easier one (information extraction
  from a trusted source, within a bounded domain) — the real progress. But it inherits
  documentation's own failure modes: **omission** (tribal-knowledge exceptions surface
  as *silence*, not detectable contradiction), **staleness / cross-document
  contradiction**, and **entity/terminology alignment** across documents. Treat an
  extracted KB as a strong first draft to stress-test against real case data (§10), not
  as ground truth the moment extraction finishes.

**Coverage — gaps by omission that surface only on edge cases — is the residual risk
that does not disappear.** It is the same long tail, rescoped from "cases no grammar
covers" to "cases the documentation happens not to mention." §6 (mechanism-level rules
that compose) is the mitigation; it is not elimination. This is the open architectural
question worth taking seriously, exactly as it has been since the beginning.

---

## 13. Standing conclusions (do not relitigate)

1. **The substrate is the reasoner.** Do not adopt clingo / Neo4j / GrGen / ACE as the
   engine; they enter only as scoped `<call>` calculators (§3) or fact producers (§4).
2. **A model lives only at the boundary** (fuzzy intent → CNL, reading arbitrary tool
   output). Never inside the controlled surface; never arbitrating defeasibility (§2, §8).
3. **Joern is extraction, not reasoning** (§4).
4. **Frames are the CPG↔CNL join; there is no translator** (§5).
5. **Author mechanism-level, composable rules — coverage is bounded by generality, not
   count** (§6).
6. **Two systems: content-blind statistical scoping upstream, exact symbolic
   verification downstream. The commit-threshold between them is designed, not
   defaulted** (§7).
7. **Evaluate the substrate by hand-authored Stage-1 cases before building any
   extractor** (§10).
8. **Coverage-by-omission is the standing residual risk; mechanism-rules mitigate, do
   not eliminate it** (§12).
9. **Correctness-about-the-world is not a goal; auditable, KB-anchored flexibility is.**
   Trade formal purity (stratification-as-an-end, *refusing* messy or non-stratifiable
   cases) and world-truth guarantees for flexibility — answer best-effort with a graded
   degree and provenance rather than declining. Reasoning may stay graded through to a
   graded conclusion; gradedness is possibilistic and authored through natural hedges (§8).
   **Never** trade engine-faithfulness or provenance: they are the anchor that makes graded,
   sometimes-wrong reasoning *attributable and locally repairable*, which is the whole
   difference from an LLM (§8, §9).
