# System Critique — an honest external analysis

> **Status: SNAPSHOT (2026-07-07).** A critical assessment of the whole system as it stands
> mid-rehost (branch `main`, ~922 commits, 448 tests). Grounded in a full read of the vision
> docs, the migration plan, the substrate core, plus three focused audits (design docs, ISA
> engine, legacy pipeline + benchmarks). Companion to `docs/nonconformance_audit.md` (which is
> itself stale — see §2.6) and `docs/related_work.md`.

## 1. What's genuinely interesting and promising

### 1.1 The empirical discipline is the system's best asset — better than the ideas themselves

Rare in solo research systems. 448 tests, 17 of 44 test files on the new ISA path, and the
flagship tests are genuinely differential rather than decorative:

- `tests/test_isa_goal_semi_naive.py` sweeps 25 random graphs × all binding patterns against an
  independent forward closure (>1000 assertions), plus a structural `full_joins <= tables`
  mechanism check.
- `tests/test_isa_runbank.py` pins byte-for-byte fact + rule parity against `rewriter.run`,
  per-sentence and whole-batch.
- The existential-NAC tests diff against the *actual* forward planner loop where `drop` is
  load-bearing.
- ProofWriter coverage measured at 99.2% over 11,304 held-out questions.

Most KR projects assert; this one measures.

### 1.2 The forms-as-rules parser is the cleanest realization of the thesis

`forms.py` + `authoring.py` (2,090 lines combined) contain **zero regex**. Text becomes token
nodes chained by `next`/`first` edges; the acceptance grammar is graph rewrite rules generated
from word-list *data*. The Python is a form-generator, not a parser. "Parsing relocated into the
substrate" — which reads as hand-waving in `vision.md` §3 — is actually built here, and it's
elegant.

### 1.3 The ISA move is a real design-tractability win, whatever one thinks of the ideology

Compiling rules to a small opcode set turns "the engine never deletes a fact" (§5) from a
code-review norm into a structural property (`DROP_CTRL` refuses fact edges in `machine.py`).
More valuable are the *findings* this produced: the planner's 15-rule teardown and the
retraction/TMS deletion path both turned out to be **subsumed** by demand-driven
negation-as-completion — the deletion machinery is never reached. A non-obvious result about the
design space, discovered by building the reference machine.

### 1.4 The contrarian agentic bet is the most distinctive strategic idea

The industry default is "LLM owns the loop, tools at the boundary"; this system inverts it — the
substrate owns trigger→plan→act→observe, the SLM is one scoped `<call>` (intent→CNL). Combined
with the coverage/composition audit (novel bugs found via *composition* of general rules, 0 false
positives — a direct empirical answer to the "isn't this just Cyc?" objection) and the
card-trader demo (defeasible deontics, graded risk, override reasoning, all in banks), there is a
plausible niche in **auditable business-policy agents** where "why did you do that" must have a
derivation.

## 2. What doesn't work, or isn't what it claims to be

### 2.1 "Label-less" is more brand than mechanism

The substrate docstring forbids value-as-identity indexing, then `isa/attrgraph.py:146` builds
`_by_name` as an "accelerator." The GoalSolver's identity system is name-centric — tokens are
`name\x00rep` strings (`isa/goal.py:582-601`), everything routes through `nodes_named`,
inertness is literal name-string matching (`isa/attrgraph.py:60-65`), `COPULA="is"` and
`NEG_SUFFIX="_not"` are hardcoded (`isa/goal.py:76-78`). The candidate-set-not-merge argument
preserves the *formal* guarantee (identity stays opaque, no merge-by-value), but operationally
the abolished label came back wearing a lanyard that says "convention."

### 2.2 The engine violates its own no-hardcoded-policy principle

`isa/goal.py:103-109` decides whether to follow coreference by **sniffing rule-key strings**
(`r.key == "same_as.symmetric"`, `startswith("same_as.subj.")`), then flips a Python flag
(`self._follow_coref`). The comment claims this is data-driven; it is the engine pattern-matching
rule *names* to select semantics. Same story for walker/fuel special-casing in the solver
(`isa/goal.py:442`, `:520`) and the hardcoded predicate list in `isa/solve.py`
(`add/cost/cheaper_than/chosen/before/for/ready/<now>/true/del`). Exactly the leak the banks
discipline was supposed to prevent, relocated one level down. Also: strategy selection by
syntactic shape-matching (`_is_transitive_closure_rule`, `_linear_recursion_base` requiring
*exactly* two rules) creates silent cliffs — adding a third rule to a derived relation silently
disables the walker.

### 2.3 Concrete correctness risks in the fragile spots — and the tests don't cover them

- The `same_as` union-find is built once at solver construction (`isa/goal.py:360-365`);
  `same_as` edges *derived during solving* are never unioned in and `_tok_cache` is never
  invalidated — derived coreference is silently missed.
