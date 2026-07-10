# Design — selective coreference via on-demand reasoning + a reversible TMS (2026-06-29)

> **Status: FIRST SLICE IMPLEMENTED (2026-06-29, big-bang).** The whole §8 first slice is
> built and GREEN (**77 tests pass**, ~3.6s). New modules: `provenance.py`, `retraction.py`,
> `demand.py`, `coref.py`. See the "IMPLEMENTATION NOTES" block immediately below for what
> was built, the design choices taken under the wall, and what remains. The rest of this
> document is the original design (still accurate as intent).
>
> Read `docs/vision.md` (§3 coreference/disambiguation as rules, §5 two layers, §6
> control-is-data, §9 provenance, §11 evaluation) and `docs/handoff_redesign.md` first. This
> is the plan for *selective* coreference — replacing the crude `canonicalize` merge
> (same-name ⇒ merge) with coreference that is **decided by reasoning**, on demand. It rests
> on a small, reusable mechanism (demand-driven evaluation) and a reversible
> truth-maintenance layer, both expressed as nodes + rules.

---

## IMPLEMENTATION NOTES (2026-06-29) — what was actually built

**1. In-graph justifications (the enabling engine change), `provenance.py`.** Every firing
emits a justification node `<j:RULEKEY>` with `--proves--> Ci` (each created fact) and
`--uses--> Pj` (each matched premise relation). `<axiom> --proves-->` grounds asserted facts
when needed (`axiomatize`). `surface.explain` was rewritten to TRAVERSE `proves`/`uses` (the
`journal`/`rules` args are now ignored/optional) — explanation is a graph walk, the firing
`Firing` list is no longer the source of truth (it is still returned, for the firing-count
tests). Readers: `support_js`, `rule_support_j`, `premises_of`, `proven_of`,
`justifications_using`, `derived_facts`.

**Provenance is INERT to reasoning** — held by four guards, because `J --proves--> C` points
an edge INTO a fact relation node and would otherwise pollute subject/locality lookups:
  - `Graph.within` skips provenance nodes → locality (the §11 Rete) is byte-identical to
    before, so a firing's `J` never bridges distant parts of the graph;
  - `Graph.relations_from` skips provenance subjects/middles → every `relations_from`-based
    reader (`expand_rules`, `rules_in_graph`, `contradictions`, frames, …) sees only domain
    relations;
  - `rewriter._try_bind` refuses to bind any pattern token to a provenance node → the
    `into(rel)` pollution never produces a spurious match (this was the subtle one: a
    `proves` node appears as an extra "subject" of the fact it proves);
  - `planning._fingerprint` excludes provenance edges → the plan fixpoint still settles.
  - Plus point fixes where a reader took `next(iter(into(rel)))` as the subject
    (`forms.declared_relations`, `session._content_relations`) and `canonicalize`'s
    protect-set (so the merge never tangles `proves`/`uses`).

**Provenance is OPT-IN, default ON (`run(..., provenance=True)`), but OFF for the planning
CONTROL loop.** A deliberate deviation from "always emit J": the non-monotone planning loop
churns its scaffolding for many cycles, and accumulated J nodes only slow matching — control
flow is not explained, so it needs none. `plan`/`solve`'s internal `run_rules` pass
`provenance=False`. (Without this, `solve` went from milliseconds to a hang.) Everything
else — reasoning, authoring, Q&A, coref — keeps provenance on.

**2. Reversible retraction, `retraction.py`.** `<quarantine>` relocation + a cascade.
`cascade_retract(graph, link)` quarantines the hypothesis and drives the existential
support cascade (§4b/§4d) to a fixpoint: a `J` that USES a quarantined node is quarantined;
a derived fact left with no LIVE justification is quarantined too. Base (asserted) facts have
no justification, so they are NEVER cascade candidates (`derived_facts` excludes them) — the
axiom mechanism is the belt-and-suspenders for facts that are *also* derived. **Deviation
from §4d:** the cascade is a small DRIVER TOOL, not pure control rules — "relocate ALL of a
node's edges" is not a single Pat pattern; the §4d rules are its declarative shadow. The
active graph stays clean (vision §11), consumer rules stay guard-free.

