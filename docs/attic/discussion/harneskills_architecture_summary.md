# Harneskills Architecture Summary

*A symbolic, interpretable, graph-grounded architecture for business-domain software engineering — with LLMs/SLMs strictly bounded at the edges.*

---

## 1. Core Principle

**There is one relational substrate, not several formalisms.** CPG (code), BSG (business semantics), and CNL (human-facing rules/specs) are not three things needing translation between them — they are three *interfaces* onto the same underlying store of typed tuples: `(entity_id, relation, filler)`.

- A property graph edge (`Cypher`) and a ground ASP fact (`clingo`) are the same tuple, differently indexed.
- CNL compiles directly into that tuple vocabulary (no CNL-specific intermediate).
- "Parsing" and "reasoning" are the same operation — pattern matching with variable binding — applied at different scales/shapes by different engines.

**Concept unification (e.g. "a loop") does not require a CPG↔CNL translator.** Define the concept once as a typed frame schema (e.g. `Iteration(collection, element_var, body, condition?)`). Write independent recognizer productions on each side (CPG-side structural patterns; CNL-side grammar productions) that each populate an instance of that same frame type. "Matching" = do two independently-produced frame instances unify. Expect **many-to-one**: several structurally distinct CPG shapes (for-loop, while-loop, list comprehension, recursion) may all express one concept — each needs its own recognizer.

---

## 2. Representation Requirements ("what allows reasoning")

For a frame representation to be reasoned over cleanly, it needs:

1. **Typed, not string-labeled** — types/roles are symbols rules can quantify over.
2. **Identity separated from content** — opaque ID + role-edges pointing to other IDs, never inlined copies. Makes unification O(1) per edge instead of deep comparison.
3. **Reified as triples** — `holds(frame_id, role, filler)` — simultaneously a graph edge (Cypher-native) and a ground ASP fact (clingo-native). This *is* the "one substrate, two engines" mechanism, concretely.
4. **Rules stated over types/roles, not instances** — a representation meeting (1)–(3) makes generality *possible*; the rule author still has to write mechanism-level rules ("iterator mutated during iteration is unsafe") rather than surface-pattern rules ("don't mutate `self.queryset` in `get_context_data`") for compositional derivation to actually pay off. This is the main authoring-effort lever in the whole system.

---

## 3. Two Engines, Two Jobs

| | Cypher / Property Graph | ASP / clingo |
|---|---|---|
| Good at | Topological/structural queries — subgraph matching, path-finding | Closure, arbitration, defeasibility — stable models, default negation |
| Bad at | Fixpoint derivation, exception/priority resolution | Large-scale graph topology at speed |
| Use for | CPG/BSG structural matching, design-pattern & anti-pattern detection (NACs for "absent" patterns) | Business-rule arbitration, conflict detection, derived hazard rules |

**Pattern:** extract a bounded region of the graph as ASP facts → run clingo → write conclusions back as graph edges/properties. This is a format projection between two views of the same store, not a lossy translation.

**Tractability caveat (recurring):** subgraph isomorphism, HRG parsing, and ASP grounding are all worst-case intractable. Mitigate by bounding pattern size / treewidth in your recognizer productions — a design discipline, not a solved problem.

---

## 4. The Two-System (Fast/Slow) Split — apply throughout

Mirrors how human experts debug: fast pattern retrieval proposes a small hypothesis set; slow exact reasoning only ever touches that set. **Never run exhaustive global derivation.**

- **System 1 (gradable/statistical):** embeddings, idiom-frequency scores (DOP-style fragment counting over the CPG), symbol/term matching — proposes/ranks/prunes a small candidate region or rule set.
- **System 2 (discrete/exact):** ASP/clingo — runs only within the narrowed scope, with full soundness/critical-pair guarantees intact.
- **The threshold/commit point where a continuous score becomes a discrete "use this" fact is a deliberate design seam** — decide the cutoff and tie-breaking rule explicitly; this is where you knowingly trade completeness for tractability.
- Gradable attributes (your existing plausibility-multitree) are the right tool for System 1. Don't ask ASP to be graceful under uncertainty, and don't ask the gradable graph to give sound derivation — keep the jobs separated.

---

## 5. Recommended Concrete Tooling (for a fast, honest prototype)

Real compatibility issue: these tools come from different communities with different schemas. **Adopt a property graph (Neo4j) as the lingua franca**; treat everything else as a narrow, well-defined external call in/out of it.

- **CPG generation → Joern.** Mature, maintained. Exports to Neo4j-loadable CSV / GraphML / GraphSON / JSON via `joern-export` / `cpggen`. Most ready-to-use piece of the stack.
- **CNL parsing → your own two-pass parser**, not ACE/APE. ACE compiles to DRS (Prolog term structure), a different paradigm from a property graph — not worth bridging when you already control both ends of your own parser's output shape.
- **BSG / domain KB → your own schema, same Neo4j instance as the CPG.** Avoids cross-tool schema mapping entirely. (OWL/DL reasoners are the "standard" alternative but are monotonic — poor fit, since defeasibility is exactly what you need.)
- **Defeasible/business-rule arbitration → clingo** (Potassco). `pip install clingo`. Real, maintained, has Python bindings, native default negation / stable models.
  - CNL→ASP authoring precedent exists and is directly reusable: **CNL2ASP** (SBVR/PENGASP-inspired CNL compiling straight to ASP), **SBVR** (OMG standard, FOL-grounded, sometimes translated to Formal Contract Logic for non-monotonic legal/business reasoning), **RuleCNL/RuleSpeak** (authoring templates by rule category).
