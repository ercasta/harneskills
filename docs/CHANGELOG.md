# Changelog — the one-substrate rebuild

Reverse-chronological log of the ground-up rebuild onto `docs/vision.md`. Newest first.
Test counts are `pytest tests/ -q`. Nothing is committed automatically — the user commits
manually, so "N tests green" is the state at that point, not a commit.

For the **index of everything**, read `docs/reference.md`. For the **current plan and next
step**, read `docs/implementation_plan.md`. For the **design philosophy**, read
`docs/vision.md`. Deep rationale for most entries lives in the `memory/` decision/finding
files (linked inline). Older entries reference docs now in `docs/attic/` — that is expected;
this log is itself a historical record.

---

## 2026-07-10

### Phase 5.5 (slices 1–3b) — firmware MODES as §8 `<call>` calculators, driven by RULES in the loop
`harneskills/mode_calls.py` — the enabling primitive for KB procedures "run as control-token programs"
(522→535 green, `tests/test_isa_mode_calls.py`).

**Slice 3b — no new surface + key-aware INTERN fix (ratified: reuse the existing `<call>` machine-rule
grammar; fix INTERN now; SUPPOSE deferred).** Mode-composing rules are authored with the EXISTING
`<call>? SLOT VALUE and … when …` grammar (`planning_requests.cnl`-style) — zero new forms, zero SLM
debt. **Key-aware INTERN fix** (`machine.py`, retires `finding-interning-aliases-predicate-literals`):
MINT-intern no longer takes `nodes_named(nm)[0]`; it skips a reified DOMAIN-RELATION candidate (graded
key == its own name, name not a reserved `<…>` token — control tokens keep interning). So a value-literal
`is`/`eats` canonicalizes to a distinct value node, never the predicate rel node. This makes RELATIONAL
mode-calls (`<call> -[pred]-> eats`) sound and retires the copula-only 3a limitation; `check_tool`'s
copula default is now mere ergonomics. Full suite green incl. reasoning parity (a core mechanism — gated
hard). Test: a CNL-authored rule emits a relational `eats` check, serviced over the backward bank, whose
derived fact drives a downstream rule.

**Slice 3a — rules emit mode-calls; the EXISTING loop services them; the effect FEEDS BACK (no new
driver, no authored surface, zero SLM debt).** Ratified framing (user): the primitive is
rules-emit-mode-calls (loop-inversion / machine-rule-CNL faithful), NOT a Python procedure DSL — the
`to NAME` linear header is later sugar. `run_bank(..., tools=mode_registry(rule_g))` ALREADY services
`<call>`s at fixpoint (`lowering.py:531`), so integration = pass the mode registry as `tools`. The CHECK
verdict is now ALSO emitted as CONTROL relations (`<check> -[status]-> S`, `-[of]-> subj`) so a forward
RULE can MATCH it and react — the plan→act→check feedback. 3 integration tests: a rule emits a CHECK
call whose POSITIVE materialization drives a downstream rule; a rule REACTS to a CWA `assumed-no` verdict
(nothing materialized — the verdict relations carry it); a rule emits a CHOOSE call whose winner drives a
downstream rule. The forward bank does NOT contain the reasoning that answers the goal — only the
serviced mode-call produces it, proving the composition is real.

**SHARP EDGE found + tracked (`finding-interning-aliases-predicate-literals`):** a rule that materializes
a `<call>` carrying the goal PREDICATE as an object literal (`<call> -[pred]-> is`) runs away + corrupts,
because `MINT(intern=True)` interns the literal `"is"` to the EXISTING `is` **predicate** rel node (same
name) — wiring the `<call>` into the fact graph so it re-matches `?x is bird` forever. Root cause:
interning is by NAME, conflating a value-literal with a same-named predicate (the Phase-2 name/key split
not yet enforced at INTERN). Interim 3a fix: `check_tool` defaulted `pred` to the copula. **RESOLVED in
3b (above) by the key-aware INTERN fix** — relational predicates now carry safely; the copula default is
now mere ergonomics.

**Slices 1–2 — the primitive.** A reasoning MODE is invoked exactly like a tool: a
rule/procedure materializes a `<call> --tool--> check` node with goal slots (`pred`/`subj`/`obj`); the
dumb dispatcher (`dispatch.service_calls`) runs the firmware `check` and folds a `<check>` verdict node
(a CONTROL token carrying the goal + one of the 4 CHECK statuses as VALUED attrs) back, consuming the
call. This is `decision-agentic-direction`'s "tools as calculators" applied to the modes themselves —
WHICH mode fires and WHEN is decided by the calls present (DATA), never the content-blind dispatcher.
Reuses the existing `<call>` loop (`decision-materialized-tool-calls`), NOT a new driver ("the loop
already exists — reuse, don't rebuild"). Lives at `harneskills/` level (a bridge like `procedure.py`;
inside `isa/` it closes an import cycle through `world_model`).
- **Slice 1 — CHECK** (goal → `<check>` verdict). 6 tests reproduce all 4 statuses vs. the direct
  `check(...)` call, pin the verdict as control (invisible to fact matching), show several calls each
  serviced + consumed.
- **Slice 2 — CHOOSE** (`<call> --tool--> choose --goal--> G [--alpha--> a]`): runs the firmware
  `choose` over the goal's pre-registered candidates (α-cut + argmax), marks `satisfied_by`/`beaten`;
  `choice_results` reads winners back. CHOOSE needs no rule bank. 3 tests: argmax winner, α-cut prunes
  all, and a HETEROGENEOUS program (a CHECK call + a CHOOSE call in one graph, both serviced). SUPPOSE
  is deliberately NOT a single call — its assumptions/predictions are variable-length lists, a scope the
  CNL surface lays down (slice 3), so forcing it into fixed slots would be a workaround.

Remaining 5.5 slices: **3b** — the CNL procedure surface that EMITS mode-calls (+ a non-aliasing
predicate encoding for relational checks, + SUPPOSE scope authoring; SLM debt); then **slice 4** —
plan→act→check→replan as ITERATE×CHECK; then the Phase-5 exit gate.

### Phase 5.4 — DECLARED strategies replace shape-sniffing (delete the three sniffers)
The engine no longer reverse-engineers a strategy from rule shape/naming; it reads a DECLARATION
(`feedback-no-hardcoded-engine-policy`). Two sniffer families in `goal.py` deleted (519→522 green:
+2 walker-declaration tests, +1 coref-tag pin; no pre-existing answer changed).

**5.4a — walker/transitive (test-only in production, answers-identical → low risk).** Deleted
`_is_transitive_closure_rule`, `_linear_recursion_base`, `_closure_bases` (the ~90-line rule-shape
matchers). Replaced by `_closure_declarations(ag)`, which reads the walker base map from the
SUBSTRATE: `R is transitive` → the CANONICAL `R -[rel_property]-> transitive` fact (the SAME
declaration `rule_graph.expand_relation_properties` already uses to GENERATE the transitivity rule —
it now does double duty), and `D -[transitive_closure_of]-> B` for linear recursion over a different
base. `GoalSolver` gains a `closures=` param (defaults to reading `self.ag`); nested solvers are
handed the parent's map. Note: `walk_fuel` is NEVER set in production (every production `GoalSolver`
is fuel-less), so the walker + these sniffers were test-only — deleting them is a pure de-sniffing
with zero production behavior change. Walker tests now DECLARE the strategy in their graphs; a new
end-to-end test drives the full CNL `is_a is transitive` → `rel_property` fact → `_closure_declarations`
→ walker chain.

**5.4b — coref-follow (production-semantic → behavior-preserving + differentially gated).** Deleted
`_is_same_as_prop` (which sniffed `r.key.startswith("same_as.subj.")`). `Rule` gains a declared
`coref_prop: bool` role (like `meta`); `universal.same_as_rules` sets it `True`; `GoalSolver.__init__`
reads `r.coref_prop` (not the key) to turn coref-following ON and drop the propagation rules as
subsumed by its union-find. This repairs a LOSSY path: `same_as_rules(preds)` already declared the
coref role, the result was discarded, and `_is_same_as_prop` re-derived it by matching the keys
`same_as_rules` itself minted. The tag carries the declaration forward instead of re-sniffing it —
the same category as the existing `nac`/`propagate`/`meta` rule-data the engine reads. Full suite
answer-identical (every pre-existing test unchanged). Pinned: `test_coref_following_is_driven_by_the_declared_flag_not_the_rule_key`
(a rule with the same key/shape but `coref_prop=False` is NOT treated as a propagation rule — the FLAG decides).

