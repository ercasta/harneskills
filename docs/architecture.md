# Harneskills — Architecture (the system as built)

> **Status: reference for the CURRENT implementation (2026-07-01).** This describes what
> exists and how it fits together. Its companion `docs/vision.md` is the canonical *design
> philosophy* (the "why"); where this document and the vision differ, the vision states the
> intent and this document states the current reality. History is in `docs/CHANGELOG.md`;
> the live plan is `docs/implementation_plan.md` (index: `docs/reference.md`). NOTE: parts of
> this document predate the AttrGraph re-host (the engine core it describes, `rewriter.py`, is
> being deleted per the plan's Phase 0); it is rewritten at plan Phase 6.2.

The whole system is one idea: **a single graph substrate where everything — facts, rules,
goals, control flow, and the source CNL — is a node.** Computation is graph rewriting. There
are no seams: nothing leaves the substrate to be processed by foreign machinery. See
`vision.md` for the full argument; this document is the concrete map.

Current state: **165 tests green** (`pytest tests/ -q`, ~2.7s). Nothing is committed
automatically (the user commits manually).

---

## The model in one screen

- **Node** = uuid identity + a non-unique `name` label + sparse `embedding` + `confidence`.
  **No values** — a datum like `0.2` is a node named `"0.2"`; only a tool parses the name.
- **Edge** = a bare directed `(from, to)` pair. **No types.** A relation `s R o` is an
  intermediate node: `s → [R] → o` (three nodes, two bare edges).
- **Rule** = LHS / RHS / NAC / drop, each a list of `Pat(s, p, o)` triple-patterns joined by
  **shared bindings** (a subgraph). Slots: `?x` (variable), `paul?` (bound literal — binds the
  rule's own token / mints a fresh rule-scope node), `is_a` (plain literal — reuses a same-named
  node). The predicate slot may itself be a variable `?p`.
- **Matching** is **homomorphic** (distinct pattern keys may co-bind — needed for control tokens
  and self-relations) and **unbounded** (the old hop-`radius` scope is retired). It is kept cheap
  by **seed-from-ground**: each pattern seeds from its most-selective *ground* anchor (a literal or
  already-bound variable) located O(1) through the lexical index; a free-only pattern yields nothing
  and must be demand-driven. NAC groups are independent (`not A and not B` = ¬A ∧ ¬B). Graded
  conditions apply an α-cut.
- **Firing**: every enabled match fires (no branch selection). Derived confidence =
  `rule-probability ⊗ graded-degree ⊗ matched-confidence`. `drop` deletes control relations only.
  Re-firing the same (rule, bindings) is suppressed → monotone rules terminate.
- **Tools** are calculators on opaque nodes: a rule emits a `<call>` node, the engine services it
  at each fixpoint through a registry and folds the result back in. A rule never calls a tool's
  internals; a tool never rewrites. They couple only through nodes.
- **Provenance** is in-graph: each firing materializes a justification node `<j:KEY> --proves-->
  C`, `--uses--> Pi`. `explain` traverses these — no separate journal for explanation.
- **Two layers, one graph** (`vision.md` §5): a **monotone fact layer** (reasoning never deletes;
  truth changes by adding marker nodes read through a guarded filter) and a **non-monotone control
  layer** (tokens, plan scaffolding — freely created and deleted, only control edges, only
  token-gated). The linter flags any ungated deleting rule.

### Two processing paths

- **Batch corpus loading** (`load_corpus` / `load_facts`): `tokenize` (tool) → `run(FORM_RULES)`
  → `canonicalize` (merge-based coreference tool) → `run(universal + domain rules)`. Same-named
  mentions are merged; efficient, used by the examples.
- **Interactive Session** (`session.py`, behind the REPL): **lazy**. Asserting a line runs
  recognition + reasoning only. Coreference and contradiction detection are *pulled* by the read
  paths — a question seeds a `<demand>` → a rule emits a `<coref-request>` → the dispatcher runs
  `coref_on_demand` (selective: a link is kept only if it does not break consistency). Under this
  path a bare repeat is a *distinct witness*, not a contradiction; a genuine one-entity mistake is
  caught only with explicit-identity grammar (`X is one thing`).

---

## The package

Core engine (the substrate + rewriting):

| File | Role |
|---|---|
| `world_model.py` | `Graph` of instance nodes + untyped edges; `add_node`, `add_relation`, `out`/`into`, `succ`/`pred` views, `nodes_named`, O(1) `name_count`, embeddings, `gc_disconnected`, `copy`. |
| `production_rule.py` | rule layer: `Pat(s,p,o)`, `Rule`, `GradedCondition`; token helpers (`is_var`/`is_bound_literal`/`binder`/`literal_name`). |
| `rewriter.py` | the engine: `run(graph, rules, *, tools, seeds, max_steps)`, `match`, `nac_blocks` (independent negation groups), `graded_degree`, `apply_rule` (applies `rule.propagate` embedding ops); seed-from-ground `_triples`, delta matching. |
| `kb.py` | `RuleBank` — a thin rule container (`add`/`extend`/`all`/`by_key`). |
| `dispatch.py` | materialized tool calls — the engine-managed §8 boundary; `<call>` nodes serviced at each fixpoint via a `tools=` registry. |
| `provenance.py` | in-graph justification nodes (`<j:KEY> --proves/uses-->`); explanation by traversal. Provenance is MATCHABLE by provenance-aware (meta/TMS) rules — a rule that names `proves`/`uses`/`unless` (`rewriter._pats_touch_prov`); ordinary rules never bind it (docs/depythonization_design.md §2). |
| `retraction.py` | truth-maintenance. Legacy Python driver `cascade_retract` (relocation to `<quarantine>`, still used by coref). NEW rule-based path (`RETRACT_RULES`): seed `<retract> targets ?rel` → CASCADE along `proves`/`uses` → INTERPOSE hides a fact by `rewire`-splicing an inert `<retracted>` node into its 2-hop path (reversible; matcher untouched). Run `provenance=False` (regress guard). |
| `demand.py` | on-demand / demand-driven evaluation — derive a fact only when a `<demand>` needs it. |
| `decide.py` | forcing a decision — negation decided-on-demand per tuple, ALL RULES. Completion = a generated rule (`completion_rule`, emitted by `authoring._completion_rules`) that materializes `?c is_not P` for a closed-world consumer's positive residual; the consumer matches that negative POSITIVELY (NAC dissolved). Completion is AGGRESSIVE+MONOTONE (a NAC would false-cycle through the overloaded copula `is`); `DEFEAT_SEED` (`?c is ?p and ?c is_not ?p` → `<retract> targets` the negative) + `RETRACT_RULES` repair the over-completed ones. `solve` = derive+complete (provenance on) then, iff defeated, the retraction pass (off). |
| `driver.py` | the one generic dumb loop: run an ordered plan of phases to fixpoint, service tool requests between phases. No domain knowledge. |
| `lint.py` | static rule-linter against the system's own invariants (§2/§5): ungated-delete, unbound-drop, no-op, negation-cycle, opt-in dead-predicate. |

CNL — recognition, authoring, questions (all "forms = acceptance grammar as rules"):

| File | Role |
|---|---|
| `forms.py` | CNL loading + normalization: `tokenize` (the one mechanical string→nodes tool), `FORM_RULES`, `canonicalize`, declared relations/verbs/prepositions, n-ary event forms + questions. |
| `authoring.py` | author a whole domain in CNL — facts + graded layer + native prose rules (`HEAD when …`) + loose-form lexicon + `load_corpus`. Prose and machine rules share `BODY_SPINE_FORMS` (one condition grammar). Degree scale (`very is 0.8`) is KB data. |
| `machine_rules.py` | machine rule CNL — a formal HEAD surface (multi-clause + `drop`) for control/machinery rules; body reuses the shared spine. |
| `query.py` | ask the KB in CNL, get CNL answers; `QUESTION_FORMS` (yes/no, who, why) recognized emergently, executed by a §8 tool over `match`/`explain`. |
| `procedure.py` | named ordered action sequences (`to brew a then b`) that desugar to planner operators; gap-filling routes an unmet step precondition to the planner. |
| `rule_graph.py` | rules as graph nodes (homoiconic, Prong B/b1): `write_rule`/`rules_in_graph` round-trip; relation-property + constraint schemas. |

Reasoning, planning, knowledge:

| File | Role |
|---|---|
| `universal.py` | domain-independent reasoning `Rule`s (is_a transitivity, goal satisfaction). |
| `planning.py` | goal → plan → act → replan, entirely as rules (no planner). Seeds operators/state/goal; banks live in `corpus/planning*.cnl`; tools `rank_by_cost` / `price_handler` / `act`. Zero `Rule(` literals. |
| `external.py` | external knowledge as request tokens + generic dispatcher + freshness (`supersedes` + guarded read, §5). Migrated onto `<call>`. |
| `walker.py` | variable-length graph traversal as control token-passing (origin + frontier + fuel + provenance shortcuts); rules in `corpus/walker.cnl`. |
| `coref.py` | selective coreference via reasoning — link mentions on demand, keep a link only if it does not break consistency. |
| `interaction.py` | human-in-the-loop: the user as an external source (§8) via an `Oracle`; only genuinely-ambiguous decisions are surfaced. |

Surface + user-facing:

| File | Role |
|---|---|
| `surface.py` | narration + explanation (journal / justification readers). |
| `session.py` | the stateful user-facing engine API: `submit(line) -> LineResult` (assert or answer), `facts`, `contradictions`, `unparsed`, `explain`. Lazy pipeline. |
| `repl.py` | the TUI over `Session`: `python -m harneskills.repl [file.cnl …]`; `:load :facts :rules :check :unparsed :why`. Wires a terminal oracle. |
| `__init__.py` | public API re-exports. |

CNL corpora (`corpus/`): `icecream.cnl` (the whole ice-cream demo), `walker.cnl`, `procedure.cnl`,
and the planner banks `planning.cnl` / `planning_requests.cnl` / `planning_execution.cnl` /
`planning_detect.cnl` / `planning_teardown.cnl`.

Examples (`examples/`): `ice_cream.py` (thin loader over the CNL), `coffee.py` /
`coffee_external.py` (the planning loop), `consistency.py`, `procedure.py`.

Benchmarks (`bench/`): `wordnet_scaling.py`, `wordnet_messy.py`, `proofwriter_coverage.py`
(the scale-beyond-toy probes).

---

## The CNL grammar (as implemented)

- **Facts.** Copula `X is Y`, `X is a Y` (→ is_a), `X wants Y`, explicit placement `X in Y`,
  declared binary relations (`R is a relation` → a generated `X R Y` form), n-ary events
  (declared verb + prepositions: `alice gives book to bob`), the graded layer
  (`urgent is gradable` + `alice is very urgent` → an embedding).
- **Surface normalization (determiners + multi-word entities + pronouns), as FORMS.**
  `forms.surface_forms` builds ordered strata of normalization rules that `normalize_surface` runs
  on the token chain before the content forms (they may `drop` surface `next`/`first` edges —
  ephemeral scaffolding, control-deletes-control §5). (1) **Determiners** are bridged out of the
  chain (a NAC keeps one inside a fixed phrase like `is the same as`). (2) **Multi-word entities
  DECOMPOSE**: a modifier before the noun-phrase head becomes an attribute — `the bald eagle` →
  head `eagle` + `eagle is bald` — gated to determiner/quantifier-introduced NPs by a `det_np` tag
  (so gibberish and undeclared verbs are not turned into attributes); a copula guard stops it
  splitting a bare predicate (`is alice happy`). (3) **Pronouns** (`it`/`they`/…) resolve to the
  discourse subject (`Session._last_subject`, §14 recency) by `expand_pronouns_text` substitution —
  anaphora is name-level coreference (one node), the same name-op category as `canonicalize`, kept
  outside the grammar. Function-word / determiner sets are DATA (read from the active forms +
  declared words). Applied on both the assert and question paths. (Indefinite existentials
  `someone`/`something` are NOT handled — they quantify rather than refer.)
- **Rules.** Prose `HEAD when COND and COND…` with copula sugar (`is a` / `is not` / `is
  <adverb>` / `not in`); machine `H1 and H2 when B1 and B2`, bare `S P O` clauses, `drop`, `not`
  NAC, `<token>?` control tokens. Both fold the body through the shared `BODY_SPINE_FORMS`.
- **Universals** are LAWS, not facts: `every X is a Y` reflects to a rule matching witnesses by
  name (no merge needed).
- **Meta-declarations** (relation properties / constraints): `is_a is transitive`,
  `R is symmetric`, `A disjoint_from B`, etc. — each a §8 tool that emits the concrete rule-node.
  Inconsistency is detected by ADDING a `<contradiction>` marker (paraconsistent, never reject).
- **Identity.** `X is one thing` (single identity), `X is the same as Y` (cross-name coreference).
- **Procedures.** `to NAME step then step` → planner operators.
- **Questions.** yes/no (`is S P O`), wh (`who P O`), why (`why S P O`), and n-ary
  (`who gives book to bob`). Recognition emergent; an unrecognized question yields no answer.

An unrecognized line stays as raw tokens — the natural place for the linter/Session to report
"no form recognized this," never a silent drop.

---

## The planner (goal → plan → act → replan)

Entirely rules over the two-layer split: operators + observed state are **monotone facts**; the
plan + execution cursor are **control** scaffolding torn down on divergence. Phases:
A relevance (backward from goal) → B connection (forward reachability, an outer loop over the
stratified bank for the fixpoint) → C ranked commitment (by fact-layer `cost`:
`rank_by_cost` → `cheaper_than` → `dominated`/`best`/`choose`) → D acting (a materialized `<call>`
to the `act` tool, observed effect may diverge from the declared one) → E divergence → replan
(teardown of control markers). External cost lookup is on-demand with §5 freshness. Guardrail:
commitment may live in control, but the *criterion* for it must live in the fact layer.

---

## The graded and metareasoning layers

- **Graded layer** (`vision.md` §13): probability as a rule prior / fact confidence (the engine's
  semiring), and sparse named embeddings on nodes (qualitative directions). Engine = the mechanism
  (dot-product similarity, t-norm aggregation, α-cut, graded firing, `rule.propagate`); authored =
  the dimensions, values, and weights. Kept and first-class.
- **Metareasoning layer** (`vision.md` §14): content-blind effort/budget policy (name-frequency /
  idf for anchor selection, α-cut thresholds, fuel budgets, fire counts). It reads *structural*
  statistics and *exogenous* budget, never what a node means. This is the bright line that keeps
  the rejected smart planner out.

---

## Decisions locked in (don't relitigate without reason)

1. **Edges untyped; relations are nodes; nodes carry no values; no semantic name index** — nodes
   are located only by matching on name (the lexical index is an internal matcher accelerator).
2. **Probability AND embeddings kept** as the graded layer. Rejected: probability-as-branch-
   *selector*, PCFG grammar, engine-enforced normalization. EM learning is *open*, not rejected.
3. **Homomorphic matching** (not injective).
4. **Matching is unbounded** (hop-`radius` retired); seed-from-ground keeps it cheap.
5. **Coreference is selective and on-demand** (`coref.py`) for the Session; `canonicalize`
   (merge-all-same-name) survives only on the batch corpus path.
6. **Forms = acceptance grammar as normalization rules** + one tokenizer tool. No CNL→IR compiler.
7. **Negation is stratified-only** — a cyclic negation is refused, not guessed; `run_rules`
   degrades to the monotone subset and warns rather than losing the whole theory.
8. **The scheduler stays dumb** — all control is token-passing data; tools couple to rules only
   through `<call>`/request nodes; provenance is in-graph.

---

## Known gotchas

- **Windows console is cp1252** — no non-ASCII in `print` (a `✓` crashed the REPL).
- **Per-line Session reasoning re-scans the whole KB** — name-matching across disconnected
  mentions is non-local, so a graph-hop locality seed would drop valid derivations. Correct but
  O(KB)/line until index-aware locality or coref-first connection lands.
- **`stratify` is predicate-NAME granular** — an object-aware (per-tuple, `(pred, literal-obj)`)
  stratifier would be a general fix. This granularity is exactly why closed-world completion is now
  an AGGRESSIVE+MONOTONE rule + DEFEAT (a completion NAC on `?c is P` would false-cycle through the
  overloaded copula `is`; see `decide.completion_rule` and docs/depythonization_design.md §5). An
  object-aware stratifier would let completion carry its natural NAC and drop the over-completion
  churn — the documented cleaner fix.
- **Rule keys** `rule.<head.s>.<head.p>.<head.o>` collide on a repeated head triple (prose path).
- **Dense/cyclic-relation walks flood the hub** — work is O(reachable component), not
  O(answer-distance); the open Tier-4 performance item.
- **A multi-word subject + bare predicate in a yes/no STATE question can't split** —
  `is the bald eagle happy` has no marker between the subject NP and the predicate, so
  decomposition mis-fires; `is the bald eagle a bird` (article separates) and the declarative
  `the bald eagle is happy` (`is` separates) both work. A bare multi-word entity with no
  determiner/quantifier introducing it (`bald eagle is a bird`) won't decompose (the `det_np`
  gate keeps controlled-CNL from treating any word run as a noun phrase) — use `the`/`every`.

---

## Pointers

- Canonical philosophy: `docs/vision.md`.
- Design docs: `docs/walkers_and_locality.md`, `docs/planning_design.md`,
  `docs/consistency_design.md`.
- Memory decisions/findings: `decision_one_substrate_vision`, `decision_quantification_coreference`,
  `decision_locality_rete`, `decision_metareasoning_layer`, `decision_materialized_tool_calls`,
  `decision_machine_rule_cnl`, `decision_nac_grouping`, `decision_walkers_locality`,
  `decision_forcing_a_decision`, `finding_matcher_is_matching_bound`, `finding_coverage_proofwriter`.