**3. On-demand evaluation, `demand.py`.** Validated on transitivity-on-demand (the simplest
case, no coreference): `seed_demand(g, a, c)` + `DEMAND_TRANSITIVITY` (a backward SPAWN rule
+ a demand-GATED DERIVE rule). Test proves selectivity: `a is_a d` is derived but `a is_a c`
is NOT (never demanded). NOT yet wired into `query`/`Session` (the `:check ⇒
demand(<contradiction>)` idea is still future).

**4. Selective coreference on demand, `coref.py`.** `coref_on_demand(graph, name)`:
hypothesize `same_as` between mentions, propagate (`same_as_rules`), check the declared
constraint schemas, and on a contradiction CASCADE-RETRACT the link + consequences and
record `not_same_as`. The end-to-end test: two distinct `paul`s in disjoint categories stay
SEPARATE (the link broke consistency → withdrawn), never merged; a compatible pair keeps its
link. Disambiguation by reasoning (vision §3), realized.

**Still open (next session):**
  - **Retire `canonicalize` from `Session`** — `coref_on_demand` is validated standalone but
    is NOT yet on the per-line `Session` path (slice item 4's tail). The merge still runs there.
  - **Demand-driven query / consistency** — route `ask`/`:check` through `<demand>` so the KB
    is lazy (slice item 3 wiring).
  - **Well-foundedness** for the general recursive case (§5; coref support is tree-shaped so
    it is fine now), and the cross-episode *confirmed*-coref-then-contradicted case (§9 deferred).
  - GC of dead provenance during long runs; folding provenance back ON for planning once an
    incremental matcher (§11 Rete) makes the J accumulation free.

---

## 0. The discipline this rests on

Coreference is the hardest case of *identity*, and merge gets it wrong two ways: it blows up
(every same-name mention linked → quadratic equality saturation — see `handoff_redesign.md`)
and it can't be selective (two genuinely distinct `Paul`s wrongly merge). The fix is not a
better heuristic; it is to **let reasoning decide identity**: link mentions tentatively, keep
a link only if it doesn't break consistency. That requires two pieces this doc designs:
**(A) on-demand evaluation** (so we only do coreference work a query needs — bounding the
blowup) and **(B) a reversible TMS** (so a wrong tentative link can be retracted, with its
consequences).

## 1. The big idea — on-demand (demand-driven) evaluation

Every blowup we hit came from **eager** forward chaining: derive *everything* to fixpoint
(the whole transitive closure, every same-name link) whether or not anyone needs it.
On-demand flips it: **derive a fact only when a demand needs it** — the Datalog *magic-sets /
demand-transformation* technique, which gets goal-directed evaluation *without* abandoning
forward chaining. This is not coreference-specific; it serves any expensive derivation:
- **transitivity on demand** — `is a is_a c?` walks the relevant `is_a` path; the O(N²)
  closure never materializes.
- **coreference on demand** — link an entity's mentions only when reasoning about *that*
  entity needs it; classes stay tiny.

## 2. Demands live in the substrate (no engine change for them)

A demand is a **node**; propagation is rules — this is *literally the planning loop's phase A
generalized* (`<goal> --want--> C ⇒ <need> --for--> C`, needs spawn sub-needs backward), which
is already proven. The scheduler stays stupid; demands are just more control tokens (§6).

- A query/goal emits `<demand> --holds--> P` for a pattern `P`.
- **Demand-propagation rules** (backward): a demand for a rule's head spawns demands for its
  body. Transitivity: `demand(?a is_a ?c) ⇒ demand(?a is_a ?b) + demand(?b is_a ?c)`.
- **Demand-gated derivation rules**: the ordinary rule, but firing only where its head is
  demanded. `?a is_a ?b, ?b is_a ?c, demand(?a is_a ?c) ⇒ ?a is_a ?c`.

**DECIDED (Q1): demands originate ONLY from explicit queries/goals.** A pure assert-only KB
derives nothing until asked. The eager/lazy tension dissolves: *everything is lazy*, and the
consistency-checker is just a standing demand — `:check` emits `demand(<contradiction>)`,
which pulls exactly the constraint derivations needed. Eager-vs-lazy is no longer a dilemma.

## 3. Selective coreference EMERGES (it isn't a separate heuristic)

It falls out of on-demand + the consistency machinery we already built:

1. **On-demand bounds the work** — a query about `X` links only `X`'s same-name mentions, not
   all mentions of everything. Small classes ⇒ no quadratic saturation. *That is the
   selectivity.*
2. **Tentative link** — to satisfy the demand, wire `X1 same_as X2` as a **hypothesis**
   (control layer, see §4), and propagate via the same-as rules.
3. **Contradiction-check + retract** — if the link makes `X` both `solid` and `liquid` (the
   constraint schemas fire `<contradiction>`), the link was wrong → **retract it** → `X1 ≠ X2`
   is recorded. *Two `Paul`s stay separate automatically, because merging them broke
   consistency.* No contradiction → the hypothesis stands and answers the demand.

So "which mentions corefer?" is answered by reasoning, not a rule of thumb — vision §3's
"disambiguation triggered by reasoning," realized.

## 4. The reversible TMS — provenance = retraction = explanation, all in-graph

### 4a. Justifications in the graph (drop the Python journal — no seams)

The firing journal is materialized as **nodes**, not an external Python list. Removing that
seam pays off three ways: retraction becomes rules (the support graph is matchable),
explanation becomes graph traversal (§9, what `:why` always wanted), and it is homoiconic
(§2 — rules can reason about derivations). Each firing `P1..Pn ⇒ C` emits a justification node
`J`: `J --proves--> C`, `J --uses--> Pi`. The bloat (a J per firing) is **affordable precisely
because we went on-demand** (firings are bounded by what queries need, not the full closure) —
lazy evaluation and in-graph provenance are natural partners. Mitigations if scope grows:
`proves`/`uses` are distinct predicates, so J-structure is inert to domain-rule matching; and
provenance nodes can be excluded from the default `within` scope.

### 4b. Reified support — "in iff some J proves it" (NO counting)

Each support is its own node, so "is this still supported?" is **existential**, a single-pattern
NAC — not a universal count. Retracting a premise removes the J's that *used* it; a fact with
another derivation keeps that J and stays in; a fact whose last J is gone has no `proves` edge
→ relocate. No counters, no "all supports gone" universal.

**Axioms:** every *asserted* fact gets `<axiom> --proves--> fact`. `<axiom>` is never
quarantined, so base facts always have a live proof and never relocate for lack of a J —
uniform, no "is this a base fact?" special case.

### 4c. Retraction by relocation — control deleting control (§5-clean), no guard tax

Retraction moves a node's active edges into `<quarantine>` (reversible), rather than the
vision's prescribed mark-and-guard. This is **better given the §11 lesson**: mark-and-guard
grows the graph with dead facts, taxes the matcher, and forces a NAC guard onto every consumer
rule — the exact cost we just fought. Relocation keeps the **active graph clean** (only true
facts) so matching stays fast and rules stay guard-free.

It stays inside §5 via a reframing: a **tentative coreference link and everything propagated
from it are CONTROL — a hypothesis under test, not monotone facts.** So relocating them is
*control deleting control* (legitimate), not deleting facts. The generic retraction is a
**control rule** (`drop` active edges + add quarantine edges), gated by a retraction marker.

### 4d. The cascade — two control rules, single-pattern NACs

```
cascade.J:     ?j uses ?n,  ?n in <quarantine>    ⇒  relocate ?j     (support using a dead premise dies)
cascade.fact:  ?c (a fact),  NAC ?j proves ?c       ⇒  relocate ?c     (no support left → out)
```
Relocating a node removes its active edges, including a J's `proves`/`uses`; that is what makes
the next NAC fire, which cascades. No counting; monotone-stratifiable; fully rule-expressed.
(`cascade.fact`'s `?c` must range over facts — relation instances — not J/entity nodes; a light
marker or structural guard handles that.)

### 4e. The coreference loop on this machinery
```
demand(X R Y) → wire hypothesis X1 same_as X2 (J: proves link, uses demand)
             → same-as rules propagate consequences (each J: proves Fi, uses link)
             → contradiction?  yes → quarantine link → cascade relocates consequences
                                      → link sits in <quarantine> as a recorded rejection (X1 ≠ X2)
                                no  → hypothesis stands, answers the demand
```

## 5. Cycles / well-foundedness — DEFERRED (and mostly pre-empted)

A support **cycle** (C's only live support uses D, D's uses C, neither grounded in an axiom) is
an *unfounded set*: the existential check says both are supported when neither truly is.

- **Coreference support is a TREE** (`demand → link → consequences`; consequences never support
  the link back), so cycles **cannot arise** — the existential cascade (§4d) is correct as-is.
  No grounding pass, no cycle detection, for the coreference slice.
- The general recursive case (e.g. transitivity over `a is_a b, b is_a a`) is the classic
  well-founded-semantics problem. The detection-free fix is **forward grounding from axioms**
  (an unfounded cycle is never reached from axioms, so it never gets `grounded` — no detection
  needed); the dual is backward cycle-detection (the "chain-id" idea — tag the traversal, detect
  revisits). Both resist pure rules (stateful path/cycle traversal), so this is a future **§8
  tool**, with the chain-id design banked for it.
- It is also partly **pre-empted**: cyclic `is_a` data is exactly what the `acyclic` constraint
  flags as a `<contradiction>`, so cycle-prone inputs often get caught upstream as modeling
  errors before they can form unfounded support cycles.

## 6. How this honors the vision
- **Stupid scheduler / control is data** (§6): demands and hypotheses are nodes; propagation,
  derivation, and retraction are rules.
- **No seams** (§3, §9): the journal is in-graph; explanation is traversal; nothing exits the substrate.
- **Two layers** (§5): tentative links/consequences are control (freely retracted); confirmed
  facts are monotone. Relocation is control deleting control.
- **Reuses the §11 win**: small same-as classes (from on-demand) + the lexical index make
  same-as-as-rules fast (already measured at ~0.01s for the small-class case).

## 7. What we reuse (little is from scratch)
- **Demand propagation** ≈ planning phase A (`PLANNING_RULES` relevance).
- **Contradiction detection** ≈ the constraint schemas (`rule_graph`: `<contradiction>`).
- **Relocation/retraction discipline** ≈ the §5 supersedes machinery built for external-lookup freshness.
- **Tentative linking** ≈ `forms.wire_same_as` + `universal.same_as_rules` (now fast via the index).

## 8. First implementation slice (when we start)
1. **Enabling engine change — in-graph justifications.** `run`/`apply_rule` emit a `J` node per
   firing (`proves` created, `uses` matched bindings); assert paths emit `<axiom> --proves-->`.
   Re-point `surface.explain` to traverse `proves`/`uses`; migrate `query.ask` / `planning.solve`
   off the Python `journal` arg. **Drop the `Firing` list as the source of truth.**
2. **Retraction layer** — `<quarantine>` relocation helper + `cascade.J` / `cascade.fact` control
   rules; verify a tree-shaped cascade relocates a link and its consequences (and resurrect =
   re-derive on a fresh demand, per the earlier "remember the rejection, re-derive the rest" lean).
3. **Demand mechanism** — `<demand>` tokens + propagation + demand-gated derivation, validated
   first on **transitivity-on-demand** (simplest; no coreference), then
4. **Coreference-on-demand** — tentative link on a demand, contradiction-check, retract; the
   end-to-end "two `Paul`s stay separate" test; retire `canonicalize` from the `Session` path.

## 9. Decisions
- **Made:** demands from explicit queries/goals only (Q1); justifications in-graph, drop the
  Python journal; reified per-firing support (existential, no counting); retraction by
  relocation framed as control-deletes-control; resurrection = re-derive on demand (stash only
  the rejection, not the consequence subgraph).
- **Deferred:** well-foundedness / unfounded-set handling for the general recursive case (a §8
  grounding tool; chain-id design banked); the cross-episode case where a *confirmed* (fact-layer)
  coreference is later contradicted by new assertions — genuine non-monotone *fact* retraction
  (tier-(b) tail).

## Pointers
- Vision: `docs/vision.md`. Sister designs: `docs/planning_design.md` (demand template = phase A),
  `docs/consistency_design.md` (constraint schemas / `<contradiction>`).
- Resume: `docs/handoff_redesign.md`. Memory: `decision_one_substrate_vision.md`.