**TRACKED RESIDUAL VIOLATION (ratified with the user 2026-07-10 — chose option A, "tag now"; log it,
don't paper over it).** 5.4b closes the ENGINE-sniffing violation (A) but NOT the deeper
`no-python-for-banks` violation (B): WHICH predicates propagate coref is still chosen in Python
(`session.py`'s `CONTENT_PREDS` constant), and the propagation RULES are still Python-generated by
`same_as_rules`. The vision-faithful end-state — a bank-authored `same_as propagates through X` CNL
surface that both generates the rules AND signals following — is NOT reachable now because it needs
the coref rules REIFIED/authored (the Phase-3 homoiconicity quote/eval wall, explicitly parked). So
the CNL surface is deferred to **Phase 3**, where it can be done whole rather than bolted onto
still-Python machinery with migration + SLM-surface risk. The `coref_prop` tag is forward-compatible:
when rules reify it becomes a graph attribute on the rule node, same read site. See `implementation_plan.md`
Phase 3 (tracked) and Phase 5.4.

### Phase 5.3 — SUPPOSE firmware: `<hypothesis>` scopes as the pencil/ink split (same-graph, not branching)
`harneskills/isa/suppose.py` — firmware v2 mode 6 ("what if" — entertain before believing). The
hypothesis-formulation-and-verification mechanism (`processing_modes.md` §3), composed from CHAIN + CHECK
inside a scoped control region. NOT possible-worlds: reasoning happens on the SAME graph, segregated by a
scope tag — never a `graph.copy()` branch (the trap mode 6 names).

The non-additive part, exactly as the plan's design crux predicted: CHECK/CHOOSE were pure additions over
`chain_sip`; SUPPOSE could not be, because the pencil (assumed facts) are CONTROL nodes and matching
deliberately IGNORES control. So **scope-aware matching** landed as a `scope=` param on
`apply._fact_relnodes` / `chain._facts_matching` / `_fact_exists`/`_find_fact_relnode`, **gated
behavior-NEUTRAL at `scope=None`** (the default everywhere but in-scope reasoning) — differentially proven
against the pre-existing firmware gates (511→519, all 34 gate tests + full suite green). A pencil fact is a
CONTROL rel node tagged `apply.SCOPE = "scope"` (a VALUED attr naming the `<hypothesis>` id): invisible to
ordinary matching (never touches ink), visible ONLY within its scope. `chain_sip(scope=…)` sees pencil+ink
and EMITs its derivations back in pencil.

`suppose(fact_g, rule_g, assumptions, predictions)` → `SupposeResult(status, committed, contradiction,
looked_for)`: mint a `<hypothesis>` scope, pencil the assumptions, CHAIN each prediction and its `_neg_pred`
in-scope, then **REFUTED** iff a prediction's negation is entailed in-scope (the supposition entails the
opposite) → `_drop_scope` (sweep every scope-tagged control rel + the hypothesis; ink untouched); **CONFIRMED**
iff every prediction holds and none contradicted → EMIT the assumptions to INK (optional `<j:confirmed>`
provenance), then sweep the pencil; **INCONCLUSIVE** (no contradiction, not all predictions derivable in
budget) → drop, ink untouched. The fact layer stays MONOTONE throughout — no retraction, because nothing
unconfirmed became a fact (the pencil/ink split doing its designed job). `explain_suppose` renders the verdict
+ what entered ink + what the in-scope reasoning explored. v0: assumption endpoints are real (only the RELATION
is pencil); CONFIRM commits only the assumptions (consequences re-derive from ink forward). Caveat logged:
`lowering.derived_triples` includes control rel nodes, so an ink-only reader must skip control/inert (see
`tests/test_isa_suppose._ink`). Tests: `tests/test_isa_suppose.py` (8) — behavior-neutral invisibility,
in-scope pencil derivation, confirm→ink-survives-teardown, refute/inconclusive→ink-untouched, two-supposes-
same-graph independence, explain. 519 green.

### Phase 5.2 — CHOOSE firmware: graded α-cut argmax over candidate frames (monotone, losers retained)
`harneskills/isa/choose.py` — firmware v2 mode 5 ("comparing options and picking"). Realizes the LOCKED
means-selection design (`graded_means_selection_design.md`, mechanism 1b "RETAINED/RANKED, MONOTONE — no
retraction"), which had been designed but NEVER built (no `select.cnl`, no `beaten`/`satisfied_by` anywhere).
`choose(g, goal, alpha=…)`: candidates are option nodes reachable by a `candidate` relation, each carrying a
graded `fit` (a VALUED float in [0,1] — invisible to the embedding view; however produced — authored
`has_fit` or a graded rule condition's α-cut degree). α-cut prunes below `alpha`, then the winner is the
argmax = the candidate NOTHING BEATS (a candidate is `beaten` iff an eligible one has STRICTLY greater fit —
the design's `satisfied_by ... and not ... beaten`, computed by the firmware driver, no `<compare>` tool
needed since fit is a real float). MONOTONE: winners marked `goal -[satisfied_by]-> w`, eligible losers
marked `beaten` and RETAINED (auditable why-trace); nothing retracted (§5). TIES (equal max) → all tied win.
α-cut and selection COMPOSE as two filters — an α-pruned candidate is INELIGIBLE, not `beaten` (it never
entered the comparison). `explain_choice` renders the winner + beaten alternatives with fits. TESTED
(`tests/test_isa_choose.py`) on the design's exact fixtures (complex_page 0.8 beats simple_page 0.3; equal-fit
tie offers both; single candidate trivially satisfied; α-cut prunes before selection) + a 200-seed randomized
differential vs an independent argmax reference (winners == eligible-max set for random fits × random α).
v0 scope: fit is an INPUT — computing it from a rule's graded condition DURING matching (the α-cut in the
APPLY/CHAIN body, `_graded_degree`) is the companion slice; the planner's `chosen` operator pick as a declared
CHOOSE is the follow-on. Next: Phase 5.3 SUPPOSE (`<hypothesis>` scopes).

### Phase 5.1 — CHECK firmware: bounded completion -> a 4-status CWA-default verdict + "where I looked"
`harneskills/isa/check.py` — firmware v2's first mode (`processing_modes.md` mode 4, "looking for something
and possibly not finding it"). `check(fact_g, rule_g, goal, open_preds=…)` runs CHAIN (`chain_sip`, the
bounded demand-driven prover) and reads the outcome as ONE of four statuses (`decision-cwa-default`'s model):
POSITIVE (derivable), ENTAILED_NEG (the negative `pred_not` is derivable — a HARD no, e.g. from disjointness),
ASSUMED_NO (neither derivable + closed-world default — a DEFEASIBLE no, computed from the demand closure, §5-
safe: nothing materialized/retracted for it), UNKNOWN (neither derivable + the concept is OPEN, `open_preds` —
gather instead of assume). `collapse()` maps the four to the yes/no/unknown a caller acts on — exactly
`query.ask_goal`'s verdict, which `GoalSolver` computes but COLLAPSES the two negative KINDs; CHECK keeps the
KIND distinct (the signal the metareasoning/escalation layer needs). `explain_check()` renders the verdict
plus "where I looked" from the visible `<demand>` magic set (`render_demands`) — what makes an assumed-no
honest and renderable ("I looked for X and Y within budget and found nothing"), not a claim about the universe.
DIFFERENTIALLY GATED (`tests/test_isa_check.py`): over 12 random positive banks × every bound goal (500+
checks) with a mix of closed and open concepts, `collapse(check(...))` EQUALS the `GoalSolver`-based
`ask_goal` verdict (yes/assumed-no/unknown) exactly; the four statuses and the "where I looked" trace are
pinned individually (incl. an ENTAILED_NEG from a `penguin -> is_not flyer` rule). v1 scope: negative
predicate is `pred + "_not"` (the `decide.NEG_COPULA` convention generalized); ENTAILED_NEG fires only where
the bank has negative-producing rules. NOTE: the reasoning-side AGGRESSIVE `is_not` completion (materialize
the negative for closed-world predicates — `decide.solve`'s elimination) is a distinct write-side mechanism,
not this query verdict; it composes in with CHOOSE/elimination. Next: Phase 5.2 CHOOSE (graded α-cut).

### Phase 4.4 — the firmware TRACE RENDERER (the phase gate): RECORD + journal-replay + firmware==GoalSolver
The firmware now JOURNALS natively (`processing_modes.md` mode 9, "not optional") and its derivations RENDER
as CNL, and it is proven equal to the reference backward engine on the positive slice — the three things
Phase 4.4 owes:
- **RECORD (mode 9), `harneskills/isa/apply.py` `_record`.** APPLY (`_apply_pass`/`apply_to_fixpoint`) and
  CHAIN (`chain_sip`) mint a `<j:rulekey>` justification per firing — `proves -> head`, `uses -> each body
  fact node` — in the SAME inert substrate shape `GoalSolver._justify` / `rewriter` write. Opt-in
  `provenance=True` (default OFF, so the derivation-set differential gates stay clean; provenance nodes are
  INERT — invisible to matching/`relations_from`). `uses` is recorded in AUTHORED rule order so the journal
  is byte-identical to `run_bank`'s.
- **RENDER = journal replay.** Because the journal is the standard `proves`/`uses` support and
  `world_model.Graph = AttrGraph`, a firmware derivation explains through the EXISTING `surface.explain`
  with NO firmware-specific renderer — "explanation = RECORD, replayed" (vision §9). Pinned: a `chain_sip`
  derivation renders as a proof tree (`socrates is_a mortal <- mortal` / `... <- person` / `... (given)`),
  and an APPLY derivation explains BYTE-IDENTICALLY to `run_bank(provenance=True)`.
- **`render_demands`** — the bound magic set (visible `<demand>` nodes) rendered as CNL "what I looked for"
  lines, scoped to the goal subject by SIP (the demand half of the trace; CHECK's "where I looked" negative
  trace extends it in Phase 5).
- **EXIT GATE — firmware == GoalSolver on the ProofWriter positive slice** (`tests/test_isa_firmware_gate.py`).
  A randomized differential over a representative positive-Horn pool (is_a transitivity + a two-relation
  inheritance join + a linear implication + a conjunctive-body rule) across 20 random fact graphs and every
  binding pattern of a goal (1000+ checks): `chain_sip`'s goal answers EQUAL `GoalSolver.solve`'s everywhere.
  The two demand-driven engines — one hidden-dict tabling, one visible-`<demand>` firmware — agree exactly.
`tests/test_isa_trace.py` + `tests/test_isa_firmware_gate.py`. NOTE: live rendering of the EPHEMERAL
`<frame>`/`<current-atom>` working state (a debug affordance) and the not-yet-built modes' traces (CHECK
"where I looked", SUPPOSE scopes) are deferred with their Phase-5 modes; the persistent journal IS the
explanation for the positive core. **Phase 4 (the firmware POSITIVE CORE) is complete through its gate.**

## 2026-07-09

### Phase 4.1 — CHAIN bound-tuple SIP: `<demand>` promoted from predicate grain to tuple grain (493 tests)
`harneskills/isa/chain.py` — `chain_sip(fact_g, rule_g, (pred, subj|None, obj|None))` answers a BOUND-TUPLE
goal demand-driven, the magic set GoalSolver computes at tuple grain (`goal.py`'s `_join_body`/`_pat_goal`)
realized as VISIBLE bound `<demand>` nodes over the reified rules. A demand is a bound tuple carried on a
`<demand>` control node (`for=/subj=/obj=`); evaluation INTERLEAVES demand-raising with per-env body
evaluation (a body atom's sub-demand is raised under the env bound so far, so a join var bound by an earlier
atom grounds the next atom's demand) and iterates to a fixpoint. The win over v0's predicate-grain `chain`:
it prunes by SUBJECT/OBJECT, not just predicate — a goal `is_a(socrates, ?)` never demands a second
philosopher `plato`'s facts (differentially pinned: `run_bank`'s full closure HAS `plato is_a mortal`,
`chain_sip` does not, while being COMPLETE for the socrates tuples; a two-chain transitive goal likewise
skips the off-goal chain). REAL BUG caught in design + differential test: seeding the body by df selectivity
(APPLY's heuristic) is UNSOUND for SIP — it can front-load an atom whose join var isn't bound yet, raising an
UNBOUND `(pred, None, None)` sub-demand that floods in every off-goal tuple (`zeb is_a delta` leaked). Fixed
with `_sideways_order`: process an atom only once it has a pruning endpoint (a literal, or a var bound by the
head-unify / an earlier atom) — binding order, not selectivity, keeps the magic set scoped; a disconnected
remainder falls back to a full scan (correct, unpruned). v1 scope: positive rules, plain-literal predicates,
unique-noded names; the per-env bindings stay a Python env (the headline visible gadget is the bound
`<demand>`; promoting the env to a `<frame>` as APPLY does is a later unification). v0 `chain` (predicate
grain) + its tests are retained. **Phase 4.1 is now COMPLETE** (APPLY cursor + `<fresh>` delta last session,
CHAIN bound-tuple SIP this one). Next: Phase 4.4 the trace renderer (the phase gate). See plan Phase 4.1.

### Phase 4.1 — firmware gadgets: `<current-atom>` cursor + `<fresh>` semi-naive delta (490 tests)
The last two pieces of hidden APPLY driver state become VISIBLE graph structure (`harneskills/isa/apply.py`),
each behavior-neutral / differentially gated vs `run_bank`:
- **`<current-atom>` cursor over a `next`-chain itinerary.** The body-atom loop is no longer a Python loop
  index: `_build_itinerary` materializes the df-sorted body as a visible chain of `<atom>` step nodes (each
  carrying its `(subj, pred, obj)` tokens as VALUED attrs), linked by a control `next` relation, with a
  `<current-atom>` cursor pointing `at` the head. `_apply_pass` reads the atom to match FROM the cursor and
  ADVANCES it along `next` — so "which body atom is current" AND the whole df-sorted sequence (the driver's
  one heuristic choice) are graph a trace renderer can read. The itinerary lives on FRESH control nodes only
  — it never touches the reified rule's patoms (an edge into a patom would corrupt `_read_atoms`) — and is
  GC'd with the frames. Pinned: `test_body_atom_cursor_is_a_visible_itinerary_that_advances`.
- **`<fresh>` semi-naive delta for the SATURATE fixpoint.** `apply_to_fixpoint` no longer re-joins the whole
  body every round: it full-joins once (the seed), then each round re-derives only from the previous round's
  DELTA — for each body position in turn, that atom draws from `fresh` while the others stay full
  (delta-substitution, mirroring `GoalSolver._delta_join`). The delta atom is marked `<fresh>` on the
  itinerary (the semi-naive position as visible structure, not a hidden flag). CORRECTNESS SUBTLETY caught in
  design: `_apply_pass` re-sorts the body by df each call, so the fixpoint FREEZES one df order per round and
  passes it to every position's pass — else `delta_pos` could name different atoms across a round and an atom
  might never take its delta turn (a silent incompleteness). Differentially identical to the naive fixpoint
  (`test_apply_transitivity_recursion_matches_run_bank` + a longer multi-round chain); the count and the
  derived-triple set both match `run_bank`. Pinned: `test_fresh_delta_atom_is_marked_visible_on_the_itinerary`,
  `test_semi_naive_fixpoint_derives_the_full_transitive_closure_over_many_rounds`. `apply_rule` refactored to
  a thin `len(_apply_pass(...))` full-pass wrapper (signature/behavior unchanged; CHAIN + tests untouched).
Phase 4.1 REMAINING: the bound-tuple SIP for CHAIN (promote the predicate-grain `<demand>` to per-bound-tuple
magic sets, mining `goal.py`'s SIP) — a larger, separate slice. Then Phase 4.4 the trace renderer (the gate).
See `docs/implementation_plan.md` Phase 4.1.

### Phase 3.3 + 4.3 — head index as graph structure + CHAIN firmware v0 (487 tests)
Head index (`apply.build_head_index`/`rules_producing`): a `<head-index>` hub with `hub -[headPred]-> rule`
per rule head predicate — the catalog-key→rule map as SUBSTRATE structure (queried via `relations_from`, no
Python dict), built to CHAIN's query shape. CHAIN v0 (`harneskills/isa/chain.py`): `chain(fact_g, rule_g,
goal_pred)` closes the demand set BACKWARD from the goal predicate through the head index (a demanded pred
pulls in the body predicates of every rule producing it, transitively), minting a VISIBLE `<demand>` control
node per predicate (the magic set, inspectable), then APPLYs only the relevant rules to quiescence.
DIFFERENTIALLY GATED vs `run_bank` over the full bank: CHAIN derives exactly the goal-predicate facts the
full closure does (complete for the goal) while NEVER applying an irrelevant rule — pinned by a bank where
the `likes` rule is provably skipped for an `is_a` goal, and a transitive goal reproduces `run_bank` exactly.
v0 scope: predicate-grain demand (restricts which rules run, not yet which tuples — bound-arg SIP is v1);
positive rules. See `docs/implementation_plan.md` Phase 4.3.

### Phase 4.2 — APPLY firmware v0: reified-rule match with a VISIBLE frame (482 tests)
`harneskills/isa/apply.py` — the first slice of the universal firmware, and the proof of its thesis on
the positive core. `apply_rule`/`apply_to_fixpoint` match a REIFIED rule (Phase 3.1's in-graph shape, read
straight from the rule node — "APPLY over reified rules") against the facts and EMIT the head, with the
binding environment held as VISIBLE graph structure: a partial match is a `<frame>` control node, each
binding a reified relation `<frame> -[?var]-> node` (GoalSolver's hidden bindings dict, now inspectable —
the 4.1 win). df seed-from-rarest (the only heuristic); EMIT monotone with CHECK-BEFORE-DERIVE (an existing
head fact is the memo → a recursive rule terminates under the SATURATE fixpoint wrapper); fuel-bounded.
DIFFERENTIALLY GATED against `run_bank` on single-atom, 3-way join, transitive recursion, and near-miss —
APPLY over the reified form derives exactly what `run_bank` derives over the Python `Rule`. The differential
gate caught a real bug: an in-graph frame binding adds an incoming edge to the bound fact node, making an
entity look like a rel node to `derived_triples` — fixed by GC'ing the ephemeral frames (nodes + binding
edges) after each pass (a preview of the one-graph-fold hazard). v0 scope: positive rules, literal
predicates, no fresh-RHS MINT; Python driver with visible bindings. See `docs/implementation_plan.md`
Phase 4.2.

### Phase 3.1 step 1 — canonical reified rule shape, 2.1/2.2-aligned (478 tests)
`rule_graph.write_rule` modernized so a reified rule is literally in the shape of the facts it rewrites.
(a) Every rule-structure node — rule node, shared var/literal nodes, per-Pat predicate nodes, role
relations — is now `control`-flagged, so a folded ONE-graph can segregate pattern-space from fact-space by
the control flag (the `goal.py` control-rel skip) instead of the current separate rule-graph — the
meta-circular one-graph milestone, unblocked by 2.2. (b) Each pattern atom is built in FACT SHAPE via
`add_relation` (predicate carried as a graded KEY `{is_a: 1.0}`, not a bare name), so the firmware's APPLY
can seed a pattern predicate through `nodes_with_key`/`has_key` exactly as it seeds a fact. Round-trip
(`rules_in_graph`) unchanged and exact (name-based read still works via the dual-write bridge);
differentially clean. SCOPING (with the user): Phase 3 is the prerequisite for Phase 4's firmware, which
needs the reified rule SHAPE not the "built by FORM rules" authoring — so the meta-circular FORM-rule
quote/eval wall is deferred as a purity milestone off Phase 4's path. Pinned:
`test_reified_rule_is_control_layer_and_pattern_predicates_are_keyed`. See `docs/implementation_plan.md`
Phase 3.

### Phase 2.2 — control TOKENS as keys, half 1: the name→key dual-write (475 tests)
A reserved control token (`<…>` syntax) minted as a NODE (`AttrGraph.add_node("<goal>")`) now ALSO
carries its token as a graded key `{<goal>: 1.0}` — the same dual-write `add_relation` already does for
control PREDICATES — so `nodes_with_key`/`has_key` can eventually replace the name-based
`nodes_named("<token>")` reads (the Phase-6 reader flip). Reserved to `<…>` names (an ordinary entity
like `Paul` gets no graded key). `AttrNode.embedding` filters `<…>` keys back out (like an inert node
reports none), keeping the fuzzy/similarity/`propagate` view token-free. T-norm is unaffected — a token
key is always degree 1.0 (identity for T_MIN/T_PROD), and degrees compose into `score` only via explicit
GRADE/FUZZY α-cut ops that crisp token matching never invokes — so the regular graded namespace is safe
(the `<…>` syntax gives the view-level distinction for free; no reserved namespace). ADDITIVE: the legacy
VALUED name stays (oracle bridge), no current reader changes; differentially clean. Repr ratified with the
user: graded key in the regular namespace + embedding `<…>` filter.

### Phase 2.2 — control TOKENS as keys, half 2: control-ness at the mint chokepoint (475 tests)
`AttrGraph.add_node` now applies the ratified control-ness criterion — reserved `<…>` syntax + NOT inert
⟹ `control=True` — so every control token is flag-queryable (`is_control`) for the Phase-6 reader flip;
inert provenance (`<j:…>`/`<axiom>`) is excluded (inert, not control); a caller's explicit `control=` only
promotes. The flag is READ in production (goal.py control-rel skip, DROP_CTRL, `_fingerprint`'s control-edge
exclusion), so this was run as a HYPOTHESIS gated by the full differential suite, not assumed additive.
RESULT: behavior-neutral across all 475 tests except one RATIFIED divergence —
`test_isa_drop.py::test_drop_of_a_fact_is_refused`: a bare edge-less `<go>` token is now control, so
`run_bank`'s orphan-control GC sweeps it (correct — orphan control scaffolding is ephemeral; real control
tokens always carry edges); the test re-establishes the token before use. So the anticipated
"family-by-family" caution proved empirically unnecessary — one content-blind rule at the chokepoint is safe.
2.2's only remaining item is the Phase-6 reader flip (`nodes_named`→`nodes_with_key`, node `startswith("<")`
→`is_control`), now SAFE but deferred with the dual-write name drop until the oracle retires. See
`docs/implementation_plan.md` Phase 2.2.

### Phase 1 exit cleanup — two pinning tests resolved (469 tests)
The prior session's two PRE-EXISTING failures were confirmed RATIFIED Phase 2.1/2.2 migration
outcomes (not regressions) and updated to lock in the new behavior:
`test_skip_inert_excludes_provenance_from_matching` builds its `uses` node with `inert=True`
(flag-first design — `Machine._inert` reads the `.inert` flag, superseding the name sniff);
`test_finding_reserved_predicate_silently_dropped_from_body` flips `not in`→`in` (the `?u uses ?r`
body clause is no longer silently dropped — name-based predicate reservation went away with the
predicate-key migration). Full suite green: 469 passed.

### Phase 2.2 — `_is_inert` name-sniff → `.inert` flag: NODE-INSTANCE migration complete (469 tests)
Every node-instance provenance-skip now reads the `.inert` FLAG instead of sniffing the node's name.
Flipped: the WORLD_MODEL subject-finder family — the 8 identical
`next((n for n in g.into(r) if not _is_inert(g.name(n))), None)` readers across
`authoring`/`deontic`/`forms`×3/`planning_kb`/`session`×2 — plus `decide.py`'s closed-world-predicate
collector and `universal.py`'s `entailed_negation_rules` node-loop; dead `_is_inert` imports dropped
from all 7 files. Precondition first: the last two UNFLAGGED provenance mint sites
(`provenance.ensure_axiom`'s `<axiom>` node, `axiomatize`'s `<axiom>--proves-->rel`) now pass
`inert=True`, so every `<j:>`/`<axiom>`/`proves`/`uses` node an `into(r)` subject-scan can encounter
carries the flag. Differentially clean against the still-name-based `rewriter` oracle.
The remaining `_is_inert` calls STAY name-based BY DESIGN (not deferred flips): pattern/literal-side
guards over rule/goal tokens (`goal.py:727/743`, `lowering.py:400/573`, `rewriter.py:78` — a literal
is a string, not a node); the `rewriter` oracle itself (`rewriter.py:59`, reads uniformly by name);
and the `to_attrgraph` bridge (`lowering.py:86`, Phase-6 expiry, arbitrary-input safety).
GUARD TESTS (`tests/test_meta_provenance.py`) pin the migration's precondition — `is_inert(n) ⟺
name∈{proves,uses,<j:…>,<axiom>}` after a prov-on run + `axiomatize`, on BOTH the oracle and ISA mint
paths — so a future unflagged mint fails loudly instead of silently leaking (the exponential-hang class
from the prior session); a third test pins that `<retracted>` is name-inert but NEVER `inert`-flagged
(so `_is_inert` name-fn is a strict SUPERSET of the flag; the marker hides a fact by name-mismatch, not
inert-skip). KEY FINDING for the NEXT 2.2 slice: `startswith("<")` is the ratified content-blind
RESERVED-SYNTAX criterion (`decision-control-ness-criterion`), NOT the content-list debt `_INERT_NAMES`
was — it must NOT be flipped to `is_control` (would misclassify `inert`-flagged `<axiom>` and unflagged
`<…>` tokens as entities). "Control tokens as keys" is representational work, not a reader sweep. See
`docs/implementation_plan.md` Phase 2.2.

## 2026-07-08

### Phase 0.5 (cont.) — `rewriter` retired from the PRODUCTION runtime (test-only oracle) (465 tests)

Migrated the last three production modules that still called the reference `rewriter` at runtime, so the
production runtime is now **100% the ISA engine**. `rewriter.py` is RETAINED deliberately as the
differential-test ORACLE (the "two independent engines must agree" safety net — it caught this session's
fired-keying bug); its outright deletion is sequenced for Phase 6, once firmware subsumes it. (User chose
"make it test-only" over full deletion, to keep the oracle.)

- **`Firing` relocated to `production_rule.py`** (an engine-neutral home). `rewriter` re-imports it for
  back-compat (`rewriter.Firing` still resolves); `surface`/`driver` now import it from `production_rule`.
  One class, sourced once (`Firing is` identical across all modules).

- **`query.ask`'s matcher → the ISA (`lowering.match_pats`).** A new pure one-shot matcher: lowers a Pat
  conjunction with `lower_conj` and runs `Machine.match`, returning `{binding-key -> node id}` — the ISA
  face of `rewriter.match`, with the same `skip_inert = not _pats_touch_prov` default and duplicate-binding
  collapse. Differential-clean vs `rewriter.match` on existential / who / literal-subject / conjunction
  queries. `query.py` now imports `match_pats as match`; the yes-no/who/nary read paths are unchanged.

- **`driver.drive` → the ISA.** A stratified phase runs via `run_rules(isa=True)` (per-stratum `run_bank`);
  a non-stratified phase is a PLAIN fixpoint = `run_bank` directly (no stratification, as the "plain
  fixpoint runner" intends). Neither surfaces a `Firing` journal — but every `drive` caller (session at
  :281/:337) already DISCARDS the return, and `explain` reads the backward `GoalSolver` trace, so nothing is
  lost. `driver` no longer imports `rewriter`.

- **`run_rules` `isa=False` fallback retained as oracle access.** It is NOT dead — `test_isa_interpose`'s
  differential drives BOTH engines through it (`isa=isa`), and ~30 tests use `run_rules`/`h.run` as the
  reference. `authoring` keeps its `from .rewriter import run` (documented oracle-only; no production caller
  reaches the branch). The `__init__` re-exports (`h.run`/`h.match`/…) likewise stay — dozens of oracle
  tests use them.

**Result: no production runtime path calls `rewriter`.** Remaining `rewriter` references are the retained
oracle: the `run_rules` `isa=False` branch, the `__init__`/`authoring` imports that expose it, and the 23
differential test files. Deleting `rewriter.py` (Phase 6) is now purely a test-oracle-retirement decision,
not a production concern.

### Phase 0.5 (cont.) — `session:480` onto the ISA; forward `rewriter.run` off the production path (465 tests)

Moved the LAST production forward-`run` caller (`session.py:480` rule-source recognition) onto `run_bank`.
An investigation first established this was **NOT Phase 4.1** (semi-naive SEED), contrary to the standing
note (`finding-session480-not-phase41`): the whole-graph "double NAC" was a `fired`-suppression keying bug,
not a frontier problem.

- **Root cause.** The `forms` list legitimately carries DUPLICATE rule keys (default forms in
  `RULE_SOURCE_FORMS` + the per-KB generators that regenerate those same defaults — 14 dupes:
  `rule.cond.do_not`, `rule.kw.very`, `rule.plural.people`, …). `rewriter` keys `fired` by
  `(rule.key, bindings)` so duplicates SHARE suppression (fire once); `run_bank` keyed `fired`
  PER-RULE-INDEX (`fired[i]`) so each duplicate fired independently → the Skolem-minting rule-source form
  minted TWO `<cond>` NAC nodes. (Only Skolem-minting rules exposed it; a deduping fact head would hide it —
  the same class as the Phase-0.3 INTERN/DEDUP fixes.)

- **The fix (lowering.py).** `run_bank`'s `fired` is now a single `set[(rule.key, sig)]` instead of a
  per-index list — exactly `rewriter`'s cross-duplicate suppression, robust to duplicate rules in any bank.
  Differential-clean: a rule listed twice fires once on both engines with identical derived triples.

- **`session.py:480` → `run_bank(self.kb, forms)`.** Whole-graph is correct — `normalize_surface` already
  strips every PRIOR sentence's `next`/`first` chain, so the forms see only the current sentence (no seed
  frontier needed). `run_bank` returns a count (recognition firings are not surfaced in `explain`), so the
  journal is unaffected — validated: the full 465-suite passes, including `test_universals`'
  verb-negation-folds-to-a-NAC canary. The now-dead `rewriter.run` imports dropped from `session` and `walker`.

**Deleting `rewriter.py` is now a mechanical sweep** (no forward-`run` production callers remain): the
`run_rules` `isa=False` fallback (`authoring.py:995`, dead in production — only non-`isa` test callers reach
it), `rewriter.match` (query.py + tests), `Firing` (surface/driver — a plain dataclass to relocate), and
`driver.py:55`'s non-stratified `run`. Phase 4.1 (semi-naive) remains a real PERFORMANCE item, off this path.

### Phase 0.5 (cont.) — coref walk + decide (both phases) onto the ISA engine (465 tests)

Peeled the last two non-blocked `run` callers off the forward `rewriter`: the coreference cursor walk
and the `decide` completion/defeat oracle. After this, the ONLY production `run` caller left is
`session.py:480` (rule-source recognition), which is genuinely gated on the semi-naive SEED frontier
(Phase 4.1). Every `run_rules` production caller now passes `isa=True`.

- **coref_walk → `run_bank(provenance=True)`.** The blocker (diagnosed last entry) was that
  `materialize_cursor`/`settle_tool` (Python helpers) minted the cursor scaffolding — `<coref>` token,
  `coref_mention`/`coref_a`/`coref_b`/`coref_pnext`/`coref_cursor`, the `settled` barrier — as FACTS, so the
  `<coref>`-gated `ADVANCE` rule's `drop` of `coref_cursor` was `DROP_CTRL`-refused. FIX: stamp all cursor
  scaffolding `control=True` in the helpers (the same tool-minted-marker discipline as Phase 0.3's
  `done`/`ranked`) — harmless on the rewriter path (it ignores the flag), and it lets the drop lower to
  DROP_CTRL over control edges. **CLASSIFIED DIVERGENCE (ratified):** COMMIT/CLASH are `<coref>`-gated, so
  their `same_as`/`not_same_as` heads are now CONTROL-stamped (like the walker shortcut) where `rewriter`
  made them facts — defensible: a coref verdict is a retractable belief, control-layer is its home, and
  matching ignores the flag so `same_as` propagation is unaffected. `session.py:312` DEMAND_COREF migrated
  too (the demand→`<call> coref` rules; the tool runs the walk). The now-dead `rewriter.run` import dropped.

- **`decide` phase 1 → `isa=True`.** The completion/defeat/entailed-negation reasoning (the CWA oracle,
  `[*rules, DEFEAT_SEED]`, provenance ON, stratified) now runs on `run_bank` — differential-clean on
  `test_decide`/`test_riddles`/`test_cards_*`/`test_contract` (162 green in the decide-adjacent set). With
  phase 2 already migrated (prior entry), `decide` is FULLY on the ISA. The `run_rules` `isa=False` fallback
  (`authoring.py:995`) is now dead in production (every caller passes `isa=True`); it survives only for
  non-`isa` test callers until `rewriter` is deleted.

**Deleting `rewriter.py` now gated on ONE production caller:** `session.py:480` rule-source recognition,
which whole-graph `run_bank` double-fires (the Skolem NAC-pattern form needs the semi-naive `<fresh>` SEED
frontier — Phase 4.1). Also remaining: `rewriter.match` (query.py + tests), `Firing` (surface/driver),
`driver.py:55`'s non-stratified `run` — mechanical once Phase 4.1 lands.

### Phase 0.5 (cont.) — INTERPOSE opcode; TMS retraction onto the ISA engine (465 tests)

Built the **`INTERPOSE`/`RESTORE` opcodes** (isa-reference.md "Reserved: INTERPOSE / RESTORE", ratified
2026-07-07) and moved truth-maintenance retraction off the forward `rewriter`. This peels the retraction
callers (`retraction.retract`, `decide` phase 2) and clears one of the two gates on deleting `rewriter.py`.

- **`INTERPOSE rel obj marker` / `RESTORE rel marker obj` (machine.py).** INTERPOSE hides an edge
  REVERSIBLY: `rel -> obj` becomes `rel -> <marker> -> obj` by splicing a fresh CONTROL marker
  (`<retracted>`), so `_relation_exists` is false NATURALLY and the matcher (which skips the inert/control
  marker) never learns what retraction is. RESTORE is the exact inverse (`INTERPOSE ∘ RESTORE = id`). §5
  reframes from "no opcode mutates a fact edge" to "the sole fact-edge op preserves its pre-image — no
  IRREVERSIBLE loss"; `DROP_CTRL` still refuses facts. **Deviation from the spec's illustrative
  `assert edge_is_fact`:** interposition is reversible, hence safe on ANY live edge, so it requires only
  that the edge exists — necessary because a retractable walker shortcut is now CONTROL-stamped and the
  cascade must still hide it.

- **`rewire` → `INTERPOSE` lowering (lowering.py).** `_lower_bank_rule` no longer rejects `rewire`;
  `lower_rewire` recognizes the reversible-interposition triple `[cut(rel,obj), link(rel,m), link(m,obj)]`
  (`retraction.INTERPOSE_RULE`, the sole `rewire` in the system) and emits one `INTERPOSE`. Any other rewire
  shape (bare cut/link — test fixtures only) stays `Unlowerable`. `rewriter`'s `rewire` path is untouched,
  so `test_rewire.py` (direct-on-rewriter) still passes.

- **Per-rule provenance-awareness in `run_bank`.** A META/TMS rule that NAMES provenance (the CASCADE's
  `?j proves ?f` / `?j uses ?rel`) must SEE the inert `<j:…>` nodes that `skip_inert` hides. `run_bank` now
  builds a second `skip_inert=OFF` machine and routes each rule to it iff `rule_touches_provenance(rule)`
  (any LHS/NAC literal is inert) — exactly `rewriter`'s per-rule `match_inert` (`_pats_touch_prov`). CASCADE
  is prov-aware (sees `<j:>`); INTERPOSE names only `<retract>`/`targets`, so it keeps the fact-only view.

- **Routed `retraction.retract()` and `decide` phase 2 to `isa=True`.** The CASCADE + INTERPOSE rules now
  run on `run_bank`. Differential-clean vs `rewriter`: retracting a premise hides the fact AND cascade-hides
  its derived consequent identically on both engines (`test_isa_interpose.py`, and `test_walkers`'
  shortcut-is-retractable, `test_decide`, `test_riddles`, `test_retract_rules` all green on the ISA path).

**coref_walk still on `rewriter`, blocker now precise (distinct unit):** its `materialize_cursor` Python
helper mints the `coref_cursor` scaffolding as FACTS (`add_relation`, control=False), so the `<coref>`-gated
`ADVANCE` `drop` is `DROP_CTRL`-refused — the same tool-marker-stamp class as Phase 0.3. Unblocking it needs
the cursor scaffolding minted control in `materialize_cursor` AND validating the resulting `same_as`-as-control
divergence (COMMIT is `<coref>`-gated, like the walker shortcut). Deleting `rewriter.py` now gated on: coref
(this) + `session.py:478` rule-source recognition (semi-naive SEED, Phase 4.1).

### Phase 0.5 (cont.) — `run_bank` PROVENANCE MINTING; cpg + walker onto the ISA engine (459 tests)

Built the biggest remaining `rewriter`-peel lever — **in-graph justification minting in `run_bank`** —
and migrated the two callers it fully unblocks. Differentially gated against `rewriter.run` every step.

- **`run_bank(provenance=True)` mints justifications exactly as `rewriter._apply` does.** A firing that
  CREATES new fact relations gets a `<j:RULEKEY>` node with `proves`->each new fact and `uses`->each LHS
  premise it matched (provenance.py). Threaded through the lowering: `lower_conj`/`lower_lhs` collect the
  premise rel-node registers, `lower_rhs` the head rel-node registers, `_lower_bank_rule` returns both;
  the driver snapshots the node set before each firing so `made_facts` = head rels NEWLY created (a
  deduped/existing rel is not re-proven, the analog of `rewriter`'s `if not _relation_exists`). Provenance
  forces `skip_inert` ON (the J's it mints must be skipped by later rounds). Differential test
  `test_isa_reasoning_parity.py`: identical proven+uses structure and no re-proving of deduped facts.

- **cpg recognition → `run_bank` (`isa=True`).** `analyze`'s `RECOGNIZER_RULES`/`JOERN_RECOGNIZER_RULES`/
  `MECHANISM_RULES` are pure positive frame/hazard recognition — no provenance needed (the detector reads
  derived triples, and benches actively filter provenance leakage), so run_bank's no-provenance path is a
  cleaner fit. Differential-clean on all three fixtures (plain cpg + joern-lowered): identical derived
  triples, empty diff both ways.

- **walker → `run_bank(provenance=True)`.** `walk_on_demand` drops the seed frontier (documented
  correctness-neutral: step 1 is `force_all`) and runs the walk on the ISA engine with tool servicing
  (`dec`/`refuel` `<call>`s) + provenance. All 14 walker tests pass incl. shortcut-has-provenance and
  shortcut-is-retractable. **CLASSIFIED DIVERGENCE (ratified, not a bug):** the arrive rule binds
  `<walker>` (a control token), so by the ratified control-ness criterion the minted shortcut `a is_a d`
  is CONTROL-stamped (`edge_is_fact` False) where `rewriter` made it a plain fact. This is defensible —
  a walker shortcut is retractable MEMOIZATION of a transitive path, so control-layer (deletable) is the
  right home; provenance is still minted, so `support_js`/retraction work unchanged.

- **coref_walk migration ATTEMPTED and REVERTED (blocked, as predicted).** Its rules all lower, and the 6
  `test_coref_walk` cases pass on `run_bank`, but the SESSION single-identity/clash path `drop`s a
  `same_as` LINK (a fact edge) on reject → `run_bank`'s `DROP_CTRL` refuses it (§5), `ControlEdgeError`.
  This is the INTERPOSE-gated reversible-retraction case (`decision-interpose-opcode`), the same fact-edge
  -drop blocker as the surface path had — not a mechanical migration. Reverted; stays on `rewriter`.

**Still on `rewriter` (need capabilities not yet built):** `coref_walk` + `session` DEMAND_COREF (fact-edge
retraction → INTERPOSE opcode); `decide`/`retraction` (`rewire` → INTERPOSE); `session.py:478` rule-source
recognition (semi-naive `<fresh>` SEED → Phase 4.1); the `run_rules` `isa=False` fallback (`authoring.py:995`,
now only reached by the retraction path). Deleting `rewriter.py` is gated on the INTERPOSE opcode + Phase 4.1.

### Phase 2.2 (slice) — surface scaffolding CONTROL-typed; `normalize_surface` onto `run_bank` (457 tests)

Acting on the Phase-0.5 finding (deleting `rewriter` is gated on the recognition scaffolding being
control-typed), landed the slice of Phase 2.2 that unblocks the surface-rewriting recognition.

- **The surface `next`/`first` token chain + surface tags are now CONTROL-layer.** `tokenize` marks
  the chain control (`add_node("<sentence>", control=True)`, `add_relation(..., control=True)`);
  `run_bank` gained a `control_preds` set and `lower_rhs` a PER-ATOM control rule — a head whose
  PREDICATE is a scaffolding predicate (`forms.SCAFFOLD_PREDS = {next, first, *SURFACE_TAGS}`) mints
  control REGARDLESS of the rule, so a recognition form can read the chain and mint CONTENT facts
  (fact) while its `next`/`first` BRIDGE stays control. This is the substrate finally matching the
  intent `forms.py` always documented ("the token chain is EPHEMERAL scaffolding (control), rewriting
  it is control-deletes-control, never fact deletion").

- **`normalize_surface` moved onto `run_bank`** (determiner strip + NP decomposition). Its `drop`s of
  `next`/`first` now target CONTROL edges, so `DROP_CTRL` permits them (was `ControlEdgeError`). The
  live Session's multiword decomposition, cross-name identity, pronoun/anaphora, and universals all
  pass on the ISA engine (`test_new_core`/`test_universals`/`test_verb_catalog`). The earlier "seed
  misfire" fear was a red herring: `_strip_surface` already removes each PRIOR sentence's chain, so
  whole-graph matching only ever sees the current line — no per-sentence seed needed here.

- **Retired two obsolete tests** (`test_isa_forward.py`): `test_solve_all_recognizes_rule_source_
  identically_to_rewriter` and `test_recognition_nac_completions_are_control_and_invisible`. They
  pinned RECOGNITION through the GoalSolver (`solve_all` over forms) — a superseded exploration with
  NO production callers (recognition is `run_bank`). Control-typing the scaffolding correctly makes it
  invisible to GoalSolver's reasoning matcher (`_facts_matching` skips control, §5), so GoalSolver can
  no longer recognize over the chain — which is the intended split (recognition sees scaffolding,
  reasoning does not). Zero production impact: `_strip_surface` removes the chain before GoalSolver
  ever answers. Test 1 also differentialed against the `rewriter` being deleted. Full note in-file.

**Still on `rewriter` (need run_bank capabilities that don't exist yet):** the RULE-SOURCE
recognition (`session.py:478` — whole-graph `run_bank` double-fires the Skolem NAC-pattern form → a
duplicate NAC clause; needs the semi-naive `<fresh>` SEED frontier, Phase 4.1); the TOOL-DRIVEN
provenance passes (`walker`, `coref_walk`, `session` DEMAND_COREF — need `run_bank` provenance minting
+ seeds); and the `run_rules` `isa=False` fallback (`authoring.py:995`). 457 tests green.

### Phase 0.5 (partial) — additive recognition migrated; surface-rewriting BLOCKED on Phase 2.2 (459 tests)

Started peeling the remaining `rewriter.run` callers toward deleting `rewriter.py`, and hit a
structural wall worth recording precisely.

- **Migrated (clean):** the ADDITIVE single-line recognition callers — each builds a fresh `tmp`
  graph and only tags/reifies (no edge surgery, no cross-sentence isolation): `deontic`, `procedure`,
  `planning_kb`, `query` (its `_KW_FORMS`/`QUESTION_FORMS` runs), and the degree-graph recognition
  (`authoring.py:175`). `run(tmp, …)` → `run_bank(tmp, …)`.

- **BLOCKED — the surface-rewriting recognition cannot run on `run_bank` as built.** A trial swap of
  `normalize_surface` died with `ControlEdgeError`. The surface-normalization forms `drop` surface
  `next`/`first` **fact** edges to strip determiners and decompose noun phrases (`forms.py:67`,
  `_determiner_forms`/`_DECOMP_FORMS`) — but `run_bank`'s `DROP_CTRL` REFUSES a fact-edge deletion
  (§5 fact-immutability, the invariant we gave it teeth for in Phase 0.3). And even setting that
  aside, whole-graph `run_bank` loses the seeded incremental isolation the live Session needs
  (`session.py:473`: "re-running forms over old chains misfires" — 25 Session tests failed the
  trial). Reverted; the Session/normalize paths stay on `rewriter`.

- **The finding reorders the plan:** deleting `rewriter` is GATED on the recognition/surface
  SCAFFOLDING (tokens + the `next`/`first` chain) being CONTROL-typed — which is exactly **Phase
  2.2** ("keyword/control tokens become keys on control-flagged nodes"). Control-flag the scaffolding
  and `DROP_CTRL` PERMITS the strip/decompose rewrites, so the surface recognition moves to
  `run_bank`. **Phase 2.2 is therefore a PREREQUISITE for finishing 0.5**, not a successor. (The
  `INTERPOSE` reversible-retraction opcode — `decision-interpose-opcode` — is the alternative: it
  makes the surface rewrite a reversible interposition instead of a fact-edge delete. Either
  unblocks it; control-flagging is the cheaper, already-planned path.) A separate, smaller blocker
  for the incremental Session: `run_bank` is naive (no semi-naive SEED / `<fresh>` frontier, Phase
  4.1), so per-sentence isolation is lost — handle alongside once the scaffolding is control-typed.

Net: the substrate's fact-immutability (a Phase-0.3 win) is exactly what stops the OLD surface
recognition — which mutates fact edges freely, rewriter-style — from moving over. The peel can't
finish until the scaffolding stops pretending to be facts. 459 tests green; the clean migrations
stand.

### Phase 0.4 — graded/coref reasoning passes onto `run_bank`; dynamic-key EMIT (459 tests)

The two reasoning passes the batch loaders (`load_facts`/`load_corpus`) and the live `Session`
still ran on `rewriter.run` now run on the ISA forward `Machine`:

- **`_coref_propagation`** (`same_as` propagation over content predicates) — plain-relation rules,
  already run_bank-lowerable; `run(...)` → `run_bank(...)` at both batch-loader sites.
- **`graded_rules`** (`propagate` → embedding write) — needed a new machine capability: a
  **dynamic-key graded SET EMIT**. `EMIT` gained `key_reg` (the attribute key is the NAME of the
  node in that register, resolved at apply time — so a `propagate` whose dimension is a BOUND var
  `?adj`→"urgent" writes `embedding[name(?adj)]`) and `raise_degree=False` (SET/overwrite, the
  semantics `rewriter.set_embedding` gives, vs the monotone max-raise a derived degree uses).
  `lowering.lower_propagate` is the ISA face of `rewriter._propagate_ops` (the `set` op; a literal
  dimension takes the static-key branch). Wired into `lower_rule` + `_lower_bank_rule`; routed at
  `load_facts`, `load_corpus`, and `session._assert` (the live graded pass — no longer journaled,
  since embedding writes are not relation firings `explain` traces).

Differential-clean vs `rewriter.run`: `test_isa_reasoning_parity.py` adds dynamic-key, literal-dim,
and an end-to-end graded-pass differential (`run_bank` == `rewriter.run` on `alice is very urgent`
→ `alice.embedding[urgent] = 0.8`). 459 tests green; suite 141s→~102s (the reasoning passes now take
the Phase-0.1-optimized path).

**Scope note for Phase 0.5 (delete `rewriter.py`):** the plan's "only remaining `rewriter.run`
callers" line was optimistic. Beyond the passes just migrated, `rewriter.run` is still called by the
module-level recognition/tool passes — `deontic`, `forms`, `query`, `procedure`, `planning_kb`,
`session._surface`/DEMAND_COREF, `walker`, `coref_walk` — plus the `run_rules` `isa=False` fallback
(`authoring.py:995`) and the degree-graph recognition (`authoring.py:175`). 0.5 must migrate ALL of
these (recognition ones are Phase-0.2-shaped; the tool-driven `walker`/`coref_walk` need the
`<call>` servicing run_bank already has) before `rewriter.py` can go.

### Phase 0.3 (cont.) — planner ROUTED onto `run_bank`; reasoning parity closed (456 tests)

The blocker the entry below names is closed: `plan()`'s reasoning + control AND the replan teardown
now run on the ISA forward `Machine` (`run_rules(isa=True)`), differentially clean against
`rewriter.run`. The planner is one engine end to end (recognition + reasoning + `DROP_CTRL`
teardown). What it took:

- **Literal-endpoint INTERN + relation DEDUP** (`isa/machine.py` `MINT.intern`/`MINT.dedup`,
  `isa/lowering.py` `lower_rhs`). Recognition compared graphs as SETS of triples, which hid two
  NODE-IDENTITY properties the planner's REASONING depends on:
  - a head endpoint that is a PLAIN LITERAL now canonicalizes to its graph-wide node
    (`rewriter.apply_rule.resolve_so`'s `nodes_named(nm)[0]`), so a downstream rule joins two
    head-derived literals by identity. This was the exact `test_cards_frontier` value→plan
    divergence: the 2-clause bridge minted `buy_charizard add have_valuable` on a FRESH
    `have_valuable` node ≠ the `<need> for have_valuable` node, so `candidate`/`viable`/`chosen`
    never fired and `solve`→'stuck'. (The bridge itself fired — it was NOT a control-stamp bug, as
    the prior entry correctly diagnosed; the gap was node canonicalization.)
  - a reified relation now reuses an existing `s -[rel]-> o` (`rewriter._relation_exists`), so a
    rule re-fired across outer control cycles stops accreting duplicate rel nodes and the graph's
    EDGE set (hence `planning._fingerprint`) reaches a fixpoint instead of growing every cycle. The
    "perf regression" the prior entry flagged was mostly this accretion — with dedup the loop
    settles in the same cycle count as the rewriter, fast.
- **Tool-minted control markers stamp control** (`planning._control_relation`). `done`/`ranked`/
  `price_known` are written by §8 TOOLS via `add_relation` (fact rel nodes); `DROP_CTRL` teardown
  would refuse them. The tool now stamps the rel node control when it targets a `<…>` token —
  content-blind (the reserved `<…>` syntax, the same criterion as `lowering._is_control_token`),
  never a predicate list. A fact a tool writes (`cheaper_than`, a price result) points at a domain
  node and stays a fact. (Under the rewriter's regardless-of-layer teardown the stamp is harmless.)
- Differential proof: `run_bank` == `rewriter.run` on the cards-frontier value→plan scenario
  (derived triples, `chosen` operators, and cycle count all identical). New regression tests
  `tests/test_isa_reasoning_parity.py` (4) pin INTERN, DEDUP, two-producer sharing, and the
  two-clause bridge differential. 456 tests green; `isa=True` is now LIVE at `plan()`/teardown.

Remaining `rewriter.run` callers: the reasoning passes (`_coref_propagation`, `graded_rules`) =
Phase 0.4 (needs a dynamic-key EMIT for `propagate`), then `rewriter.py` deletes (Phase 0.5).

### Phase 0.3 — control-layer machine capabilities built + tested; planner routing BLOCKED (452 tests)

The opcode/lowering machinery for putting the planner's control layer on the ISA `Machine` is built
and unit-tested (`tests/test_isa_drop.py`, 3 tests), but ROUTING the planner/teardown to it is gated
on run_bank reaching REASONING parity with `rewriter.run`. What landed (all off the default path;
`isa=True` driver is OFF):

- **Control-stamp at MINT** (`isa/lowering.py` `_rule_touches_control` + `lower_rhs`). A relation
  minted by a rule that references a `<…>` control token is flagged `control` at MINT. This is the
  producer-side, content-blind criterion — established INDEPENDENTLY of any `drop` rule, so
  `DROP_CTRL`'s fact-edge refusal keeps its teeth (a fact minted by a control-free rule stays a fact
  and its deletion is refused). **Design ratified with the user against `vision.md`**: control-ness
  = the reserved `<…>` syntax (forms.py/lint.py already treat it as reserved machinery) + structural
  propagation, NEVER a domain-predicate list in Python (the "no python logic" bright line). The §1
  "substrate doesn't distinguish control tokens" tension resolves via the §1 amendment (control-ness
  IS a borne attribute) + Phase 2.2 ("control tokens become keys on control-flagged nodes"). It
  strengthens §12.3: the lint-time "control rule must be gated" invariant becomes engine-enforced.

- **`drop` → DROP_CTRL** (`isa/lowering.py` `lower_drop`, wired in `_lower_bank_rule`/`run_bank`). A
  control rule's `drop` deletes a reified relation via `DROP_CTRL` over both bare edges (seeded from
  the LHS-bound endpoints, df-optimal); run_bank gc's the orphaned control rel node (matching
  `rewriter._remove_relation`). `rewire`/`propagate` still raise `Unlowerable`.

- **`<call>` tool servicing in `run_bank`** (`tools=` param; services pending `<call>`s at each
  rule-fixpoint via `dispatch.service_calls`, exactly `rewriter.run`'s loop). No provenance minted
  (parity with the planner's `provenance=False` path).

- **`run_rules(isa=True)`** opt-in per-stratum `run_bank` driver (`authoring.py`), OFF by default.

**Why routing is blocked (the honest gate):** stamping control at mint needs the PLANNER to mint on
run_bank. A trial `isa=True` at `plan()`/teardown surfaced (a) a correctness divergence —
`test_cards_frontier`'s value→plan bridge `solve` returns 'stuck' not 'done' (the 2-clause
`?o add have_valuable when ?o acts_on ?c and ?c is valuable` bridge has NO control tokens, so it is
a baseline run_bank REASONING-parity gap, not a control-stamp bug) — and (b) a perf regression
(run_bank is naive; no semi-naive/seeds). run_bank's RECOGNITION parity is proven; its REASONING
parity with `rewriter.run` on the planner+card-trader banks is the open gap the docs always named
(GoalSolver/run_bank "prove SEMANTICS not SPEED"). So `isa=True` is OFF everywhere; the planner
stays on the rewriter. `implementation_plan.md` Phase 0.3 — NEXT: close run_bank reasoning parity,
then flip the flag.

### Phase 0.2 — the four rule loaders recognize on `run_bank` (449 tests, suite 99s→82s)

The perf gate Phase 0.1 lifted was the only thing keeping RULE recognition on `rewriter.run`. All
four rule loaders now fold their CNL surface into `Rule` structure via `run_bank` (the ISA forward
`Machine`), matching `load_facts`/`load_corpus` which were already there:

- `authoring.load_rules` (native rule CNL), `authoring.load_universal_rules` (`if/then` NL
  universals), `authoring.load_loose_rules` (loose imperative CNL): `run(rg, …)` → `run_bank(rg, …)`.
- `machine_rules.load_machine_rules` (planner/control CNL — the perf-heavy `planning.cnl` bank):
  `run(rg, MACHINE_RULE_FORMS)` → `run_bank(…)`; the `from .rewriter import run` import dropped
  (no other `rewriter` use in that module).

Licensed by the existing whole-batch + per-sentence differential tests (`test_isa_runbank.py`):
`run_bank(_ALL_FORMS)` reproduces `rewriter.run` EXACTLY on recognized rule shapes across the
diverse corpus (every recognition form is a subset of `_ALL_FORMS`). 449 tests green, no output
change; the suite dropped 99s→82s (the machine-rule loaders now run the Phase-0.1-optimized path).

Remaining `rewriter.run` callers: the reasoning passes (`_coref_propagation`, `graded_rules` in
`load_facts`/`load_corpus`) = Phase 0.4, and the planner teardown `drop`s = Phase 0.3.
`implementation_plan.md` Phase 0.2.

## 2026-07-07

### Phase 0.1 — `run_bank` perf: df-seeding + bound-endpoint join driving (449 tests, 34× faster)

The gate everything in Phase 0 waits behind (the loader swap off `rewriter`). `run_bank` was ~89× slower than
`rewriter.run` on a large machine-rule bank (`planning.cnl`: 9.6s vs 108ms). TWO content-blind, semantically
transparent wins — each differential-tested green vs `rewriter.run` at every step (`test_isa_runbank.py`) — took
it to **2.6× on `planning.cnl` (273ms)** and **1.0–5.1× across all ten CNL banks, every output IDENTICAL**:

- **Name-index SEED fast path** (`isa/machine.py`). A `SEED(reg, name, "=", X)` was scanning EVERY named node
  (`nodes_with_key("name")`) and comparing values one by one — 8.6M `_valued_ok`/`get_attr` calls. It now hits the
  O(1) lexical accelerator `nodes_named(X)` (the KB-blessed discriminating index, Phase 2.3 — `nodes_named`/
  `name_count` exist precisely as "the selectivity the matcher seeds from"). Semantically transparent: `_by_name`
  is kept in sync with the always-VALUED NAME attr, so the candidate set is identical to the scan. Guarded on a
  `str` value so a hypothetical non-string name SEED falls back to the scan. Cut 88.8× → 33.1×.
- **Drive the join from the bound endpoint** (`isa/lowering.py`, `lower_conj`). A literal-predicate pattern like
  `(?co, next, and?)` whose subject an earlier pattern already bound was doing a FRESH `SEED next` over all ~200
  `next` nodes then a `SAME` to reconnect — a cross-product blowup (`body.and`: 26k intermediate states → 25 final;
  four `body.and.ellipsis*` rules: 16k steps each → ZERO results). It now reaches the rel node by `FOLLOW`ing from
  the bound (rarest, specific) endpoint + a name `TEST`. The set is identical (`{rel : edge(s,rel) ∧ name(rel)=p}`)
  because a conjunction match is a relational join — order-independent in its result SET — so this is the df-optimal
  join order, not a semantic change. Cut 33.1× → 2.6×; intra-match `_match_step` calls 3.86M → 243k.

The remaining factor is pure cross-round re-matching (~16 rounds; the semi-naive/`<fresh>` change-frontier, win #3 —
not yet needed: absolute times are ≤240ms and the intra-match pathology is gone). This lifts the perf blocker the
loaders' `rewriter`-swap (Phase 0.2) waited on. decision-attrgraph-rehost; `implementation_plan.md` Phase 0.1.

### AttrGraph re-host, item #3 sub-item (i) — recognition-NAC completions demoted to CONTROL-layer (441 tests)

The flagged residual for #3 (recognition off `rewriter`). Running the FORM rules through the `GoalSolver`
forward driver (`solve_all`) lowers their guard NACs to demand-completions whose NEGATIVES (`is_kw_not`/
`is_bnd_not`/`kw_not_not`) are pure surface scaffolding — the forward `rewriter` never materializes them
(its NAC is a match-time check), so the ISA driver over-produced visible facts. Fixed domain-blind, with
one boolean and no predicate list (`isa/goal.py`, `isa/attrgraph.py`):

- **`control_completions` flag** on `GoalSolver`/`solve_all` (default False). A RECOGNITION solve passes
  True → `_complete_negative` marks the materialized negative `control=True` (nested solvers inherit it).
  A REASONING solve leaves it False → `is_not P`/`overridden_not …` stay REAL facts consumers match
  positively (the `decide` line).
- **`_facts_matching` skips CONTROL relation nodes** (all 3 branches) — a demoted completion is invisible
  to fact matching structurally, not just by naming convention. Safe for recognition itself (a NAC negative
  is answered by `_complete_negative`'s cache, never re-read via `_facts_matching`); full suite green, so no
  reasoning path relied on a control node being matchable.
- **`AttrGraph.set_control(nid, flag=True)`** added (complements read-only `is_control`).
- Recognized `Rule`s stay BYTE-IDENTICAL to `rewriter` (the completions are NAC scaffolding, never read by
  `expand_rules`); the positive guard fact `kw_not` correctly stays visible (rewriter emits it too). New test
  `test_recognition_nac_completions_are_control_and_invisible` pins that the flag (not the predicate) demotes,
  and that a reasoning enumeration of a control completion returns nothing. decision-attrgraph-rehost.

### AttrGraph re-host, item #3 — GoalSolver gains value-invention + bound-literal pinning; recognition ports to the ISA (439 tests)

Toward "move the reasoning MECHANISMS out of `rewriter` so the ISA is the only engine" (user framing:
`FORM_RULES` may stay Python, but NAC/`propagate→EMIT`/interpose must not live in `rewriter`). Empirically
established that recognition runs on `solve_all` (the GoalSolver forward driver) — its NAC handling is
*already* the ISA's (NAC-as-completion, byte-for-byte with `rewriter.nac_blocks` on the `in`/last-token
guards). Diagnosing rule-source recognition surfaced TWO real gaps in the demand-driven engine, both now
fixed (`isa/goal.py`):

- **Skolem / value-invention.** A `<...>?` head token (`<cond>?`/`<rule>?`/`<use>?`) is a FRESH node per
  firing (what `rewriter.apply_rule`'s `fresh` dict and the ISA `MINT` do); `GoalSolver._materialize`
  resolved it BY NAME → one shared node → every clause of a rule collided into one mangled `<cond>`.
  Added `_head_endpoint`/`_skolem` — a `<...>?` head mints a fresh node keyed by `(rule, token, env)`, so a
  rule's RHS clauses share one node per firing, distinct firings stay distinct, and re-derivation is
  idempotent (shared across nested solvers). `_materialize` returns the rel node; `_is_skolem` gates on the
  `<`-prefixed bound-literal (excludes name-keywords `is?`/`a?` and bare singletons `<closed_world>`).
- **Bound-literal pinning.** `is?`/`a?` were matched BY NAME independently per body clause, so
  `?cs next is?, is? next a?` floated over every `is` node — a cross-product that duplicated clauses when a
  rule had several `is` tokens (fact recognition escaped it: one `is` per sentence). `_extend`/`_resolve`
  now treat a bound-literal as a NAME-CONSTRAINED variable: match the name, then PIN the node so later
  occurrences reference the same one (as `rewriter` binds it).

VALIDATED: rule-source recognition compiles byte-for-byte identical `Rule`s via `solve_all` vs `rewriter`
across 4 rule shapes + a full mixed corpus (the thief NAC rule, multi-clause `and` bodies, graded); fact
recognition already matched; **full suite 439 green (no reasoning regression from the core-binding change).**
Residual (a smaller follow-up): `solve_all` leaves the materialized recognition-NAC completions (`is_kw_not`
/`is_bnd_not`) as visible scaffolding facts — harmless to rule/fact output, but should be marked
control-layer so they can't pollute reasoning. Then recognition can move off `rewriter` for real.

### AttrGraph re-host, item #4 unblock — backward-engine PROVENANCE + contract oracle on the backward path (439 tests)

The load-bearing enabler for retiring `decide`/retraction (the §5 payoff): the backward ISA engine now
MINTs provenance, so `why` works on backward-materialized graphs, so the closed-world consumers can move
off `decide.solve` (whose phase-2 retraction is the last production fact-edge cut).

- **DISCOVERY (corrects the earlier scoping):** `decide.solve` phase-2 retraction is NOT reached only by
  one deliberate test — its aggressive completion over-asserts `is_not P` for EVERY closed-world entity
  (e.g. `ada`/`bo` both get `is_not cleared` → both "thief"), and phase-2 retraction is what repairs it.
  So retraction is load-bearing for ALL forward closed-world consumers; they must move to the backward
  engine's NON-aggressive demand-completion, which needs provenance for `why`. `explain`/`why` already
  reads IN-GRAPH `proves`/`uses` (not a journal, `surface.explain`), but `GoalSolver` never minted it.
- **`GoalSolver` provenance MINT** (`isa/goal.py`, `provenance=` flag, default off): when a rule
  materializes a head, mint `<j:rulekey>` + `proves→head` + `uses→each positive body clause's relation
  node` — the SAME substrate trace `rewriter.run` writes, deduped per (fact, rule) across semi-naive
  rounds/nested solves (`_justified`, threaded like `_materialized`). `_materialize` now returns the
  relation node id (+ `_rel_node` memo); `_find_fact_node`/`_justify` added; nested completion/∃ solvers
  inherit the flag. `solve_all(..., provenance=True)` exposes it. `provenance` import is lazy (avoids a
  `provenance → world_model → isa` cycle).
- **`load_corpus(..., decided_negation=False)`**: threads the plain-NAC compilation (no `decide`
  aggressive-completion rule) so the backward engine completes closed-world negation on demand.
- **Contract + riddles oracles migrated** to the backward engine (`test_contract.py`, `test_riddles.py`):
  `load_corpus(..., decided_negation=False)` + `solve_all(..., provenance=True)`. Same public contract
  (unique culprit, `why` names the elimination + `cleared`, the negative explained as a completion) with
  NO retraction / fact-edge cut. `_complete_negative` mints a premise-less `<j:complete.REL>` so a `why`
  on a closed-world negative renders the elimination step. `test_riddles_author_entirely_in_cnl` re-homed
  to the backward form (thief rule KEEPS its NAC; no generated aggressive-completion rule); the intermediate
  `positive_holds`/`negative_holds` checks made node-agnostic (any coref mention) since the node-level
  engine materializes on the same_as-class canonical.

- **§5 REFRAMED (user, 2026-07-07):** retraction-by-INTERPOSITION (`retraction.py`: `cut ?rel→?o` +
  relink through the inert `<retracted>` marker) is REVERSIBLE and marker-recorded — the fact node
  persists and the edge is reconstructible — so it is NOT the fact-LOSS §5 forbids. The invariant worth
  protecting is "the monotone reasoning fixpoint never loses a derived fact," which the backward engine
  satisfies BY CONSTRUCTION; the reversible `h.retract` belief-revision tool is a sanctioned control op,
  NOT a violation. Consequence: the planned blanket "`remove_*` refuses fact edges" guard is the WRONG
  shape (it would forbid the legitimate reversible rewire) and is DROPPED. `retraction.py` + `decide` +
  their tests STAY. The re-host retires the forward machinery for the OTHER arc reasons (domain-blind
  engine, goal-direction, one substrate), moving reasoning onto the backward ISA engine — not because
  retraction breaks §5. A future rule-based `<reconsider>` (un-splice on new evidence, `<retracted>` as
  KB vocabulary) would make belief revision pure banks, no machinery.

### AttrGraph re-host, Phase C item #1 FINISHED — `canonicalize` retired from BOTH load paths (438 tests)

The LAST fact-deletion in the loaders is gone: `authoring.load_facts` and `load_corpus` no longer call
the destructive `forms.canonicalize` node-MERGE. Coreference is now the additive `wire_same_as` link +
`same_as` propagation — §5-safe (only adds edges, never deletes a fact). (`decision-attrgraph-rehost`,
handoff item #1; the `Session._merge_unique` slice landed earlier the same day.)

- **`load_facts`**: `wire_same_as` → `run(_coref_propagation)` (compose facts across the links, so
  `urgent is gradable` reaches the surface `urgent` token of `alice is very urgent` before the graded
  rule fires) → `graded_rules` → **`forms.propagate_embeddings`** (NEW: unions graded/embedding attrs
  across each `same_as` class — the GRADED-layer counterpart of `same_as_rules`, a §8 tool since the
  path language can't join on embedding attrs, so degrees spread to every coreferent mention).
- **`load_corpus`**: same recipe, PLUS the returned `rules` now APPEND the `same_as` propagation so the
  forward `run_rules(kb, rules)` consumers (contract/cards/riddles) compose derived facts across links
  live (the merge gave that permanently). `closes` added to the propagation predicate set so a
  closed-world marker reaches a rule's `is not P` clause before `expand_rules` reflects it.
- **`GoalSolver` skips `same_as` propagation rules** (`_is_same_as_prop`): the node-level engine follows
  a `same_as` class natively (union-find in `_facts_matching`), so the copy rules are redundant — dropped
  at intake. This kept the ISA `solve_all`/`ask_goal` path fast (the appended propagation had ~2×'d those
  tests; suite back to ~53s) and re-confirms node-level == forward-propagation at the answer level.
- Internal-coupled `test_new_core` re-homes (additive coref replicates a derived fact across an entity's
  mentions): `outcome`/`served`/`placed`/`custs` helpers dedupe with a set; two raw-`run_rules` tests
  now bundle `same_as_rules` as the Session's reasoning bank does; the corpus `keys` assertion filters
  the appended propagation. `canonicalize` is now DEFINED but UNCALLED in production (test-only; a Phase
  D delete). Next §5 step — the `remove_*`-refuses-fact-edges GUARD — is gated on retiring the still-live
  `decide`/`retraction` interpose (the one remaining production fact-edge cut, item #4).

### ISA arc — deeper walker integration (a deferred non-arc slice, 423 tests)

With both honest-gate speed wins in (below), picked up the first deferred non-arc slice: generalizing
the long-range walker demand beyond the pure same-relation transitive-closure shape
(`harneskills/isa/{walker,goal}.py`; `tests/test_isa_goal_walker_linear.py`, 8 tests).

- **Linear recursion over a DIFFERENT base relation.** `goal._closure_bases` maps a derived relation
  that is the transitive closure of a base — `anc(a,b):-parent(a,b)`, `anc(a,c):-parent(a,b),anc(b,c)`
  (left- OR right-recursive step) — to that base. `Walker` gained a `mint_rel` so it WALKS the base
  (`parent`) while materializing the discovered shortcut AS the derived relation (`anc`) — walk one
  relation, mint another. A relation is only treated as walkable when its head rules are EXACTLY
  {base, step}; any other contributor to it would be a derivation a base-edge walk cannot see, so we
  fall back to tabling (completeness before speed).
- **A walker for an INTERIOR reachability subgoal.** `_walk_applicable` now fires for a ground
  reachability subgoal arising *inside* a larger tabled query (the check moved into the fixpoint loop,
  a `_walked_goals` set makes it once-only), so a body clause like `anc(?x,?y)` with both ends
  SIP-bound is carried by a walker instead of the tabled chain, materializing only the shortcut.
- **Soundness fix the generalization surfaced.** A transitive-closure walker answers ≥1 hop, so a
  reflexive `rel(a,a)` holds ONLY via a real cycle — the old `subj==obj` 0-hop short-circuit was
  latently unsound (it claimed reflexive reachability with no cycle, diverging from tabling). The
  target check now runs before the visited-skip so a ≥1-hop path back to the source is found, and the
  path reconstruction handles the cycle. Pinned on cyclic graphs for BOTH the linear and the
  same-relation shapes.

All differential-tested against tabling (the trusted oracle, itself validated against the forward
closure): agreement left- and right-recursive, fuel bounds the reach, free-object goals still table,
the interior subgoal is walked, and a 300+-pair random sweep over cyclic `parent` graphs (incl. every
reflexive pair) matches tabling exactly. 423 tests green. Uncommitted on top of `a31e264`. Memory
`finding-isa-reference-machine`.

### ISA arc, the HONEST GATE — semi-naïve delta parity (slice 2 of 3, 415 tests)

The second speed-parity win, on top of seed-from-ground (below). `GoalSolver.solve` was a naive
`while changed` fixpoint that re-joined every demanded goal's WHOLE body every round, rediscovering
answers it already had — the O(rounds) round-churn that kept the transitive-chain curve ~O(n^3.8).
Now `solve` is **semi-naïve** (`harneskills/isa/goal.py`): a goal's body is joined in FULL exactly
once — its first evaluation, the seed (`self._full_joined`) — and thereafter only against the previous
round's DELTA (`self._delta_by_rel`) via the new `_delta_join`/`_delta_matching` (the classic
delta-substitution — for each body-clause position that clause draws from the delta while the others
stay full). Work drops to ~proportional-to-derivations instead of rounds × closure.

The careful part the design flagged: answers flow through BOTH the join tables AND the graph
side-channel (`_facts_matching` reads materialized facts across DIFFERENT table entries on the same
relation). Correctness is kept by folding EVERY table growth of a round into `next_new` — whether a
join derived it or `_facts_matching` picked up a cross-materialized graph fact — so the delta
propagates through both channels and no derivation is dropped (the arc's "correctness never traded"
invariant). MEASURED (walker disabled, pure tabling): n=50 2.27s → 0.59s, **n=80 15s → 2.9s** (~5× on
top of slice 1, ~37× vs the original 107s); exponent ~O(n^3.8) → ~O(n^2.9), one full power of n gone.

PROVEN answer-preserving (`tests/test_isa_goal_semi_naive.py`, 3 tests): a randomized differential
test sweeps >1000 goals across ~25 random interacting-rule programs (transitivity + linear recursion
over a DIFFERENT base relation + a two-relation join) and asserts each demand-driven answer equals the
FORWARD CLOSURE (`run_to_fixpoint`, the independent oracle) filtered to that goal — the strong catch
for a silent dropped delta; a structural pin asserts each goal is full-joined at most once
(`solver.full_joins <= #demanded goals`, non-flaky proof the round-churn is gone). All 415 tests green;
the suite got FASTER (48s → 38s). With both speed wins in, the honest gate is no longer blocked on the
goal-solver's asymptotics — retiring `rewriter.run` is now a re-hosting + deletion pass. Uncommitted on
top of `a31e264`. Memory `finding-isa-reference-machine`.

### ISA arc, the HONEST GATE — seed-from-ground parity (slice 1 of 3, 412 tests)

The ISA arc is semantically complete on the planner; the remaining move is the honest gate — the
reference `GoalSolver` proves SEMANTICS, not SPEED, so it cannot retire `rewriter.run` until it reaches
production parity (the three named wins: df-indexed rarest-anchor SEED, hub-flooding avoidance,
semi-naïve delta). A scaling probe measured the gap honestly: pure tabling on a transitive-closure
chain is ~O(n⁴) — n=40 → 4s, **n=80 → 107s**. Profiling pinned the cause: `derived_triples` (an
O(graph) rebuild of the whole triple set) called ~197k times for one n=40 solve, because every
`_materialize` bumps `AttrGraph.version` and invalidates its cache mid-derivation.

Landed the FIRST parity win — **seed from the ground endpoint** (`harneskills/isa/goal.py`;
`tests/test_isa_goal_seed.py`, 5 tests): `_facts_matching` now traverses LOCALLY from the bound
subject/object's edges (a relation `s -[rel]-> o` is a rel-node named `rel`) — O(degree), not
O(graph) — the same seed-from-ground discipline `rewriter._match` uses. Only a fully-unbound goal (an
inherent free-variable enumeration) falls back to a scan. `_materialize` went local too, plus a shared
`_materialized` memo (the monotone graph makes a repeat write an O(1) set hit). MEASURED: a
bound-endpoint solve now makes ZERO `derived_triples` scans (pinned by test); n=80 tabling **107s →
~15s** (~7×), and the O(graph)-scan-per-subgoal the profiling flagged as THE dominant cost is gone.
Exactly answer-preserving — all differential tests (`test_isa_solve*`, `test_isa_goal_predicate_nac`,
…) stay green, so this is purely the SPEED gate, answers unchanged. REMAINS: **semi-naïve delta** (the
naive fixpoint re-joins every goal every round; ~O(n^3.8) round-churn) — the next honest-gate slice,
and a careful one (answers flow through both the tables AND the graph side-channel, so a delta driver
must propagate through both without a silent incompleteness). Detail: `docs/graph low level
machine/isa-reference.md` ("The honest gate — seed from the ground endpoint").

### ISA arc, Phase 3 — the goal-directed planner, complete on a non-toy bank (407 tests)

Phase 3 remainder landed on top of the core (below). (1) The §8 rank `<call>` tool serviced
GOAL-DIRECTED: `GoalSolver` gained a `tools` registry — a TOOL-BACKED relation → a calculator `f(ag)`
run ONCE the first time a subgoal on that relation is demanded, materializing its facts. `cheaper_than`
is backed by `isa/solve.rank_cheaper_than` (AttrGraph-native cost comparison), so a `dominated` subgoal
demands the ordering → the tool mints `cheaper_than` → `dominated`/`best` complete. A COST preference
(chain step 1) now breaks a tie by cost, not the arbitrary fallback — `examples/coffee.py` (fetch(1)
beats deliver(5), dead buy_latte pruned, multi-need commitment) reproduces `plan()` exactly.

(2) The CARD-TRADER stress case (`tests/test_isa_solve_cards.py`, the non-toy target): `run_to_goal`
drives the real `corpus/cards_frontier_kb.cnl` + value→plan bridge + full `POLICY_RULES` deontic
override. The value→plan BRIDGE (reasoning DERIVES an operator effect, `?o add have_valuable when ?o
acts_on ?c and ?c is valuable`) is observed by the act loop via demand-forward add-resolution
(`_observe_simulated` demands `add(op, ?)` over the reasoning bank, so DERIVED effects reach `<now>`,
not just base facts); object-scoped deontic exclusion (a predicate-NAC completion) and its defeasible
override both work on the demand path. As predicted, no engine limits — one integration point (derived
effects at the act boundary). The ISA arc is now SEMANTICALLY COMPLETE on the planner; what remains is
the honest gate (production parity to retire `rewriter.run`).

### ISA arc, Phase 3 CORE — the goal-directed planner (plan → act → replan) (400 tests)

`harneskills/isa/solve.py`, `tests/test_isa_solve.py` (9). The forward `plan()`/`solve()` loop
SATURATES; this drives the SAME `PLANNING_RULES`/`SOLVE_RULES` through `GoalSolver` demand-forward — a
goal PULLS only its AND-OR chain (measured: goal-directed `reachable` is a STRICT SUBSET of forward's,
never the goal fact it doesn't need). Everything but `chosen` lowers to Phase-1/2 completion; the driver
owns only the selection. `derive_plan` demands `best` (pulling need/candidate/viable/cost_settled/
dominated along the chain), runs the `chosen` SELECTION per need, commits `chosen`, demands `before`.

The `chosen` selection is the ratified resolution CHAIN: preferences (the `dominated`/`best` CNL) resolve
a unique best DETERMINISTICALLY (mostly SUBSUMED, like `DROP_CTRL`); a genuine tie → a KB-prescribed
`tie_break` `<call>` (§8 seam); else a DETERMINISTIC-ARBITRARY pick (stable order, not RNG — reproducible/
provenance-safe). No operational policy hidden in the driver.

`run_to_goal` folds act/observe + replan. Control (`chosen`/`done`/viable/ready/…) is DRIVER-held and
injected into a fresh per-cycle `AttrGraph`; the persistent name-`Graph` carries ONLY monotone facts
(operators + goal + observed `<now> true`). So the forward engine's whole control-TEARDOWN bank
(`planning_teardown.cnl`, 15 gated drops) is SUBSUMED — a replan is a driver-state reset; nothing
control-layer is ever persisted, so there is nothing to tear down (the `DROP_CTRL` subsumption of Phase 2,
now for the entire replan machinery). Acting reuses `planning._perform_op`. Differential-tested vs
`planning.solve` (happy → `done`, withheld-effect divergence → replan → `done`, dead goal → `stuck`) +
the direction-preservation and teardown-subsumed gates the parity oracle is blind to.

PERF (pure, no semantics): `AttrGraph.version` (monotonic mutation counter) + a version-keyed
`derived_triples` memo (returns a frozenset). The goal solver snapshots per subgoal across many nested
solvers (~38k full-graph scans for one small plan → the dominant cost); the cache cut a plan derivation
~12.7s → sub-second and the ISA test bucket ~18s → ~4s. Phase 3 REMAINDER (not built): the rank `<call>`
tool serviced goal-directed (cost-based preference), then the card-trader `have_valuable` stress case.

### ISA arc, Phase 2 — existential NACs + `DROP_CTRL` subsumed (390 tests)

The planner's ground negation shapes now lower goal-directed. `harneskills/isa/goal.py`, additive,
NO shipped-engine change. `_lower_nac` PARTITIONS a rule's NACs by whether a clause introduces a
NAC-LOCAL free var (a binder the positive LHS does not bind): fully-bound stays the Phase-1 ground
`R_not` completion path; a free var makes the clause EXISTENTIAL, grouped by shared free var
(`_nac_groups_free`, the forward engine's `not (A and B)` vs `not A and not B` partition) and applied
per env as a demand-driven EMPTINESS check (`_exist_nac_blocks`/`_group_satisfiable` — the group
joined and solved to COMPLETION in a nested solve, same soundness discipline as `_complete_negative`).
This lifts both shapes Phase 1 rejected: ¬∃p `not ?o blocked_by ?anyp` (variable object) and grouped
¬∃x `not ?x A and not ?x B` (shared free subject). Fixed a Phase-1 over-strictness: `not ?a consume
?b` with `?b` LHS-bound is a GROUND NAC, not ¬∃ (only a NAC-LOCAL free var makes a clause existential).

**`DROP_CTRL` is SUBSUMED, not needed** — the load-bearing finding. The block/unblock idiom's
`drop ?o blocked_by ?p …` control retraction exists only to undo a block the FORWARD engine asserts
prematurely; on the demand path `blocked_by` is computed against COMPLETE reachability, so no stale
block is ever asserted and the `drop` rule (empty rhs) is INERT on the goal path. DIFFERENTIAL-TESTED
against the ACTUAL planner driver — the repeat-`run_rules`-until-stable loop of `planning.plan`, where
`drop` IS load-bearing — over a 2-step precondition chain: the goal solver reproduces the loop's final
`viable`={opa,opb} / `reachable`={water,coffee,done} exactly, `blocked_by` empty in both. (A lone
stratified `run_rules` sweep UNDER-derives — the mutual viable↔reachable recursion needs the loop.)

**The one Phase-3 residual, isolated.** The `chosen` commit rule's grouped NAC references its OWN head
(`not ?x chosen …`): a non-stratified SELECTION the forward engine resolves by commit-ORDER, not
completion. `_lower_nac` REJECTS it (a grouped existential NAC whose predicate == a head predicate) —
never silently mis-answers. Loading the WHOLE `corpus/planning.cnl` bank raises on exactly this one
rule; every other planner rule lowers. Phase 3's remaining scope is precisely operational choice for
`chosen`. `tests/test_isa_goal_existential_nac.py` (10); `test_isa_goal_nac.py` updated (9). Docs:
`isa-reference.md`, `isa-card-trader-coverage.md`. Memory `finding-isa-reference-machine`.

## 2026-07-06

### ISA arc, Phase 0 + Phase 1 — predicate-NAC generalization on the goal path (380 tests)

The ISA migration's first two phases (handoff "Next step"): make hardcoding structurally impossible
by moving reasoning onto the label-less / goal-directed machine, with the card-trader banks as the
differential-test oracle.

- **Phase 0 — the coverage map** (`docs/graph low level machine/isa-card-trader-coverage.md`). Every
  card-trader bank's rules (`policy`/`risk`/`preference`/`cards_reasoning`/`planning`) against the
  opcode set, each row marked COVERED / PHASE 1 / PHASE 2 / PHASE 3. The bulk of the domain reasoning
  (positive conjunction, transitive closure, graded α-cut, MINT reification) was already covered; the
  load-bearing gap was NAC on relation markers.

- **Phase 1 — predicate-NAC completion** (`harneskills/isa/goal.py`). The NAC→materialized-positive
  completion (previously copula-only, `not ?c is P` → `is_not`) generalizes with NO new mechanism to
  an arbitrary relation marker: `_lower_nac` rewrites `not ?s R o` → a positive body clause
  `?s R_not o` (the copula is just `R = is`), records `_neg_of[R_not] = R`, and `_complete_negative`
  answers a demanded `R_not(c, P)` by the same nested-complete-solve of `R(c, P)`. The nested solver
  is now handed the `_neg_of` map (its rules are already lowered, so it can't rebuild it). This
  covers the card trader's whole negation surface — `overridden`, `stance`, `excluded`, `reachable`,
  `needs_price`, `ranked`, `dominated`, `best`. Out of slice, **rejected explicitly** (never silent):
  a variable-object NAC (`not ?o blocked_by ?anyp`, ¬∃o) and a NAC subject the body never binds
  (`not ?x chosen <yes>`, ¬∃x) — the grouped existentials, deferred to Phase 2.

- **Differential-tested against the STRATIFIED forward driver** (`authoring.run_rules`, NOT
  `rewriter.run`) on the REAL banks (`tests/test_isa_goal_predicate_nac.py`, 6 tests): the
  `preference.cnl` stance rules (where `neutral` is a DEFAULT defended by two ground NACs) and the
  full `policy.cnl` override bank. The goal-directed completion reproduces the stratified answer
  EXACTLY, including the demo's keystone (`today outranks standing` → `sell overridden` → the
  exclusion lifted). Why the stratified driver is the oracle: `rewriter.run` is a naive single
  fixpoint that evaluates a NAC against a partial graph, so it derives the unsound `op stance neutral`
  alongside `op stance encouraged`; the completion's nested-complete-solve is the goal-directed
  analog of stratifying the producer below the consumer, which is what makes it sound.

- **`isa-reference.md`** gained a "Predicate-NAC generalization (DONE)" subsection + a Phase-2 entry
  atop "Next slice". `test_isa_goal_nac.py` renamed/clarified: a relational GROUND-object NAC now
  lowers (no longer rejected); only the existential shapes (¬∃o, ¬∃s) are rejected — two tests pin
  each. Memory `finding-isa-reference-machine` updated.

### Planning-problem CNL surface — author operators + state + goal in one `.cnl` (337 tests)

A whole planning INSTANCE can now be authored in CNL and handed straight to `planning.solve` —
no Python problem-authoring. `harneskills/planning_kb.py` adds `load_planning_kb(text, graph=None)`
(the ONE entry point the TUI calls) + `PLANNING_KB_FORMS`, lowering readable lines to the EXACT
edges the Python seeders (`seed_operator`/`seed_state`/`seed_goal`) produce:

- `make_coffee needs water` → `O --pre--> C`; `make_coffee produces have_coffee` → `O --add--> C`;
  `make_coffee removes water` → `O --del--> C`; `make_coffee costs 3` → `O --cost--> "3"` (opaque
  data-node, vision §1); `fetch_water is priced` → `O --needs_price--> <yes>`;
  `we have water` → `<now> --true--> C`; `we want have_coffee` → `<goal> --want--> C`.

REUSED the `procedure.py` pattern end-to-end: dedicated recognition FORMS (like `PROCEDURE_FORMS`,
in the `authoring.FACT_FORMS` bare-triple idiom), parse each line in its OWN throwaway graph, then a
mechanical §8 reader transfers recognized triples into the real graph BY NAME via `planning._hub`
(get-or-create → shared condition nodes). The operator/goal SEMANTICS live in the forms (data/CNL),
not Python branches; NO engine or planner change. One collision handled: the goal keyword `want`
shares a name with the target predicate `want`, so the reader skips relations whose subject/object is
a surface-chain node (`first`/`next`/`<sentence>`). `costs X` lowers the datum OPAQUELY, so a graded
criterion (`costs cheap` + fuzzy comparator) is a drop-in tool change with no grammar change
(graded-means-selection-friendly, `docs/graded_means_selection_design.md`).

Example KB `corpus/coffee_kb.cnl` (+ demo `examples/coffee_cnl.py`) reproduces `examples/coffee.py`.
Tests (`tests/test_new_core.py`, 4 new): CNL edges == Python seeders (asserted equal); del/priced/
state coverage; unrecognized-line no-op; `plan`/`solve` reach the goal with cheapest-producer ranking.
Design note `docs/operator_goal_cnl.md`. FIRST-SLICE limits: single-token names, one pre/effect per
line (author several — they share by name); `we want`/`the goal is C` the noted state/goal alternative.

**SLM front-end debt registered.** This is new FACT-shaped surface the NL→CNL SLM does not yet cover,
so it is logged in the new **`docs/handoff_slm_surface_track.md`** (the retrain ledger for parallel
sessions) as NOT COVERED / trainable — a future retrain sweeps it up (see that doc's protocol).

### ISA goal path — NAC → materialized-positive completion (the last reasoning piece, 333 tests)

The goal-directed evaluator (`harneskills/isa/goal.py`) now handles negation, closing the goal path over
contract scenario 1 (graded routing + a NAC-gated default a derived fact defeats). Negation is NOT a
CHECK-ABSENT filter — it is the `decide` line on the demand-driven path (`memory/decision_forcing_a_decision`,
`harneskills/decide.py`):

- **`_lower_nac`** rewrites a rule's copula NAC `H :- BODY, not ?c is P` into a POSITIVE body clause
  `?c is_not P`, appended AFTER the positive LHS so the residual grounds the subject before the `is_not`
  subgoal is demanded. Only the copula `is` lowers this slice; a relational/variable-object NAC raises
  `NonStratifiable` (explicit, never a silent drop). Idempotent, so a nested solve re-lowering already-lowered
  rules is a no-op.
- **`_complete_negative`** is the single demand-driven producer for `is_not` goals: to answer `is_not(c, P)`,
  solve the positive `is(c, P)` to COMPLETION in a self-contained nested `GoalSolver`; materialize `c is_not P`
  (matched positively everywhere else) iff the positive has no answer, else answer nothing (the derived positive
  DEFEATS the default directly — no separate TMS pass on the goal path). The matching core stays PURELY POSITIVE.
- **Soundness.** The nested solve computes the positive's COMPLETE extension independently of the outer fixpoint
  round, so reading "the positive failed" is sound (the classic NAF-in-a-fixpoint bug — empty merely because a
  producer hadn't run — cannot occur). A negative cycle (`is(x,p) :- q(x), not is(x,p)`) is caught by the
  `_completing` up-stack guard → `NonStratifiable`. Stratified-only by design (`vision.md` §11).
- **`_materialize`** hardened to mint-and-register a missing endpoint node: a completion object like `urgent` may
  live only as a rule literal (never a base node), and the reified `c is_not urgent` must still anchor to a
  `urgent` node. Names are unique in this KB setting, so mint-if-absent is idempotent.

`tests/test_isa_goal_nac.py` (8): reproduces scenario 1's routing goal-directed (alice→express not regular;
bob→regular not express), pins that the negative is minted + matched positively and stays demand-scoped, and that
relational / negative-cycle NACs are rejected. Memory `finding-isa-reference-machine` extended.

---

## 2026-07-05

### Rule ISA — the cheap experiment BUILT: label-less attribute substrate + reference machine (299 tests)

Built the go/no-go artifact of `docs/graph low level machine/rule-isa-design.md` (the label-less-substrate
revision) and `memory/decision_labelless_substrate`: the opcode set as a small-step operational semantics
plus a runnable reference interpreter, exercised by HAND-WRITTEN instruction sequences — no rules, no
compiler. Isolated from the as-built engine (imports nothing from `rewriter.py`/`world_model.Graph`),
non-throwaway.

- **`harneskills/isa/attrgraph.py`** — the label-less attribute substrate. Opaque-identity nodes + a
  closed-key attribute bundle (`GRADED` degree∈[0,1] / `VALUED` open data), directed unlabeled edges. The
  label guard is structural: the sole index is `key→{nid}`, never by value — two nodes both `name="Paul"`
  stay distinct. Deterministic ids (no clock/RNG).
- **`harneskills/isa/machine.py`** — reference `Machine`. Matching core SEED/FOLLOW/TEST/JOIN (positive),
  FUZZY (graded SEED, α-cut + t-norm score), GRADE (graded α-cut or valued cmp), SET/DUP; effects MINT
  (Skolem/reify/chunk), EMIT (monotone graded raise / valued assert), DROP_CTRL (deletes an edge, REFUSES a
  fact edge). State = (regs, score); score composes by t-norm (min default, product selectable). Two-phase
  match-then-apply.
- **`docs/graph low level machine/isa-reference.md`** — the spec + the honest verdict.
- **`tests/test_isa_machine.py`** — 14 conformance programs.

VERDICT (what the experiment decided): the positive core + monotone/control effects + MINT enumerate
cleanly, and the vision.md §5 monotonicity invariant is now a PROPERTY OF THE OPCODE SET — no opcode
deletes a fact edge or lowers a degree, so illegal fact-deletion is unrepresentable (design payoff #1).
Existentials fold into MINT (no new primitive). Aggregation does NOT fit the per-state opcode shape (it
folds across the whole state stream) → keep it a `<call>` calculator, freeze the positive-core ISA.
Still design-hygiene, NOT the critical path (graded means-selection remains the immediate build). Memory
`finding-isa-reference-machine`.

**Then the lowering + differential test landed (304 tests).** `harneskills/isa/lowering.py` +
`tests/test_isa_lowering.py` (5 tests): a dumb `Rule`→ISA-program lowering, a name-`Graph`⇄`AttrGraph`
bridge (`to_attrgraph` — a former node NAME becomes the valued attribute `name="…"`, edges copied 1:1), and
a fixpoint driver (`run_to_fixpoint` — fired-suppression keyed by binding, the engine's own `fired` set, so
recursive/transitive rules terminate). `lower_rule` pivots each `Pat` on its rel node (SEED-by-name or FOLLOW
from a bound/literal anchor, then subject=predecessor / object=successor, binding fresh / `SAME`-checking
bound / `TEST`-ing literal; RHS→`MINT` reified relation), and raises `Unlowerable` on anything outside the
positive/monotone/non-graded fragment. Two machine ops added: `SAME` (register unification for already-bound
join endpoints) and `MINT.in_edges` (a reified relation needs an in-edge). RESULT: the machine reproduces
`rewriter.run` EXACTLY on a 2-clause conjunction, transitive CLOSURE (recursion), and a 4-clause join whose
last clause has both endpoints bound (`SAME`), plus the near-miss.

**Then graded α-cut lowering + the GOAL-DIRECTION shift (310 tests).** `lower_graded`: a non-inverted
`GradedCondition` lowers to one `GRADE(var, dim, threshold)` per dim — under the min t-norm exactly
`rewriter.graded_degree` (the bridge now carries embedding dims across as graded attributes). Differential-tested:
the machine's per-state score equals `graded_degree` on the passing bindings and the α-cut gates the same
derivations (`tests/test_isa_lowering.py`, +2). Then — steered by the user, *"switch from forward-rushing to
fixpoint to acting toward a goal"* (§6a "Everything is goal-directed") — `harneskills/isa/goal.py`
(`GoalSolver`/`solve_goal`, `tests/test_isa_goal.py`, +4): a demand-forward driver = rule-head index + sideways
information passing + tabling over the same positive core (no trail, no NAF). A `Goal` is a partial relation;
answering it materializes ONLY the demanded facts. MEASURED contrast: over two disjoint `isa` chains,
`run_to_fixpoint` derives the full closure of both, while `solve(isa, x, w)` materializes a strict subset and
never touches the irrelevant chain. `run_to_fixpoint` is now the differential-test harness and the contrast; the
DIRECTION is goal-directed.

**Then walkers — the long-range demand primitive (315 tests).** `harneskills/isa/walker.py`
(`Walker`/`walk_to_goal`, `tests/test_isa_walker.py`, +5): a fuel-bounded BFS demand token that carries a
reachability goal `rel(subj, obj)` hop-by-hop, spending one fuel unit per traversal — fuel is the content-blind
effort budget, so *"think harder" is literally more fuel*. It stays goal-directed (frontier confined to what the
source reaches), terminates through cycles (`visited`), and on arrival **materializes a shortcut** — the derived
transitive relation marked `shortcut: 1` (its provenance) — so a repeat query is O(1). Pinned: reaching `w` from
`x` needs 3 traversals, so fuel 2 fails and fuel 3 succeeds; a walk from the disjoint chain never touches `x`'s
facts; an unreachable target in a cycle terminates; a post-discovery small-fuel repeat succeeds on the direct
shortcut. This is the carrier a goal-directed driver spawns for an unbounded transitive subgoal instead of
enumerating it. The README was also reframed to the ratified principles (label-less attribute nodes +
goal-directed default as the headline, with a demarcated "What runs today" section separating the shipped
name-based engine from the built `isa/` reference slice).

**Then the walker was wired into `GoalSolver` (321 tests).** `tests/test_isa_goal_walker.py` (+6):
`GoalSolver(…, walk_fuel=N)` carries a **ground reachability goal on a transitive-closure relation** with a
fuel-bounded walker instead of tabling the whole chain — goal-direction with bounded long-range demand as one
driver. `_transitive_closure_rels` detects the exact shape `R(?a,?c) :- R(?a,?b), R(?b,?c)`; walking `R`'s base
edges *is* the transitive reachability, so the walker returns the same yes/no as tabling while materializing only
the one shortcut. Measured: `solve(isa, x, w)` under `walk_fuel` derives exactly `{x→w}` where pure tabling
derives `{x→z, x→w, y→w}` (a strict subset — bounded work); fuel bounds the reach (2 empty, 3 answers);
free-variable goals still fall to tabling; an unreachable ground goal returns empty with nothing materialized.

**Then the graded gate on the goal path (325 tests).** `tests/test_isa_goal_graded.py` (+4): a demanded goal
answered via a rule with a graded condition is **gated by the α-cut** — `GoalSolver._graded_degree` is
`rewriter.graded_degree` on the demand path (min over a condition's dims, α-cut at the threshold, min across
conditions). A failed cut suppresses the answer (an entity below threshold does not satisfy the goal); a surviving
answer records its degree in `solver.degree[(rel, s, o)]` (possibilistic — the most-confident derivation). Pinned:
a ground goal above the cut passes and records its degree; below the cut it is gated out with nothing
materialized; a free-variable goal returns only the entities that clear the cut; and the recorded degree equals
the engine's `graded_degree`. This is where goal-direction meets the graded layer. NEXT: NAC →
materialized-positive (the `decide` line) — the last reasoning piece for the defeasible contract scenario; then
deeper walker integration.

---

## 2026-07-04

### Direction reoriented — the §9 inversion, the agentic loop, correctness-for-flexibility (docs only)
A design conversation refined the canonical direction (no code; `vision_agentic.md` §7/§8/§9/§13 +
`README.md` edited, memory `decision_agentic_loop_inversion`). Standing conclusions: **the substrate owns
the agentic loop** and the SLM is a scoped `<call>` tool at ONE boundary (fuzzy intent → CNL) — §9
retitled "The SLM is a scoped transducer, not the loop" and given an **agentic-loop subsection** (trigger
→ **triage** [step 1, derivation not classification] → plan → act → observe → decide-next). **Procedures
are SUBGOALS, not scripts** — goal-directed planning with genuine but KB-bounded agency. **Generation of
artificial languages needs no model** (deterministic grammar rendering; search → clingo). **Correctness-
about-the-world is not a goal; auditable KB-anchored flexibility is** (§13 #9): trade world-truth +
formal-purity, never engine-faithfulness + provenance (the anchor). **Gradedness is possibilistic, not
probabilistic**, authored through natural hedges (`very is 0.8`) — already built in `authoring.py`. Next
build fully specced with locked decisions: graded means-selection (`docs/graded_means_selection_design.md`).

### Coverage / composition audit — the top open experiment, measured (273 tests)
`bench/coverage_audit.py` + `tests/test_coverage_audit.py` (8 tests) — the one load-bearing assumption
the whole agentic arc still ASSUMED rather than measured (`docs/vision_agentic.md` §6/§12,
`docs/handoff_redesign.md` TOP OPEN EXPERIMENT): does a small set of MECHANISM-level rules COMPOSE to
cover real bugs, or does the absent-premise long tail dominate — the Cyc-shaped risk that historically
killed this class of system? Run the vision's own §10/§12 prescription in-env, ZERO extraction (frames
hand-authored as if a CPG recognizer had run, same discipline as `test_code_frames.py`).

Domain: **Python resource- and collection-safety hazards** — 8 mechanism rules over one causal
vocabulary (iteration-consumes-collection, mutation, aliasing-propagates-mutation, acquire/release
lifecycle, mutable-default) + 2 structural-closure rules (happens-before / within transitivity), all
machine-rule CNL (DATA). **21 scenarios** across 5 categories: direct positives, NOVEL manifestations
of an encoded mechanism, adversarial near-misses, and real bugs needing an unencoded premise. Each
scenario carries an analyst `wish` (ground-truth buggy nodes) + `category`; the engine's hazard set is
MEASURED, never asserted — recall / FP-rate / miss-split are computed from measured-vs-wish.

RESULTS: **encoded-mechanism recall 100% (8/8, including 3 novel manifestations caught by composition
with NO dedicated rule** — recursion-as-iteration, mutation-through-an-alias, nested-loop containment);
**0 false positives across 8 near-misses** (composition did not over-generate to get the recall);
**overall real-bug recall 61.5% (8/13) — the honest coverage number.** The MISS TAXONOMY is the
finding and splits cleanly: **2 CHEAP** (composable-but-unencoded — alias propagation for `use`,
release-dominates-all-exits; one more general rule, composes with existing frames → authoring, not an
engine limit) vs **3 FUNDAMENTAL** (absent-premise — taint/dataflow, concurrency, arithmetic/bounds;
a premise encoded at NO level, unreachable by any composition → the residual, irreducible Cyc-shaped
risk mechanism rules MITIGATE but do not ELIMINATE, §12). Actionable read: the coverage frontier moves
by adding general mechanism rules and importing whole premise CLASSES (a taint ontology, a concurrency
ontology), not by enumerating bug patterns — the §6 KB-authoring discipline, now with a number under it.

Two SILENT-FAILURE findings surfaced and are pinned as tests: (1) the machine-rule body parser SILENTLY
DROPS a body clause whose predicate is a reserved provenance name (`uses` = `h.USES`), collapsing the
rule to its first clause with no error (same family as the `is a X` rule-head silent-drop already in
the handoff's NL-surface gaps) — the audit's access frame therefore uses `accesses`; (2) a provenance
predicate-concept node (`proves`) spuriously inherits a derived type when provenance is on — invisible
to the public `ask` surface, but a raw hazard scan must exclude the provenance vocabulary.


### Direction reoriented — code / business-semantics / SLM arc (235 tests)
A first-principles design conversation (`docs/discussion/discussion.md`) independently RE-DERIVED
the one-substrate reasoner and mapped what it is FOR: a deterministic, auditable reasoning substrate
serving small language models in agentic coding. Synthesis saved as `docs/vision_agentic.md`
(CANONICAL DIRECTION, companion to `vision.md`); `handoff_redesign.md` reoriented; memory
`decision_agentic_direction`. Standing conclusions: the substrate IS the reasoner (don't adopt
clingo/Neo4j/GrGen/ACE as the engine — only as scoped `<call>` calculators / fact producers); a
model lives ONLY at the boundary (intent→CNL, reading tool output); Joern = fact producer folded as
`S P O`; frames are the CPG↔CNL join (no translator); coverage is bounded by rule GENERALITY not
count (mechanism-level rules); two-system split (content-blind statistical scoping → exact symbolic
verify); the parser is both the SLM's synthetic-data generator and its exact reward signal.

### Stage-1 code-reasoning probe lands — the arc's go/no-go (235 tests)
`tests/test_code_frames.py` (7 tests) — the `vision_agentic.md` §10 Stage 1, run with ZERO extraction
(no Joern/Neo4j), proving the substrate reasons over hand-authored **code frames**. The canonical
case is the **queryset-mutation-during-iteration hazard**, and it validates two vision claims
end-to-end:
- **§6 coverage-by-composition** — the hazard is DERIVED by composing two mechanism-level rules
  ("iterating a collection consumes it"; "mutating a consumed collection in the same loop is a
  hazard"), authored in machine-rule CNL. Nobody wrote a "queryset-mutated-in-its-own-loop" rule; it
  falls out of the composition (the intermediate `consumes` fact is asserted directly, so the
  composition is visible). The frame ontology (`Iteration`/`Mutation` as `is_a`-typed nodes with
  `iterates`/`mutates`/`within` role edges) is authored the §5 way.
- **§5 frames are the join (many-to-one)** — a recursion-shaped iteration (structurally nothing like a
  `for` loop in a CPG) materializes the SAME `Iteration` frame, so the one mechanism rule fires with
  no recursion-specific rule.
- **Stage 2 adversarial near-misses** all correctly refuse (mutation on a disjoint collection; mutation
  outside the consuming loop; read-only iteration) — catching the compositional-rules-over-generate
  failure mode with no extraction code. QA + why-trace over the frames work via `ask`/`explain`.

Next per `handoff_redesign.md`: clingo as a scoped `<call>` calculator (disjunction/exactly-one/
optimization) → Joern as a fact producer (one frame type first) → the SLM NL→CNL loop.

### SLM NL->CNL data generator + Colab training script (263 tests)
`harneskills/slm_data.py` + `tests/test_slm_data.py` (7 tests) + `scripts/finetune_nl2cnl.py` — the
fine-tuning pipeline, split into the IN-ENV testable half (data + reward) and the OFF-BOX GPU half
(the user has Colab). The generator produces validated (NL, gold-CNL, frame) pairs over 4 constructs
that parse cleanly to a distinct frame (typed fact, attribute, multi-word definite decomposition,
universal). Two vision commitments made concrete + tested:
- **Vocabulary stripped from the model's job** — fillers are NONSENSE tokens (colorless-green-ideas
  separability), so the model learns STRUCTURE + copy-through, not vocabulary. Every gold CNL is
  VALIDATED by parsing it (`slm.frame_graph`) — an invalid target raises, never trains silently.
- **Copy-through tested by a DISJOINT eval vocab** — `TRAIN_VOCAB`/`EVAL_VOCAB` share no tokens, so a
  correct eval prediction PROVES verbatim copying of a never-seen token, not memorization.
The Colab script (`scripts/finetune_nl2cnl.py`, NOT run by tests; unsloth QLoRA, 0.5-1B on a T4) grades
with `slm.grade` — FRAME-GRAPH match, the exact reward, catching confidently-wrong CNL a loss curve
misses — and reports per-construct exact-match on the held-out novel vocab. Its GPU imports are lazy so
the module loads without a GPU stack (syntax/import verified). Negation + undeclared-relation constructs
are OUT until they parse to a non-empty frame (the NL-front-end gaps). Highest-information experiment is
still the coverage/composition audit (recommended, deferred by the user's choice to run the fine-tune).

**FIRST FINE-TUNE RESULT (user-run, Colab):** a 0.5-1B QLoRA fine-tune scored **98% (78/80) on the
held-out NOVEL vocab** — attribute/multiword_def/typed_fact 100%, universal 90% (2/20). This validates
the SLM-boundary thesis: a small model learns structural NL→CNL with COPY-THROUGH of never-seen tokens
(disjoint eval vocab ⇒ real generalization, not memorization). Caveat: harneskills wasn't installed in
Colab so it fell back to STRING match; string-match is a strictly conservative lower bound of
frame-graph match, so the honest score is ≥98%. `scripts/eval_nl2cnl.py` added to re-grade the saved
adapter with the frame-graph reward and DUMP failures (no retrain).
- **Frame-graph re-eval (user-run) confirmed 98% and DIAGNOSED both misses as novel-token COPY-THROUGH
  failures** (not surface variants): (1) `any thorb is a quank` -> `every TRONK is a quank` — SUBSTITUTED
  a training token for the unseen `thorb` (smoothing an unknown word into a familiar one, the exact
  failure the discussion warned about); (2) `quanks are always sprods` -> `every QUEN is a SPRO` —
  mangled novel stems while depluralizing. Root cause: only ~12 tokens/category let the model memorize
  instead of learning "copy the slot". Silver lining: in the real architecture an unknown token is a KB
  failure, so both misses fall exactly where the KB is already the backstop — the failure mode
  validates the "strip vocabulary from the model's job" decision.
- **FIX ATTEMPT 1 regressed to 79%, exposing a data bug (a good lesson):** the generated 200/category
  cluster-onset vocab was enumerated with the coda as the slowest index and sliced CONTIGUOUSLY, so
  every train noun ended `b` and every eval noun ended `g`. The model learned the spurious regularity
  "nouns end in b" and REWROTE eval tokens (`drog`->`drob`) instead of copying — a structural
  train/eval leak, not a capacity limit. Confirms: **a bigger model is the WRONG fix** (it would learn
  the artifact harder); the first run's 98% already showed 0.5-1B suffices.
- **FIX ATTEMPT 2 (264->265 tests):** decorrelate the pool with a multiplicative permutation (stride
  coprime to pool size) so train and eval share the SAME onset/nucleus/coda distribution — verified:
  train & eval noun endings now both span 12 distinct chars, no ending dominates (was 100%/100%). No
  learnable feature separates the splits, so the only way to get an eval token is verbatim COPY.
  Regression test pins "no ending monoculture per category".
- **RE-TRAIN RESULT: 95% (76/80), substitution artifact GONE** — attribute/multiword/typed_fact all
  100%; the ONLY 4 misses are plural-universal depluralization of NOVEL tokens (`grumts`->`grumt`
  etc.), the residual hard edge predicted. INTERPRETATION: this is largely a nonsense-vocab ARTIFACT —
  depluralization is hard only because the stem is unseen; on real vocab (`customers`->`customer`) it
  is pretrained morphology, so the synthetic metric UNDERSTATES deployment performance. Plus it's KB-
  backstopped. CONCLUSION: SLM-boundary thesis CONFIRMED (0.5B, structural NL→CNL + copy-through,
  95-98%). Recommend NOT chasing 100% (dropping plural NL variants would game the metric, not improve
  capability). SLM pillar validated; the coverage/composition audit remains the top open experiment.

### clingo calculator — rule-driven aggregation (256 tests)
`asp.DISJUNCTION_RULES` + 2 tests — the clingo follow-up (a): RULES now build the disjunction call from
ordinary domain facts, so the calculator composes into pure reasoning with NO Python driver. A decision
is declared as facts (`?dec pred_of ?p`, `?dec domain_of ?type`), candidates are `?d is_a ?type`, and a
ruled-out member is `?d ruled_out ?p`; the rules materialize ONE `asp_solve` call and accrete every
candidate as `atom` / every ruled-out as `out`. MECHANISM: one materializer rule (bound only to the
decision → fires once) + plain-variable accretor rules that bind the existing call via its `decision`
link — because a fresh `<call>?` bound-literal token mints a NEW node per firing (verified: it does not
aggregate). End-to-end `run(g, DISJUNCTION_RULES, tools=TOOLS)` folds the winner back; ambiguous case
forces nothing (same soundness as the driver path). A fully NATURAL-language "exactly one of …" surface
stays gated on the two NL-front-end gaps (batch declaration-before-use; same-name merge).

### SLM NL->CNL exact reward signal — the final pillar's linchpin (254 tests)
`harneskills/slm.py` + `tests/test_slm_grader.py` (6 tests) — the buildable-here, GPU-free half of the
SLM pillar (`vision_agentic.md` §9). The whole fine-tuning plan hinges on a FREE, EXACT, automatic
grade for a candidate CNL translation, which we get because we own the parser: parse the candidate,
compare its FRAME GRAPH to gold. `frame_graph(cnl)` = the fact-level denotation (canonical
`s p o` strings, order-free, representation-independent); `grade(candidate, gold)` = parsed / exact /
missing / extra / overlap; `reward` = 1.0 on exact-match else soft overlap (for rejection sampling /
preference pairs).
- **Why frame-graph match, not parse-success or string similarity:** it catches the CONFIDENTLY-WRONG
  translation — valid CNL that parses cleanly into a DIFFERENT frame ("alice is a person" for "alice is
  a customer") — which the cheaper checks wave through. It also scores the SLM's copy-through behavior
  (carry an unknown token verbatim into the slot vs. normalize it — a normalized token lands a
  different frame). Both pinned by tests.
- **DEFERRED (needs a GPU/model, per §9):** the NL side of the training corpus (sample CNL from the
  grammar, back-translate to NL with a larger model), grammar-constrained decoding, and the fine-tune
  itself. This module is the reward/eval half, validated with neither.
- **Scope:** the frame graph is the FACT-level denotation (the templated fact/statement bulk); grading
  rule-CNL needs a behavioral probe (run the rule, compare derived facts), a documented extension.

### Joern CPG -> frames extractor slice — fact producer, no live JVM (248 tests)
`harneskills/cpg.py` + `tests/test_cpg_adapter.py` (5 tests) + `tests/fixtures/cpg_{purge,read_only}.json`
— the §10 Stage-4 "one vertical slice" of the Joern step (`vision_agentic.md` §4/§5). Joern is a FACT
PRODUCER, never a second engine: a CPG is our substrate in a different serialization, so loading it is
mechanical re-serialization. A NORMALIZED CPG export (faithful joern labels/edges — METHOD,
CONTROL_STRUCTURE+CONTROL_STRUCTURE_TYPE, CALL+NAME, IDENTIFIER; edges AST/REF/RECEIVER/ARGUMENT) folds
into `S P O` facts (`load_cpg`), recognizer rules materialize the SAME `Iteration`/`Mutation` frames
the Stage-1 probe hand-authored, and the IDENTICAL mechanism rules then derive the hazard — frames are
the CPG<->CNL join (§5), reasoning unchanged.
- **Decoupled from a live joern/JVM** (the decouple-the-extractor discipline): java + joern are absent
  here (joern is a JDK/Scala tool, not pip). The valuable, testable half — CPG STRUCTURE -> frames -> hazard
  — is built and exercised against hand-authored schema-faithful fixtures. Two pieces are explicit,
  DEFERRED seams pending a real `joern-export`: (1) `parse_graphson` (raw GraphSON wire decode, stubbed
  with a clear NotImplementedError); (2) the exact frontend lowering of `for`/method-calls (fixtures
  reproduce joern's schema from public docs — a faithful APPROXIMATION, not validated output).
- **Recognizer faithfulness:** variable IDENTITY via REF (distinct `items` occurrences unify on their
  shared decl); "within" via transitive AST containment (`ast_star`); the loop's INDUCTION VARIABLE is
  excluded by a NAC (its decl is loop-scoped, an iterated collection's is not) — verified (`iterates`
  binds the collection, never the loop var). Read-only iteration (`print(x)`) yields the Iteration
  frame but NO hazard.
- **Two-phase run (recognition, then reasoning):** the iteration recognizer's NAC pushes it into a
  later stratum than the positive mechanism consumers, so a single stratified pass runs consumers
  before frames exist. `cpg.analyze` runs the two banks in order — authoring around a stratifier
  limitation, not an engine change (vision §11 stands). The mutator LEXICON is inlined data (belongs in
  the KB as `X is a mutator` facts).

### clingo scoped calculator — constructive disjunction / exactly-one (243 tests)
`harneskills/asp.py` + `tests/test_asp_calc.py` (4 tests) — the RECOMMENDED-NEXT arc step, the ONE
reasoning capability the stratified single-fixpoint engine cannot express (no head-disjunction, no
model enumeration), DELEGATED to clingo behind the §8 materialized-`<call>` boundary rather than
built into the monotone fact layer (`vision_agentic.md` §3). Driving case = the gap the riddles
pinned (`finding_riddles_probe`): "exactly one door hides the prize; not door1; not door2; therefore
door3" — a POSITIVE conclusion by exhaustion that closed-world `decide` cannot reach (it would wrongly
conclude `not door3`, since door3 is unproven). Reasoning by cases forces it; clingo's unique stable
model entails it.
- **Opaque discipline honored (vision §1/§8):** the calculator NEVER parses atom node names — it
  assigns each an anonymous index, hands clingo only `sel(0..k-1)`, and maps the solution back onto
  the real nodes. Program: `1 { sel(0);…;sel(k-1) } 1.` + `:- sel(J).` per ruled-out member.
- **Sound — never guesses:** the winner is emitted only under CAUTIOUS entailment (selected in EVERY
  stable model). All-but-one ruled out -> one model -> forced. Two live options -> two models ->
  nothing. Unsat -> nothing. Tests pin all three.
- **Composes in the engine loop:** `run(g, rules, tools=asp.TOOLS)` services the call at rule
  quiescence and the folded-back winner re-seeds ordinary reasoning (a consumer rule fires on it).
- **Opt-in dependency:** clingo is imported LAZILY (only when the calculator runs), declared as the
  `asp` extra in `pyproject.toml`; the core package imports and reasons without it. Test guards with
  `pytest.importorskip("clingo")`.
- **Follow-up (noted in `handoff_redesign.md`):** aggregating N atoms into ONE `<call>` from per-match
  rule firings (rules building the call, not just consuming its result) is the remaining integration
  step; the spike seeds the call via a driver helper, which the vision explicitly permits.

### Behavioral contract suite — the swap-safety net (239 tests)
`tests/test_contract.py` (4 tests) — representation-INDEPENDENT tests that pin what the system DOES,
not how it is built, so engine parts can be SWAPPED later against a fixed spec (HRG-backed matcher,
clingo-delegated negation, SLM front-end, Joern extractor — the `vision_agentic.md` seams). Asserts
ONLY through the public surface (CNL in via `load_corpus`/`Session.submit`; answers out via `ask`/
`.answer` — strings and booleans, never internals). Three scenarios span the substrate: graded +
defeasible routing, closed-world elimination (the thief riddle), and the compositional code hazard.
The internals-coupled regression tests (`test_new_core`, `test_code_frames`) stay as the CURRENT-
engine defense; this file is the swap net. An engine-adapter parametrization is deferred until a
second engine exists (YAGNI).
- **Two NL-front-end gaps surfaced while building it** (recorded in `handoff_redesign.md`): (1) the
  batch loaders (`load_corpus`/`load_facts`) do NOT sequence declaration-before-use, so a declared-
  relation FACT parses only on the sequential `Session.submit` path (the code-hazard scenario authors
  via `Session`); (2) an `is a X` RULE HEAD is silently dropped by `load_rules` (returns 0 rules, no
  error) — a "report, don't drop" smell; relational and bare-copula-marker heads work.

## 2026-07-02

### Indefinite existentials (∃) — question side (228 tests)
First reasoning-expressiveness gap (user-picked over disjunction/aggregation/negation). An
existential QUESTION `is anyone happy` / `is anything a dog` means ∃ — "does ANY witness satisfy
this" — so it now binds a VARIABLE over all nodes (`query.EXISTENTIAL_SUBJECTS` -> `Pat("?w", p, o)`)
instead of matching the literal word "someone" as a node name. Fixes the real bug: a NAMED individual
witnessed nothing (`bob is happy` but `is anyone happy` -> **no**; now **yes**). `everyone`/`everything`
are universal and deliberately excluded; `they`/`it` are anaphora. This is the query-side dual of a
labelled-null witness.
- **Existential FACTS already reason soundly in the Session** and are pinned by tests: `someone is
  happy` materializes a witness that forward-chains through rules (`is anyone calm` -> yes), and two
  existential facts stay DISTINCT (∃x.solid ∧ ∃y.liquid — no false contradiction, each separately
  witnessed) because the un-canonicalized Session keeps each mention a distinct node. The witness is a
  labelled null (a fresh anonymous *constant* — NOT a variable, which would be ∀), per the
  design discussion.
- **Deferred (next slice):** the sound-under-canonicalization representation — an explicit null tag +
  blank identity (RDF `_:bN`), so ∃-facts stay distinct on the batch/`canonicalize` path and unlock RDF
  blank nodes / OWL `someValuesFrom`; plus witness IDENTIFICATION (`someone stole it. the thief is bob`)
  via the existing `same_as`/merge machinery. `tests/test_existentials.py` (+8). Bench unchanged
  (488/509, 95.2%) — ∃ is isolated to `someone`/`anyone`-subject questions.

### Elliptical copula conjunction/negation — `is round and big`, `is young and not rough` (220 tests)
The biggest remaining unrecognized bucket (handoff "RECOMMENDED NEXT"). A SHARED-SUBJECT ellipsis:
`and <mod>` / `and not <mod>` after a copula clause `?cs is ?co` reuses the clause's SUBJECT and its
`is`, folding `?cs is <mod>` (rl_lhs) or a NAC on `?cs is <mod>` (rl_nac). The full-clause conjunct
(`... and they are calm`) already worked via the generic clause; this is the one-token modifier the
generic clause can't fold. In the SHARED body spine (`authoring.BODY_SPINE_FORMS`), so it works in
`if…then` universals, the prose `HEAD when BODY`, and the machine grammar alike. Raw-NL probe
(depth-1): sentences **461→488**/509, accuracy **90.1%→95.2%**, QDep-1 **79%→91%**.
- **Four forms** (`_ellipsis_cond`): positive/negated × modifier-at-end / modifier-before-boundary.
  Disambiguation is content-blind — an elliptical modifier CLOSES its clause (last token, or followed
  by a boundary kw `then`/`when`/`and`, now tagged `is_bnd`); a token followed by a non-boundary word
  is a full clause `S P O` and the generic path handles it. The reused copula is pinned to `is`
  (`?prev k_pred is?`), so an ellipsis only chains off a plain copula clause.
- **Chaining + mixed polarity** (`round and big and small`, `young and not rough and big`): each
  modifier reuses the ORIGINAL subject+copula and marks itself `body_end`, so the head grammar and a
  further `and` continue past it. The prior conjunct is found by its object (the `body_end` token,
  unique per position), role-blind, so an ellipsis chains off a positive OR a NAC prior conjunct.
- **Two spine guards** so the inert `_BODY_AND` domino (which still marks the modifier `body_subj`)
  can't mis-fold: the generic clause and the `not`-clause both NAC `?cp is_bnd` (a boundary kw is
  never a clause predicate — kills the spurious `big then they` / `big and small`).
- **Latent-bug fix** surfaced by the first `not`-led prose `body_subj`: `_dropped_conditions`
  compared `_obj(...)` (a node id) to `"yes"` — the `kw_not`/`kw_drop` exclusion never fired. Now
  compares the node NAME; also counts a folded `k_obj` as consumed (an elliptical modifier is a
  clause object, not subject). `tests/test_universals.py` (+5).

### Lexicon-as-data cleanup — declarable variables/auxiliaries; content-blind stratify (215 tests)
Hardening the "nothing hardcoded in Python" rule (user audit). Three moves:
- **The engine no longer knows `is`.** Object-aware stratification was special-casing `pat.p == "is"`
  (relation-routing in the engine, §1/§10). Generalized `_prod_key` to key EVERY predicate on
  `(pred, literal-obj)` with variable-object producers as wildcards — content-blind, only refines
  deps, planning unchanged.
- **Function-word lexicon is now DATA.** The new grammar words (`PERSON_VARS`/`THING_VARS` variable
  classes, `UNIV_NOUNS`, `VERB_NEG_AUX`) were hardcoded tuples with no KB override — unlike the
  precedent (`declared_pronouns` etc. = DEFAULT | declared). Added `declared_rule_variables`
  (`X is a variable` -> `?<word>`, doubles as a plural universal noun), `declared_auxiliaries`
  (`X is an auxiliary`), `declared_univ_nouns`; `rule_var_name` is graph-aware; the verb-negation and
  plural-universal forms are now graph-derived generators (`verb_neg_forms`/`plural_universal_forms`,
  like `degree_grammar_forms`) — static DEFAULT banks + a Session-added declared extension. So a
  domain can extend the grammar lexicon as data (`critters is a variable` -> `Cold critters are kind`).
- **`is an Y` form** added (vowel-initial categories: `doth is an auxiliary` now parses).
`tests/test_universals.py`. Probe unchanged (284/311, 89.9%).

### Verb negation + object-aware copula stratification (213 tests)
Two paired negation pieces. Probe (depth-1, 25 theories): sentences 278→**284**/311; degradation
warnings 8→**3**. Memory `decision_universals_to_laws`, `decision_depythonization`.
- **Verb negation.** `S does/do/did not V O` -> a NAC on the relation `S V O` (`authoring._verb_not_sugar`
  per `VERB_NEG_AUX`; the do-support auxiliary is is_kw-tagged so the generic clause defers, like
  `is not`). `the cat does not like the cow` -> NAC `cat like cow`; `they do not eat the cow` ->
  NAC `?x eat cow`. Works inside a conjunctive body + verb head (needs the verb declared, so heads
  don't mis-decompose). `tests/test_universals.py`.
- **Object-aware stratification (content-blind).** `stratify` keyed on predicate NAME, so all `is X`
  collided and an `is not` NAC false-cycled through the overloaded `is` (with `goal.satisfied` etc.)
  -> the rule was dropped by graceful degradation. FIX: stratification is now object-aware for EVERY
  predicate — keyed on `(pred, literal-obj)`, with a variable-object producer (`?x P ?y`) as a
  WILDCARD every `P`-NAC depends on (`authoring._prod_key`). NO relation name is special-cased (vision
  §1/§10 — no engine routing by relation); it only REFINES deps (never adds a cycle), so every bank
  is safe (a predicate that always uses one object, e.g. planning's `viable <yes>`, collapses to the
  old name-keying). Now `if someone is young and they are not rough then they are calm` + `bob is
  young` -> `is bob calm` = yes (was degraded to no). The documented cleaner cure for the `is`-overload
  cycle (was a `decide`/de-pyth follow-up), done without hardcoding the copula.

### Multi-word definite entities + stopword df-cap — probe unhangs (210 tests)
Probe-driven robustness fixes; the depth-1 25-theory probe now COMPLETES (was hanging) at **278/311
sentences (89%), 198 answered, 89.9% acc, QDep-1 80% (all 80 answered), QDep-0 97%**. Memory
`decision_verb_catalog`.
- **Multi-word definite entity merge.** `the bald eagle` decomposes to head `eagle` + attribute
  `bald`, but the first-token definiteness marking tagged `bald`, not the head — so `eagle` never
  merged → O(k²) coref HANG (theory 3). FIX: mark the WHOLE definite NP span `is_unique`
  (`forms._definite_forms`: seed `def_np` after a definite determiner, propagate across the span,
  mark each). Head merges → 1 node → fast + correct (theory 3: 128s → 0.34s at 8/8).
- **Stopword df-cap.** A mis-parsed query (multi-word subject with no `the` shoves the VERB into the
  object slot) then coref'd a relation predicate with many instances → hang. FIX: a content-blind df
  cap (`Session.COREF_DF_CAP=24`, vision §14) — a name borne by >cap nodes is a STOPWORD, skip coref
  (a count is structure, not meaning). Makes the resolver robust to any such mis-parse.
- **Bench.** Queries entities WITH `the` (`does the S V the O`) so a multi-word entity decomposes the
  same on both sides. Residual: a COPULA question with a multi-word subject + bare predicate (`is the
  bald eagle young`) still can't split (the pre-existing Tier-3 limit). `tests/test_verb_catalog.py`.

### Plural-noun universals — `Cold things are kind` (208 tests)
A second universal surface, the biggest remaining unrec bucket in the depth-1 probe (~18 sentences).
`<Adj> <plural-noun> are <Pred>` (`Cold things are kind`, `Cold people are green`) = "all things that
are Adj are Pred" -> `?x is Pred when ?x is Adj`. `authoring.PLURAL_UNIVERSAL_FORMS` (per noun in
`UNIV_NOUNS`={things,people}) reuses the if/then rule fragment + variable machinery unchanged: the
plural noun is the bound variable (`things`→`?y`, `people`→`?x`, added to `forms.PERSON/THING_VARS`),
the leading adjective the single body condition, the copula predicate the head. FIRST SLICE: single
adjective + single predicate (positive → clean runtime, no stratification risk); multi-adjective +
`All`/comma (`All young, cold people are green`) stays unrecognized (never mis-folded).
`tests/test_universals.py`.

### Verb catalog + definiteness-merge — relational NL, fast (206 tests)
The n-ary/relational NL axis (the ceiling after universals→laws). Memory `decision_verb_catalog`;
`tests/test_verb_catalog.py`. **User-driven design call:** an undeclared verb is indistinguishable
from a multi-word noun phrase, and the engine has no learning yet (vision §10 lists induction as
OPEN), so we do NOT infer a verb from position — that is a weak stand-in for the deferred learning,
and "this word is a verb" is a MEANING commitment that brushes the content-blind line (§14). Verbs
are a CATALOG, declared as DATA (`eat is a relation`) like the rest of the domain; inference is
demoted to at most a linter hint. The CNL stays "caveman" (one base verb form); English inflection
is corpus-adaptation, not grammar.
- **The catalog reuses everything — almost no new code.** A declared relation word joins the surface
  KEYWORD set, so (a) the NP decomposition STOPS at it (the same fix that enables recognition — the
  bug and the feature are one) and (b) the generic body clause folds it inside a universal rule. So
  relational facts (`the dog eat the squirrel` → `dog eat squirrel`), verb-clause rules (`if
  something eat the cat then it chase the dog` → `?y chase dog when ?y eat cat`), and multi-step
  reasoning ALL worked out of the box once a catalog was declared — verified before writing any code.
- **The only new engine piece is the question side.** `forms.relation_question_forms` generates a
  `does S V O` yes/no form per declared relation (mirrors `relation_forms`; reflects to the same
  `<query>` yesno `query.ask` already runs). Binary relations use the plain `s v o` shape (like
  declared `relation_forms`), NOT the event reification (that's for ditransitives). Wired into
  `Session.submit`'s question path + exported.
- **Definiteness → uniqueness → merge (the perf+correctness fix; user-driven).** Relational facts put
  entities in object position, so same-named mentions multiply and the lazy per-query coref goes
  O(k²) + `same_as` saturation — measured 5–16 s/query, the full probe HUNG. The user surfaced the
  root cause by asking "how do we KNOW entities are unique?": ProofWriter entities ARE unique, but the
  pure-§3 model reads bare repeats as distinct witnesses. FIX (opt-in per domain, not universal): read
  DEFINITENESS from the article. `the X` = one individual — the missing definite/indefinite axis
  (`memory/decision_quantification_coreference`). Opt in with `the is a definite`
  (`forms.declared_definites`); the determiner-strip form marks `the X` entities `is_unique`, and
  `Session._merge_unique` COLLAPSES a unique name's mentions to ONE node (SCOPED merge — entity names
  only, not the blunt global `canonicalize`). Correct AND O(mentions): ~1000x (0.02 s for 3 questions
  vs 141 s). MEASURED that `is_unique`+force-coref is WORSE (same O(k²) walk); merge must run BEFORE
  `_derive` (unify a name's split facts, then compose cross-name `same_as`). Default (no opt-in)
  keeps the distinct-witness model — existing `is one thing`/`same as` tests unaffected.
- **Question-form simplification (user challenge).** The generated per-relation `relation_question_forms`
  was over-built: a question is gated by its `does` marker, so a SINGLE generic static rule
  `does S P O -> <query> yesno` (in `query.QUESTION_FORMS`, like the generic copula `is S P O`) binds
  the predicate freely. DELETED `relation_question_forms`; only the declarative side stays per-relation.
- **Bench.** `bench/proofwriter_nl.py` DECLARES `the is a definite` + each theory's verb catalog (base
  forms from the representations), caveman-normalizes inflection (`_base`/`_caveman`), and asks
  relational `does X V Y` questions. MEASURED (depth-1, 15 theories): sentences recognized 98→**173**/198,
  answered 81→**114**, accuracy 75→**79%**, QDep-1 52→**65%**; and the probe now completes in seconds.
  LIMITS: verb negation (`does not eat`), multi-word entities in a relational clause (`the bald eagle`
  mis-decomposes — the next ceiling), ellipsis, and the `is not` copula-stratification degradation.

### Universals→laws (first slice) — NL `if BODY then HEAD` parses to a rule (198 tests)
The highest-leverage NL grammar gap from `finding_raw_nl_coverage`: a natural-language universal
`if someone is rough then they are young` now parses to the executable rule `?x is young when ?x is
rough`, end-to-end through `Session` (assert → reason → explain). Memory
`decision_quantification_coreference` / `finding_raw_nl_coverage`; `tests/test_universals.py`.
- **The bound variable's NL surface is a quantifier+anaphor pair.** `someone`…`they` and
  `something`…`it` each denote ONE bound variable, not entities: a universal binds all witnesses BY
  NAME (decision_quantification_coreference), so the two words UNIFY to a single rule variable with
  NO coreference. `forms.rule_var_name` maps the person class → `?x`, the thing class → `?y`.
- **Reuse, don't reinvent.** `authoring.IF_THEN_FORMS` (two forms) reuse the shared body spine
  (`BODY_SPINE_FORMS`) + the copula sugar and fold the trailing head triple into the same
  `rl_subj/rl_pred/rl_obj` the prose `when` grammar uses. `expand_rules` then applies `rule_var_name`
  when reflecting the fragment — the name-op lives on the calculator side of the quote/eval wall, so
  NO `?x` node is ever minted in the graph (the "gap" that supposedly blocked this did not).
  A literal-subject rule (`if the lion is angry then the lion is loud`) reflects as a GROUND
  conditional — exactly right for ProofWriter's `if the lion … then the lion …` rules.
- **Wiring.** `are`→`is` copula morphology is a lexical step (`forms.normalize_lexical`); the `then`
  of a rule is kept distinct from the `X then Y` sequencing form by an `if_ctx` NAC set in a surface-
  normalization stratum (no race). In `Session`, a rule line's pronouns are NOT resolved to the
  discourse subject (they are variables) — detected content-blind by the `if`/`then`/`when` keywords.
- **Scope = COPULA laws** (`is [not] O`), single or non-elliptical conjunctive body. `load_universal_rules`
  is the batch entry. KNOWN LIMITS (all pre-existing gaps, now surfaced): n-ary VERB clauses
  mis-decompose as multi-word NPs (undeclared-verb gap → dropped); `is not` parses to a NAC but its
  runtime is limited by the coarse copula stratification (all `is X` share pred `is` → false cycle
  with `goal.satisfied` → graceful degradation; fix = object-aware copula stratification); elliptical
  conjunction (`is round and big`) not folded. The remaining QDep≥1 NL ceiling is now the VERB axis.

### De-pythonization — provenance as substrate, retraction & decide as rules (178 tests)
A keystone arc (docs/depythonization_design.md, memory `decision_depythonization`), driven by the
user challenging two seams: "why do tools trigger decisions?" and "why is provenance inert to the
matcher?". Both were right. This **supersedes** the "engine-driven tools" entry below — the decide
tools it added are now deleted.
- **Provenance matchable, per rule** (§2). `_is_inert` no longer hides provenance from ALL rules;
  a rule that NAMES a provenance predicate (`proves`/`uses`/`unless`) is provenance-aware and the
  matcher lifts the inert-bind refusal only for it (`rewriter._pats_touch_prov` → `_try_bind`).
  Ordinary rules are byte-identical (seed-from-ground already kept them off provenance). The
  "third category" (meta/TMS rules) is a LINTER LABEL, not an engine type; motivation =
  fact-layer confluence; meta-rules fire with `provenance=False` (regress guard).
  `tests/test_provenance_matchable.py`.
- **`rewire` primitive + interposition** (§4). A general control-layer `cut`/`link` raw-edge op
  (`Rule.rewire`, `apply_rule`) — the identity/provenance-preserving structural edit `drop`+re-add
  can't do. Retraction hides a fact by splicing an (inert) `<retracted>` node into its 2-hop path;
  resurrect is the inverse. Matcher untouched. `tests/test_rewire.py`.
- **Cascade as meta-rules** (`retraction.RETRACT_RULES`). Seed `<retract> targets ?rel` → CASCADE
  propagates along `proves`/`uses` → INTERPOSE hides each. FINDING: the EXACT "all justifications
  defeated" cascade is non-stratifiable (§11 forbids); the AGGRESSIVE form (retract if SOME j uses
  a retracted fact, unless axiom) is stratified and correct for single-support (multi-support =
  aggressive + re-derive, deferred). `tests/test_retract_rules.py`.
- **The decide completion/defeat stack is now rules.** Completion = a generated rule
  (`decide.completion_rule` via `authoring._completion_rules`), consumed positively; defeat =
  `DEFEAT_SEED` (`?c is ?p and ?c is_not ?p` → retract the negative) onto `RETRACT_RULES`.
  `decide.solve` = derive+complete (provenance on) then, iff defeated, the retraction pass (off).
  Deleted the whole tool/`<decide>`/`complete`/`recheck` machinery. FINDING: a completion NAC on
  `?c is P` false-cycles through the overloaded copula `is` (consumer produces `is thief`), so
  completion is AGGRESSIVE + MONOTONE (no NAC) and DEFEAT repairs — the mirror of the aggressive
  cascade. `tests/test_decide.py` rewritten; riddles unchanged. Full de-pythonization AUDIT of
  `harneskills/*.py` in the design doc: engine clean, no BLOCKS; remaining seams are `query.ask`,
  `session._assert` (parked), `coref_on_demand`→walker, `rule_graph` property-laws (quote/eval gap).

### Coref as rules — `Rule.meta` + the check-before-commit cursor (187 tests, DONE)
De-pythonization follow-up COMPLETE: `coref.coref_on_demand`'s Python generate-and-test loop (the
audit's other real seam — a tool handler that inspected `<contradiction>` and DECIDED which links
to keep) is migrated to rules; the old module, `cascade_retract`, and the `<quarantine>` cluster
are DELETED. Design + findings in `docs/coref_as_rules_design.md`.
- **`Rule.meta` — per-rule provenance** (`production_rule.Rule`, `rewriter.Rewriter.run`). A
  `meta=True` rule fires provenance-silent even in a prov-on run (the regress guard, previously
  enforced by a separate `run(prov=False)`), so reasoning (prov on, for the support chain) and
  TMS/meta rules can share ONE run. `RETRACT_RULES` marked `meta`. `tests/test_meta_provenance.py`.
- **The `<coref>` cursor** (`coref_walk.py`) walks a name's mention pairs ONE at a time, driven by
  rule firing + the engine's fixpoint-then-service cycle (a trivial `settle` barrier `<call>`) —
  **no Python driver loop** (the user's constraint: iteration must be emergent, like the walker's
  BFS). A thin materializer lays the mentions as a linear `<coref-pair>` chain (demand scope, by
  name — rules can't gather by name); `advance` moves the cursor (positive on `pnext`, ends
  naturally). `tests/test_coref_walk.py`.
- **FINDING: retraction cannot share a run with propagation.** Wiring a serialize+retract reject
  blew up — cascade hides a `same_as` fact, `force_all` re-runs the monotone propagation, it
  re-derives, they fight (nodes 74→1830 in four steps). This is why `cascade_retract`/`decide.solve`
  isolate retraction. So the plan pivoted.
- **CHECK-BEFORE-COMMIT (the pivot, user-chosen).** Coref becomes purely ADDITIVE: detect the
  disqualifying clash from the two endpoints' sort closures BEFORE linking (`?a is_a ?s1, ?b is_a
  ?s2, ?s1 disjoint_from ?s2 ⇒ not_same_as`), and COMMIT `same_as` only if none. No hypothesize,
  no cascade, no retraction, no propagation-fight — and it kills `cascade_retract` by removing
  coref's NEED to retract (goal met by elimination). Transitive-aware (each commit's propagation
  extends the endpoints' sorts before the next pair's barrier). A one-step `checked` delay orders
  clash-before-commit (a barrier-gated NAC = stratified negation, which §11 permits — the earlier
  "no NAC" was too strong). Greedy/order-dependent = the original `coref_on_demand`'s semantics.
- **`force` / resolver / Session / deletions** all landed: `FORCE_COMMIT` (link every pair so a
  `X is one thing` mistake surfaces a real `<contradiction>` under detection); a `resolve` tool
  wrapping the oracle for consistent-but-ambiguous pairs; `resolve_coref`/`coref_request_handler`
  wired into `Session`; `coref.py` + `cascade_retract` + the `<quarantine>` mechanism DELETED
  (`retract`/`RETRACT_RULES` is now the sole TMS path). Instance-vs-name fix: `clash_rules` are
  generated per `disjoint_from` declaration with LITERAL cat names (a generic instance-bound rule
  missed across distinct same-name `teacher` nodes in `Session`).
- Deferred as SEPARATE arcs (not loose ends): the general propagate-then-retract path
  (generalization hook); retiring `canonicalize` from the batch load path (gated on universals→laws).

### Follow-up: `unless` OUT-LIST machinery deleted (178 tests)
De-pythonization follow-up (handoff step 1). The JTMS `unless` OUT-LIST edge is fully retired now
that defeat is coexistence-driven (`DEFEAT_SEED` matches a live positive next to a completed
negative — no bookkeeping edge to watch). Deleted `provenance.add_unless` / `unless_watch` /
`completion_js` and the `UNLESS` predicate constant, and dropped `"unless"` from
`provenance.PROVENANCE_PREDS` + `world_model._INERT_NAMES` (and the matching exports/comments). No
code wrote or read an `unless` edge anymore. (The CNL `applies unless X present` NAC keyword is
unrelated — it never mints an `unless` relation.) Byte-identical behaviour; pure dead-code removal.

### The decide loop is engine-driven — `complete`/`recheck` as tools + triggers (167 tests)
Handoff step 1 #2, DONE. The last hand-sequenced driver in the decide stack is gone: `decide.solve`
no longer loops `run_rules` + `complete` + `recheck` in Python. The two decisions are now
materialized `<call>`s (dispatch.py) the engine services at its rule-fixpoint — which is EXACTLY
the per-tuple producer-fixpoint completion needs, since `rewriter.run` services a `<call>` only
once the rules have quiesced (producers done → the completion is sound by construction).
- **Two tools** (`decide.complete_tool`/`recheck_tool`, `DECIDE_TOOLS`) wrap the unchanged
  primitives — so `test_decide.py` still drives `complete`/`recheck` step by step (the per-step
  contract is untouched); only the loop that invoked them moved into the engine.
- **Two content-blind triggers.** `COMPLETE_TRIGGER`: a standing `<decide>` demand → `<call>
  complete` (fires ONCE per demand — the rewriter's `fired` set dedups the binding, so no busy
  loop; emitted early, serviced late at quiescence). `RECHECK_TRIGGER`: the defeater made
  MATCHABLE — the completion's `unless` OUT-LIST is inert, but a live positive `?c is ?P`
  COEXISTING with a completed `?c is_not ?P` is precisely "a defeater now holds for a completed
  tuple", so `?c is ?P and ?c is_not ?P → <call> recheck`. This is the demand-scoped re-decision
  trigger the handoff flagged: it fires ONLY when a positive appears for an already-completed tuple
  (the watched extension changed), and after `recheck` retracts the negative the `is_not` edge is
  gone → it cannot re-fire. (The two clauses bind the SAME property node because a plain-literal
  concept resolves to the one shared node, `rewriter.apply_rule`.)
- **`solve` is now three lines** — register `DECIDE_TOOLS` alongside any caller tools, append the
  two triggers, one `run_rules`. Still a no-op beyond plain `run_rules` when nothing is decided (no
  `<decide>` → no complete trigger; no completed negative → no recheck trigger).
- Two new `test_decide.py` cases drive the whole loop through `solve` (completion with no manual
  sequencing; a later positive defeating a completion via the engine trigger). Riddles unchanged.
  See `memory/decision_forcing_a_decision`.

## 2026-07-01

### The grammar authors a decide-consumer — closed-world `is not` onto `decide` (165 tests)
Handoff step 1, DONE (riddle-confirmed): a riddle now authors ENTIRELY in CNL — the two hand-built
consumer rules (`_THIEF`/`_CULPRIT`), the explicit `suspects` list, and the hand-sequenced
`complete`/`recheck` loop are all gone. This is design **C** (the substrate route, not a Python
post-transform on compiled rules): the reflection reads in-graph CWA data and the rule is BORN as a
decided negation.
- **CWA in CNL** — `cleared is closed world` is a fact form (`form.fact.closed_world`) that emits
  the marker `cleared closes <closed_world>` that `decide.is_closed_world` already reads. The
  two-word object `closed world` self-excludes the copula (same additive idiom as `X is one thing`),
  so it is purely additive + linter-clean; no new keyword machinery.
- **CWA-aware reflection** (`authoring.expand_rules`) — a rule's `is not P` clause whose `P` carries
  the closed-world marker is UPGRADED: the NAC becomes a positive `?x is_not P` condition, and a
  companion `<decide>` demand rule (`decide.demand_rule`) is emitted that seeds the decision from the
  consumer's POSITIVE RESIDUAL (`?x is a suspect`) — the magic-set/`demand.py` pattern, so the tuples
  to decide are DISCOVERED, not hand-listed. The demand binds the concept node via its own marker
  (CWA-gated) and self-dedups (one live demand per tuple, `stratify` discards the self-dep).
- **Backward-compatible by construction** — a factless rule graph (`load_rules`,
  `load_machine_rules`) carries no CWA marker, so `is not` stays a NAC and the ~pinned grammar tests
  are untouched. Only the one-substrate `load_corpus` path (facts + rules together) upgrades. Open-
  world negation (icecream's `is not urgent`) is unchanged: no marker, no upgrade.
- **The reasoning driver** — `decide.solve(graph, rules)` loops `run_rules` + `complete` + `recheck`
  to a combined fixpoint; a no-op beyond one `run_rules` pass when nothing is decided, so an ordinary
  bank behaves exactly as before. (Expressing this loop itself as tokens serviced in `run` — so a
  caller need not sequence it — is the remaining refinement; see handoff.)
- Riddle probe (`tests/test_riddles.py`, 6 tests) rewritten: one CNL corpus per riddle, solved by
  `decide.solve`, plus `test_riddles_author_entirely_in_cnl` asserting the consumer has no NAC, a
  positive `is_not` lhs, and a generated `decide.demand.*` rule. See
  `memory/decision_forcing_a_decision` and `memory/finding_riddles_probe`.

### Riddles — an integration probe over reasoning + Q&A + explanation (164 tests)
First riddles (`tests/test_riddles.py`), the workload that pulls the whole stack through one
problem and pressure-tests the fresh negation work. A riddle is authored as a domain and SOLVED
by elimination: the answer is the entity for which a closed-world property cannot be derived.
- **"the thief"** — suspects ada/bo/cy; `in library -> innocent -> cleared` (multi-step deduction)
  clears bo, an alibi clears ada, so `cy is_not cleared` is COMPLETED (`decide.complete`); the
  consumer `?x is_a suspect and ?x is_not cleared => ?x is thief` fires for cy. Answered by the
  real `ask` (`who is thief -> cy`) and explained by the real `explain` (the trace bottoms out at
  `cy is_not cleared <- complete` — the elimination step, rendered from in-graph provenance).
- **"the broken vase"** — a second, independent riddle (yes/no + why-not, different predicate),
  confirming the completion path is not a one-off.
- **First composition of** multi-step deduction → closed-world completion → wh/yes-no answer →
  why-trace, all through the real surface (only the two consumer rules are hand-built).
- **What they surfaced (the "what to build next" signal):** (1) the CNL grammar cannot yet author
  a decide-consumer — an authored `is not` still folds to a NAC + stratify, so the two consumer
  rules are hand-built; **wiring the grammar's closed-world `is not` onto `decide` is the clear
  #1 next item.** (2) No constructive disjunction / "exactly one" — a puzzle whose answer must be
  derived POSITIVELY by ruling out alternatives (not the "one we can't clear" framing) needs the
  deferred indefinite-existentials/uniqueness axis. Files: `tests/test_riddles.py` (new, 5 tests).

### Forcing a decision — negation decided-on-demand, per tuple (159 tests)
Built the engine direction from `memory/decision_forcing_a_decision` (spike-validated 2026-07-01):
a closed-world negative is no longer read as a NAC over the ABSENCE of a fact, but DECIDED per
demanded tuple and materialized as an explicit positive the consumer matches — **the NAC dissolves.**
- **The one new primitive: a JTMS OUT-LIST `unless` edge** (`provenance.add_unless` / `UNLESS`,
  inert in `world_model._is_inert` + `PROVENANCE_PREDS`). A completion holds by the ABSENCE of the
  positive, which a `uses`-only (in-list) provenance cannot express; `J --unless--> watched-subject`
  records the atom whose derivation defeats it. Inert, so it never surfaces as a domain fact nor
  collides with the relation instances named for the decided property (the spike's two bugs). The
  advance over the spike: the `unless` edges now live IN THE GRAPH, so re-decision reads completions
  off the graph — no Python registry stand-in.
- **`decide.py`** — generic calculator drivers gated by in-graph markers (same category as
  `retraction.cascade_retract` / `coref_on_demand`, no domain predicate hardcoded):
  `declare_closed_world` / `is_closed_world` (CWA is per-predicate DATA), `seed_decide` (a `<decide>`
  demand), `complete` (at a producer fixpoint, license `c is_not P` + the completion `<j:complete>`
  for a demanded, closed-world, unproven tuple), `recheck` (a defeater now holds → `cascade_retract`
  the negative, which withdraws everything it fed FOR FREE via the consumer firing's `uses` edge —
  the TMS half needed no new code, as the spike found).
- **Why completion, not just demand, is load-bearing:** forcing the positive is completeness (monotone,
  never wrong); forcing the negative is SOUNDNESS — so completion is licensed only for a closed-world
  predicate at a true per-tuple fixpoint. Open-world stays UNKNOWN (`test_open_world_..._never_completed`).
  Decided-negatives are defeasible CONTROL and ephemeral: resurrection is automatic (the standing
  `<decide>` demand lets `complete` re-materialize if the positive is later withdrawn).
- Scope: unary copula property `P(c) == c is P` (positive `is`, negative `is_not`) — the validated
  shape. Generalizing to arbitrary `R(c, o)` and expressing the drivers as rules/tokens (finding #4)
  are the noted next refinements. The static `stratify`/NAC path is UNCHANGED (this is an alternative,
  not yet a replacement). Files: `world_model.py`, `provenance.py`, `decide.py` (new), `__init__.py`,
  `tests/test_decide.py` (new, 8 tests).

### Tier 3 REDONE as forms — surface grammar is rules, not imperative Python (150 tests)
On review (user: "why Python instead of CNL rules?") the first-cut `chunk_phrases` tool was
retired: it baked grammar/recognition decisions into imperative Python — the seam the vision
rejects. Rebuilt as NORMALIZATION FORMS (`forms.surface_forms`, run in ordered strata by
`normalize_surface`). The one concession: these forms may `drop` surface `next`/`first` edges —
the token chain is ephemeral scaffolding (control), so rewriting it is control-deletes-control
(§5), not fact deletion.
- **Determiners** → a bridge form drops the determiner and re-links the chain (`the`/demonstratives
  anywhere; articles `a`/`an` only when LEADING). NAC `?x kw` keeps a determiner inside a fixed
  keyword phrase (`is the same as`).
- **Multi-word entities DECOMPOSE, not merge** (user's call, and it removes the one "irreducible"
  name-join tool): a modifier before the NP HEAD becomes a gradable ATTRIBUTE — `the bald eagle`
  → head `eagle` + `eagle is bald`; `the big bald eagle` → `eagle is big`, `eagle is bald`.
  Structure is exposed to reasoning, not hidden in an opaque string. Gated to genuine
  determiner/quantifier-introduced NPs via a `det_np` tag (seeded after a determiner/article/`every`,
  propagated across the content run), so controlled-CNL still rejects gibberish (`glorp the flarn
  wibbit`) and an undeclared verb (`alice sends parcel` stays for the n-ary form to reject, not
  turned into attributes). The head is the token before a keyword (`np_head_kw`) or the chain end
  (`np_head_end`); a copula guard stops the end-case splitting a bare predicate (`is alice happy`).
  Decomposition is normalization, so recognition is measured AFTER it (a bare NP/gibberish is not
  "recognized" on an attribute alone; a real clause must fire).
- **Pronouns** (`it`/`they`/…) resolve to the discourse subject (`Session._last_subject`, a §14
  content-blind recency policy) by `expand_pronouns_text` substitution before tokenizing — anaphora
  is name-level coreference (the pronoun IS that entity, ONE node — no same-as twin), the same
  name-op category as `canonicalize`, kept minimal and OUTSIDE the grammar rules.
Both assert and question paths run the same strata (`query` gained `strata=`). `stratify` insight
applies by hand here (tag → seed → strip → decompose), which motivated the negation-protocol
discussion → memory `decision_forcing_a_decision`. **Known limit (unchanged):** a yes/no STATE
question with a multi-word subject AND a bare predicate (`is the bald eagle happy`) can't split
them. **Deferred:** indefinite existentials (`someone`/`something`). Supersedes the first-cut
`chunk_phrases` (atomic-name) entries. Files: `forms.py`, `query.py`, `session.py`, `__init__.py`,
tests.

### Grammar unification — prose + machine rules share ONE condition grammar (138 tests)
Retired the prose↔machine condition-grammar seam. Both surfaces now fold their rule BODY
through one shared spine (`authoring.BODY_SPINE_FORMS`): a generic positive clause `S P O`
(any predicate, no fixed menu), a `not S P O` NAC, and an `and`-domino. They differ only in
the HEAD (prose = single triple with stable `rule.S.P.O` keys + frames; machine = multi-clause
+ `drop`). Prose copula sugar (`is a` / `is not` / `is <adverb>` / `not in`) sits on top and the
generic clause NACs `is_kw` to defer to it; the NAC is inert unless prose `is_kw` tags exist, so
planning/walker/procedure banks are unaffected. `_dropped_conditions` re-based on `body_subj`
(now reports only malformed clauses, never silently drops). Removed the now-redundant
`relation_cond_forms` / `load_rules(relations=)`. Supersedes the part-1 declared-relation work
below. **Residual seam:** full HEAD unification (multi-head/`drop` in prose) deferred — higher
churn (~4 pinned key tests). Files: `authoring.py`, `machine_rules.py`, `session.py`, `__init__.py`.

### 1a proper-fix part 1 — declared relations in prose rule bodies (138 tests, +2)
Prose rule grammar honours declared relations in bodies via `relation_cond_forms` (later
superseded by the shared spine above). `?x visits dog` folds once `visits is a relation` is
declared; undeclared still raises. (Superseded same day by grammar unification.)

### Remediation Tiers 1 + 2 — silent-failure kills (136 tests, +2)
- **1a immediate fix:** prose `load_rules` used to silently DROP un-menued body clauses (rule
  then fired unconditionally). Now DETECTS via `_dropped_conditions` and RAISES, naming the clause.
- **1b:** documented tokenizer case-folding at `forms.tokenize` (CNL is case-insensitive; code
  building nodes directly must lower-case). No code change.
- **2a:** `run_rules` now degrades to the monotone (no-NAC) subset on an un-stratifiable theory
  and warns which NAF rules it dropped (was: raise, whole theory unreasoned). `strict=True` restores
  the hard failure; `stratify` itself still raises.
- **2b:** documented the deliberately stratified-only negation boundary in `vision.md` §11.
Files: `authoring.py`, `forms.py`, `vision.md`, tests.

### Remediation plan drafted — from the scale-beyond-toy probes
Prioritized punch-list: Tier 1 silent failures (done above), Tier 2 reasoning fragment (done),
Tier 3 surface-NL grammar (multi-word entities, determiners, pronouns/coreference), Tier 4
dense/hub-relation walk performance (bidirectional or df-gated). Tier 3 is the substantive
remaining build; Tier 4a is the one hard research item.

## 2026-06-30

### Coverage probe: ProofWriter — multi-step reasoning is EXACT (134 tests, bench-only)
Held-out ProofWriter theories loaded into the substrate (facts + `load_machine_rules`, CWA):
99.2% over 11,304 questions; **monotone multi-step deduction = 100.000% exact**. Whole residual
is NAF conservatism (stratified negation refuses negation cycles by design). Surfaced 4 silent
grammar gaps (prose multi-cond drop, multi-word entities, `~` NAF polarity, machine-rule literal
lowercasing). `bench/proofwriter_coverage.py`. Canonical: memory `finding_coverage_proofwriter`.

### Scale probe: WordNet — on-demand is flat in KB size after a matcher fix (134 tests)
WordNet noun hypernymy (166k nodes) answered by the demand-spawned `is_a` walker. Found the
matcher was O(graph)/step on the `is_a` stopword (df≈84k); fixed with O(1) `Graph.name_count`,
seed-from-the-rarest-anchor, and retiring `scope` as a real set. Result: flat 5.7→10ms across an
8k→166k node sweep (~120×). Fuel re-represented as a single counter node + `dec` tool (was N unary
edges = quadratic). Added stop-on-arrival NAC → is_a work now ∝ answer depth. Messy-graph probe:
clutter isolation passes at 188k; dense/cyclic relations flood the hub (the Tier-4 open item).
`bench/wordnet_scaling.py`, `bench/wordnet_messy.py`. Canonical: memory `finding_matcher_is_matching_bound`.

### Procedure gap-filling — procedures ⇄ planner bridge (134 tests)
A procedure step's unmet precondition becomes a subgoal the existing goal-directed planner
solves, so a procedure with a missing step auto-completes (recursive, reuses cost ranking). One
bridge rule in `corpus/procedure.cnl`; `solve(extra_rules=)`, `run_procedure(gap_fill=True)`.

### Procedures + a latent NAC-semantics engine bug fixed (131 tests)
Procedures (`to brew get_water then add_beans then heat`, `procedure.py`) desugar to planner
operators; the `to NAME` header is a CNL-emergent form, the body a `then`-chain. Building the
`waits_for` before-gate exposed that `rewriter.nac_blocks` treated ALL `not` clauses as ONE
conjunctive NAC (so `unmet` had been cosmetic since the planner was written). Fixed via
`_nac_groups`: independent negation groups by shared free var (`not A and not B` = ¬A ∧ ¬B).
Canonical: memory `decision_nac_grouping`.

### ADVERB_THRESHOLDS moved to the KB — degree scale is now data (126 tests)
Deleted the last hardcoded lexical config. The adverb→degree scale lives in the KB as CNL facts
(`very is 0.8`); `graded_rules` / `degree_grammar_forms` / α-cut all generate from `_degrees`
(defaults overlaid with KB declarations). A user can declare `extremely is 0.95` with no code change.

### Prepositions declarable + engine-stays-stupid audit (124 tests)
Removed the frozen `NARY_PREPOSITIONS` list — `P is a preposition` drives n-ary roles as data.
Audit confirmed the engine never categorizes: `match` compares names as opaque strings, α-cut is
read off the rule; the only name-based engine special-case is `_is_inert` (structural provenance).

### N-ary relations + questions — event reification (124 tests)
`alice gives book to bob` reifies to a fresh event node with positional (subj/obj) + prepositional
role edges; only a DECLARED verb (`gives is a verb`) parses. N-ary questions (`who gives book to
bob`, `alice gives what to bob`) query one event node. `forms.nary_forms` / `nary_question_forms`.
First-slice limits: surface verb must match the declaration, single-word entities, one preposition.

### act/observe folded onto `<call>` — uniform tool dispatch complete (119 tests)
The last bespoke per-cycle tool step in planning is gone: acting is now an engine-serviced
materialized `<call>` like price and rank, folded into the planning fixpoint. Every §8 boundary
(price/rank/act/coref) is now uniform token-gated dispatch. Canonical: memory
`decision_materialized_tool_calls`.

### Explicit cross-name coreference — `X is the same as Y` (119 tests)
Declares two different names denote one individual; desugars to single-identity + an asserted
cross-link, reusing the single-identity machinery. Composes facts across the class; catches
cross-name contradictions.

### Explicit single-identity grammar — `X is one thing` (116 tests)
Declares single identity, overriding the distinct-witness default so a genuine one-entity mistake
(`ice is a solid` + `ice is a liquid` over disjoint sorts) is caught. `coref_on_demand(force=True)`.

### Connection model / matcher performance — measure-first (88 tests, suite ~1.2s)
Profiling overturned the assumption that `run()` is firing-bound: it is **matching-bound**
(`_triples`/`Graph.out` dominate). Landed: fixed a latent `Graph.copy()` index bug; live neighbour
views (no per-call set copy); bound-NAC → existence check; **seed-from-ground** matching (seed each
pattern from its most-selective ground anchor via the lexical index). Chain n=40 10,730→359ms (~30×).
Honest findings: rule-level anchor-delta is ~inert atop the index; semi-naive helps only deep-closure;
per-line Session reasoning stays whole-graph (name-matching across disconnected mentions is non-local).
See `docs/walkers_and_locality.md`.

### `within`/`radius` retired as the matching scope
Profiling showed hop-radius is mismatched to a name-keyed substrate (a single-pattern law finds a
disconnected mention through the index, not by hops) and a too-small radius silently truncated valid
long joins. Matching is now **unbounded and correct**; seed-from-ground keeps it cheap. `radius`
survives only as a vestigial ignored parameter. Canonical: memory `decision_locality_rete`.

### Walkers + locality — the connection model (114 tests)
Seed-from-ground matching; a demand-spawned **walker** gadget (origin + reached + target + fuel,
provenance-bearing shortcuts) in `walker.py`; token-typed walkers give fully concurrent traversal
on different relations with zero cross-wire. Walker rules and the entire planner now live in CNL
(`corpus/walker.cnl`, `planning*.cnl`); `planning.py`/`walker.py` have zero `Rule(` literals.
Canonical: memory `decision_walkers_locality`, `decision_machine_rule_cnl`.

### Materialized tool calls — `dispatch.py` (114 tests)
Tool calls are `<call>` nodes a rule emits; the engine services them at each rule-fixpoint via a
`tools=` registry passed to `run`/`run_rules`, folds output back in. Generalizes `external.py`'s
old request/dispatcher board (migrated). Machine rule CNL (`machine_rules.py`, `corpus/*.cnl`) lets
control/machinery rules be authored in CNL. Planning's `service_calls` folded onto `run(tools=)` —
the last holdout, ordered by DATA (`cost_settled` gate) not a hand-written cycle.

### Demand-driven selective coreference wired into Session + ask-user tool (83 tests)
The KB is now LAZY: asserting runs reasoning only; a question seeds a `<demand>` → rule →
`<coref-request>` → dispatcher → `coref_on_demand`. Coreference = pure §3 disambiguation: a
same-name clash means distinct entities, so bare repeats are distinct witnesses (three Session
detection tests flipped to assert consistency). `interaction.py` adds the user as an external
source (§8) — only consistent-but-ambiguous links are referred to an `Oracle`. Canonical: memory
`decision_quantification_coreference`.

## 2026-06-29

### Selective coreference first slice — on-demand + reversible TMS (77 tests)
New modules `provenance.py` / `retraction.py` / `demand.py` / `coref.py`. In-graph justifications
(`<j:KEY> --proves/uses-->`; `explain` traverses them, no journal); reversible quarantine + cascade
retraction; on-demand transitivity; coreference-by-reasoning (two distinct Pauls stay separate
because merging breaks consistency). Design: `docs/coreference_design.md`.

### Quantification/coreference rework + one generic driver (81 tests)
Universals are LAWS not facts (`every X is a Y` → a reflected rule matching witnesses by name).
`canonicalize` retired from Session in favour of context-scoped additive `same_as`. `driver.py` =
the one dumb loop (run each phase's rules to fixpoint, service tool requests via a registry).
Canonical: memory `decision_quantification_coreference`.

### Universal consistency / rule-linter (56→64 tests)
`lint.py`: a §8 tool over a rule bank emitting `Smell` findings (ungated-delete, unbound-drop,
no-op, negation-cycle, opt-in dead-predicate). Universal constraint schemas (irreflexive,
asymmetric, acyclic, disjoint_from, inverse_of) extend the relation-property meta-feature and
detect inconsistency by ADDING a `<contradiction>` marker (paraconsistent §5, never reject).
Inequality-blocked constraints (functional/injective/cardinality) await a distinctness primitive.
Design: `docs/consistency_design.md`.

### Planning loop — goal → plan → act → replan, all as rules (41→59 tests)
`planning.py`: phases A (relevance) → B (connection) → C (ranked commitment) → D (acting) →
E (divergence→replan), entirely as rules, no planner. Ranked multi-option commitment by fact-layer
`cost` (`rank_by_cost` → `cheaper_than` → `dominated`/`best`/`choose`). External on-demand cost
lookup (`external.py`: request → dispatcher → tool → result; freshness via §5 supersedes, no
deletion). Real §8 act tools (observed effect may ≠ declared → real divergence). Design:
`docs/planning_design.md`. Guardrail: commitment may be control, but the criterion must be
fact-layer (graded cost).

### CNL-authored domains, Q&A, one-graph corpus loading (68→71 tests)
`authoring.py`: a whole domain (facts + rules + lexicon + loose form) authored in CNL; the
embedding-write is a rule effect (`rule.propagate`). `query.py`: ask the KB in CNL, get CNL
answers (recognition emergent, execution a §8 tool). `load_corpus`: a mixed corpus recognized
in ONE graph with no Python classifier; b2 fact-space pollution resolved with no engine scope
(bound-literal rule fragments + context-as-a-node bound by rules). Defeasible context tier (a):
a monotone defeasible default (explicit placement defeats the general rule via NAC, no retraction).
Session + REPL (`session.py`, `repl.py`). Housekeeping: ~74 old-paradigm files deleted; tests run
plainly (`pytest tests/ -q`).

## 2026-06-28

### Rebuild started — the one-substrate core
The old paradigm (typed predicates, smart planner, PCFG/EM, mappers/dispatcher/grounder, CNL Forms
compiler) was deleted; a clean core was built on `docs/vision.md`. Rules-as-graph-nodes (Prong B/b1):
`rule_graph.py` stores a rule as a literal-subgraph fragment; `write_rule`/`rules_in_graph` round-trip.
Relation-property meta-feature (`is_a is transitive` → a rule-node, two-phase). b2 meta-circular
execution parked. Canonical: memory `decision_one_substrate_vision`.