- Stratification is never statically checked; only lazy same-goal cycle detection
  (`_completing`, `isa/goal.py:850`). A negative cycle routed through a *different* goal's
  positive intermediary may evade it.
- `_group_satisfiable` (`isa/goal.py:807`) builds an **uncached** fresh solver per environment —
  O(envs × graph) — and reads the shared mutable graph mid-round (the classic non-stratified
  hazard, held at bay only by discipline).
- `_ensure_node` registers completion objects in `_name_ids`/`_tok_cache` but not
  `_token_class` (`isa/goal.py:985`) — a later duplicated-name node isn't found.

The differential tests assert **parity with sibling implementations** (rewriter,
`planning.plan`), not ground truth — a shared bug passes both. No adversarial tests target
visitation-order independence, derived-`same_as`, or cross-goal negative cycles — precisely the
weak points above.

### 2.4 The novelty claim is thin, and "no seams" is contradicted by the architecture

`related_work.md` is admirably candid that the vision is "mostly a recombination" (magic sets,
tabling, production systems, AtomSpace, Conceptual Graphs, CHR) — but it conspicuously omits
**XSB/SLG tabling** despite `GoalSolver` *being* a tabled top-down solver, and gives ASP and Cyc
one-line treatment. The one claimed novelty — no-seam CNL-as-substrate — coexists with real
seams: the tokenizer, tools, clingo, Joern, the SLM, the comparator, and the metareasoning layer
(§14: "outside the graph") all live outside the substrate. The honest statement is "few,
well-chosen seams" — good engineering, not a new idea. And everything classical KR found hard —
aggregation, disjunction, arithmetic, optimization — is punted to `<call>`/clingo, so "one
substrate" is really one substrate plus an escape hatch for the hard parts.

### 2.5 The evidence base is narrower than the headline numbers

- The ProofWriter NL probe pre-folds English inflection and declares verb catalogs up front —
  the parser never sees messy NL.
- The CPG "100% recall / 0 FP" is on 8 bugs the author encoded; on real Django precision was
  thin (0 true positives in mature code).
- The 95–98% SLM number is closed-target translation.

None of this is dishonest — the caveats are all *in the docs* — but the distance from curated
corpus to real input is the unproven part, and it is the part the agentic bet depends on.

### 2.6 Migration debt is real and the strategy is risky

Two engines (`rewriter.py` VF2 forward vs `isa/` machine+GoalSolver), two coref implementations
(`coref_walk.py` still imported by `session.py:45` vs the union-find path), two walkers
(`walker.py` vs `isa/walker.py`), dual rule-head encodings (`authoring.py:643-687`), and a stale
`nonconformance_audit.md` referencing files that no longer exist. Duplicated logic that will
drift: two independent NAC-group partitioners (`lowering._nac_groups` vs
`goal._nac_groups_free`), three ways to write a reified relation.

The ratified strategy is big-batch and **red-tolerant** on a solo multi-session arc, while the
design itself churned same-day during migration (OWA→CWA reversed; the retraction plan
retired-then-kept; ~15 self-reversing handoff entries on 2026-07-07 alone). Settling the
semantics *while* rehosting the whole system on it is the highest-risk thing in the repo.

Performance ceilings worth naming: `_solve1`'s semi-naiveté is partial (the delta removes the
re-join but not the per-round fact re-scan or goal re-visitation); nested-solver construction is
O(nodes+edges) each (`__init__` rebuilds head index, union-find, token classes); `derived_triples`
memoizes on `ag.version` but every materialization invalidates it and the planner calls it
repeatedly. Scale evidence stops at n=80 sentences / 31 modules.

## 3. Verdict

A serious, unusually well-instrumented research system whose **methodology is stronger than its
ideology**. The measurable outputs — the differential-test harness, the composition audit, the
NAC-as-completion subsumption findings, the regex-free rule-based parser — are genuinely good
work. The conceptual framing (label-less purity, no-seam substrate) is largely rhetorical: the
engine is name-centric in practice, the seams exist, and the individual mechanisms are
1980s–2000s KR recombined — which the project's own docs admit.

As a research vehicle it is earning its keep: it keeps producing non-obvious findings. As a
useful system the case is unproven on the two axes that matter — messy real-world input (the
SLM/NL boundary) and differentiation against the cheap alternative of "LLM + off-the-shelf
ASP/Datalog." The card-trader-style auditable-policy-agent niche is the most credible path to
usefulness; demonstrating *that* end-to-end on un-curated input matters more than further
substrate purification.

**Nearer-term recommendations:**

1. Fix the derived-`same_as` staleness and the rule-key sniffing (§2.2–2.3) before the rehost
   bakes them in.
2. Add adversarial tests for the untested fragile areas: visitation-order independence,
   derived-`same_as` mid-solve, cross-goal negative cycles.
3. Finish the migration before touching the semantics again; refresh or delete the stale
   `nonconformance_audit.md`.
4. Add XSB/SLG and NARS to `related_work.md` — the comparison the current draft avoids is the
   one a skeptical reader will make first.