- **Rewrite layer (spec+KB → code) → hand-rolled Cypher transactions** (`MATCH`/`CREATE`/`DELETE`/`SET`), not a dedicated GTS tool (GrGen.NET/AGG/PROGRES are dated or don't speak your schema — not worth the integration cost for a prototype). Add formal DPO/SPO tooling later only if you need confluence/termination proofs.
- **Rule induction:**
  - **ILASP** for the BSG/KB (ASP) side — learns ASP rules (including defaults, exceptions, preferences via weak constraints) from positive/negative examples + declarative bias, with an *optimal-hypothesis* guarantee within the declared search space. Tolerant of noisy examples (ILASP3). Tractability lever = tighten the declarative bias (restrict hypothesis shapes) — same discipline as bounding pattern size elsewhere.
  - **Not directly applicable to gradable/continuous attributes** — ASP needs discrete ground atoms. Bridge by discretizing scores into bucket predicates (`confidence_high(X) :- score(X,S), S>=700.`) before ILASP sees them; learning the scoring/aggregation function itself is a separate regression problem, not an ILP problem.
  - **Grammar-induction (split-merge/EM, latent-variable PCFG/HRG-style)** for the CPG-recognizer side — a different formalism than ILASP, matched to that side's graph-pattern shape.
- **Neo4j Community Edition** is GPLv3, free for commercial use (including closed-source applications talking to it over the network). Enterprise only needed for clustering/HA at scale.

---

## 6. Staged Evaluation Plan (decouple risks; don't build extraction machinery first)

1. **Hand-author facts.** Write `.lp` facts or a tiny NetworkX graph *as if* extraction already ran, for 3–5 real cases. Run clingo directly. Answers: "does the schema let me state the rule / does it derive correctly" — before writing any extractor.
2. **Adversarial near-misses.** For each rule, hand-write a structurally-close case that should *not* fire. Rules tend to over-generate before under-generating — catch this cheaply, with zero extraction code.
3. **Synthetic scale.** Mechanically generate large synthetic fact sets (not from real code) matching your schema; check clingo grounding size / solve time. Isolates tractability from correctness.
4. **One real vertical slice.** Build the CPG→frame bridge for *one* frame type against a handful of real files; manually check extracted frames match Stage-1 hand-authored ones. Validates the recognizer in isolation before generalizing.
5. **QA as a separate axis from rule-detection.** Most real code questions are retrieval (graph traversal), not derivation — a different capability than the rules above. Test with hand-written questions + expected graph-query answers; consider repurposing existing code-QA benchmarks as adversarial stress tests (they'll surface schema gaps you wouldn't think to ask about). Also test **answer composition** (graph result → legible CNL/NL), the reverse direction of your CNL parser, which nothing else exercises.
   - Keep test questions in CNL/fixed templates during substrate evaluation — free-form NL questions reopen fuzzy-intent parsing, a separate thing to evaluate later; conflating the two makes failures impossible to diagnose.

---

## 7. LLM / SLM Boundary — where non-symbolic components go, and only there

**Principle:** LLMs live only at the edges — translating fuzzy human intent into CNL, and (optionally) reading arbitrary external artifacts (issues, docs, error messages). Everything inside the controlled surface (parsing, unification, defeasible arbitration, transformation, comprehension, pattern/anti-pattern detection, idiom scoring) stays symbolic.

**Critical trap to avoid:** don't let an LLM-derived KB (e.g. "read this library and infer its invariants") become trusted ground truth — that just relocates Cyc's knowledge-acquisition bottleneck one layer up and hides it behind a confident-looking parse. Instead: **LLM proposes (as tentative, tagged-unverified CNL/frames) → symbolic layer + real signals (test suite, KB consistency) dispose.** Promote what survives falsification; discard/flag what doesn't.

### Fine-tuned small model for NL → CNL specifically

- **Feasible, and one of the more tractable pieces of the whole architecture** — it's translation into a *closed target grammar*, not open generation. Current evidence: fine-tuned 3–4B models (Qwen3-4B, Llama-3.2-3B) match or exceed much larger teacher models on narrow, specialized tasks.
- **Use grammar-constrained decoding** (GBNF-style grammars / `outlines`/`guidance`) so syntactically invalid CNL is unreachable at generation time — offloads syntax correctness to the decoder, leaving the model to learn only the semantic mapping.
- **If vocabulary is explicitly the KB's job, not the model's:** drop per-construct example counts substantially (~20–50 examples/construct instead of 100+; synthetic/nonsense filler words work fine for structure-only training, per the standard grammatical/lexical competence separation). But add a **dedicated copy/pointer-behavior training slice** (~50–100 examples) so the model learns to pass unrecognized tokens through verbatim into the correct slot rather than "helpfully" normalizing them into something that happens to parse but is wrong — a known failure mode without explicit training against it (cf. copy mechanisms in NL-to-SQL).
- **Data generation:** sample valid CNL from your own grammar, back-translate to plausible NL via a larger model — a standard round-trip augmentation pattern, cheap and scalable, no manual annotation needed. Sample broadly across constructs, not just common ones.
- **Evaluation:** your own CNL parser is a free, automatic, exact grader — feed model output back through it; score parse-success and frame-graph match against ground truth per construct. Score copy-behavior and construct-coverage as *separate* metrics; a single aggregate blurs two different failure modes.
- **Model size:** 3–4B is a safe default. **~0.8B is plausible only for your simplest/shallowest constructs** — sub-1B models are known to degrade on multi-step compositional structure (nested exceptions, multi-role binding), independent of vocabulary breadth. Decide per-construct via the same evaluation harness rather than assuming uniformly yes/no; full fine-tuning (not just LoRA) becomes affordable and may be worth it at this size.
- **Hardware:** modest. QLoRA fine-tuning of a 3–4B model needs ~15GB VRAM — fits a **free** Colab/Kaggle T4. Recommended stack: Unsloth + HF PEFT + bitsandbytes (NF4). Local alternative: any 8–12GB consumer GPU (RTX 3060/4060). Apple Silicon (M3 Pro+) works via MLX, ~3–5x slower wall-clock. With only a few hundred examples, whole runs likely take minutes to under an hour.

---

## 8. Does Any of This Solve Cyc's Knowledge-Acquisition Bottleneck?

**Not in general.** A cheap NL→CNL interface lowers the barrier to *expressing* a rule someone already knows — it does nothing about the combinatorial cost of *inventing and vetting* rules, which was Cyc's actual bottleneck (each new fact must cohere with everything already encoded; cost grows with KB size).

**But it does help meaningfully in one specific, real scenario:** bootstrapping from **existing, trusted, narrow-domain documentation**. This converts *elicitation* (Cyc's hard problem) into *extraction* (a materially easier NLP task — closer to relation extraction from an authoritative source than to open-ended ontology engineering), and the domain is bounded rather than open-world, capping consistency-checking cost at domain size rather than "all of world knowledge."

**Caveats to actually test, not assume:**
- "Assume the rules are correct" doesn't mean *complete* — documentation typically omits tribal-knowledge exceptions everyone in the department just knows. These surface as silent gaps, not detectable contradictions — same long-tail risk as everywhere else in this architecture, just relocated to "cases the documentation doesn't mention."
- Real documentation is often multi-authored, drifts over time, and can silently contradict itself across sections — worth a cheap consistency audit (compile all sections into one KB, check for direct contradictions) before trusting it, using the same Stage-1/2 adversarial-testing discipline from Section 6.
- Integrating multiple documents into one KB still needs entity/terminology alignment (same term, different meaning across sections, or vice versa) — its own extraction/alignment task.

**Net verdict:** treat the extracted KB as a strong first draft to stress-test against real case/transaction data, not as ground truth the moment extraction finishes.

---

## 9. Scope Honesty: What This Architecture Is (and Isn't) For

- **Not** a replacement for an LLM coding agent on open-ended, arbitrary-codebase tasks (e.g. most of SWE-bench) — that territory is exactly the fuzzy-intent + no-provenance + open-domain-logic zone this architecture deliberately excludes.
- **Is** a strong fit for: regression prevention and known-defect classes within a well-modeled library/domain — a linter with teeth that can also propose the fix (production-rule RHS doubling as repair template), plus a candidate LLM-agent-loop augmentation (CPG-based localization à la Repograph; clingo-based invariant checks as a pre-test-suite filter with an attributable rejection reason).
- Composability (rules deriving novel-looking conclusions from combining basic mechanism-level rules) is real and precedented (type systems, abstract interpretation already do this) — but bounded by the *generality* of the basic rules you write, not their count, and bounded by solver tractability for the derivation itself.

---

## 10. Open Design Decisions Worth Deciding Explicitly (not defaulting)

- Aggregation function for gradable scores (sum/product/min/Bayesian) — no canonical answer; a modeling choice with real downstream consequences.
- Confidence threshold and tie-break rule at the System-1→System-2 commit point.
- Declarative bias / hypothesis-space restrictions for ILASP and for CPG-recognizer induction — the main lever against combinatorial search blowup.
- Which target formalism CNL rules compile to (plain FOL vs. ASP vs. Formal Contract Logic) — matters primarily for whether defeasibility is native or bolted on.
- Bounded pattern size / treewidth discipline for all graph-matching productions (HRG, CPG queries) — a standing tractability constraint, not a one-time decision.
