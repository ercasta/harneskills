# Harneskills Spec — Changelog

**Version:** 4.1
**Date:** 2026-06-14
**Changes in 4.1:**
- **§4.7.8 Negative Application Conditions (NAC)** — `nac: list[Branch]` added
  to both `ProductionRule` and `RewriteRule`. A rule fires only when the LHS
  matches AND no NAC branch matches. DPO-with-NACs semantics (Ehrig 2006).
  NACs on production rules act as negative preconditions in the planner's routing
  pass. Example: `Paul NOT (is_a Person)`.
- **§4.8 Rule Co-Activation Graph** — each rule is already a WM node in the KB;
  `likely_next` is a new relation terminal linking rules that tend to co-fire.
  EM over session firing logs updates edge probabilities. The Reasoner uses
  `likely_next` links to pre-load the next-step candidate beam; System-1 fires
  pre-loaded rules automatically when preconditions are met. RewriteRules may
  target the rule graph itself, enabling meta-level routing updates.
**Changes in 4.0:** Graph grammar foundation, rewrites as a third computation
mode, System-1/System-2 distinction, and `ProductionRule` branch schema formalized
(absorbing `docs/arch_addendum_rewrites.md` v2). Key additions:
- **§2.5 Three Computation Modes** — tool dispatch, KB navigation/planning, and
  rewriting (pure WM graph transformation, no I/O) as orthogonal, named modes.
- **§3.9 Fact Value Opacity** — fact values are atomic labels; the rule system
  never inspects their content. `Ref` type introduced as the only traversable
  value. Technical debt table for structured-value slots.
- **§4.2 ProductionRule schema** — `Branch` dataclass added; `ProductionRule`
  gains `branches: list[Branch]` (AND-fork). `rhs: list[Symbol]` is superseded
  but backward-compatible (single-branch rules use `branches=[Branch(rhs)]`).
  Generic slot-name variables (`NT("inferred.?S")`) and entity variables
  (`NT("concept", var="?F")`) formalized together under §4.2.5.
- **§4.7 RewriteRule schema** — DPO graph rewrite rules stored in the KB at
  `rewrite.<name>` keys; LHS/RHS as list[Branch]; node variables `NT("?x")` and
  `Ref("?x")`; termination protocol (max_steps + no-same-subgraph-twice);
  bidirectionality; context sensitivity.
- **§7.3 System-1: Automatic Expansions** — fires after every `dm.apply()`,
  max 2 hops, expansions only, no rewrites.
- **§7.4 System-2 and `tool.think_harder`** — deliberate rewrites scheduled by
  the planner; parameterized depth expansion.
- **§9.2** and **§13.1** updated to include `RewriteRule` as a KB entry type
  and rewrites as a fifth consumer.
- **Appendix** extended with literature references for HRG, DPO, interaction
  nets, string diagrams, rewriting logic, term rewriting, subgraph isomorphism,
  and RETE (from addendum §N).
**Changes in 3.0:** Architecture simplified to a fetch-execute loop with an
explicit Plan object (§7). Planner renamed **Reasoner**; interface changed to
`step(world_model, kb, plan, goal) → (action, plan)` — stateless, Plan carries
all reasoning state between calls (§6.5). Dispatcher simplified to a
function-call mediator; pending delta machinery flagged for Track C removal
(§6.4). Tools added to KB as `causes`/`requires` rules; ActionCatalog dissolves
into KB (§9.2). New §3.8: WorldModel granularity principle, session isolation,
heap/stack/plan model, hypothesis management boundary. Refactoring tracks A/B/C
defined in `docs/implementation_handoff.md`.
**Changes in 2.9:** `is_a` added as a named relation terminal (§4.2, §4.2.3).
`is_a`-typed rules occupy their own lane in the planner's routing table
(subsumption), exactly like `causes`, `requires`, and `has_part`. New §4.2.3
explains subsumption inference through the PCFG model using the
`paul is_a person` / `person mortal` example: transitivity is implicit in
recursive non-terminal expansion; no separate reasoner or closure pass is
needed; probabilistic class membership follows from the standard OR-node
Bayesian update.
**Changes in 2.8:** Production rule formalism made fully explicit (§4.2,
§4.2.2): `Symbol(name, terminal)` distinguishes terminals from non-terminals
in the RHS; relation-type symbols (`causes`, `requires`, `has_part`, …) are
terminals, not encoded in the key name. Each concept maps to a list of
independent `ProductionRule` objects firing in parallel; probability
normalization is per `(LHS, first-terminal)` group, not per entry.
`EmbeddingEquations(synthesized, inherited)` replaces `embedding_delta`:
explicit invertible functions in both directions, enabling the same rule to
operate in generation (top-down) and recognition (bottom-up) without separate
propagation logic. `shifted_eq` is the invertible replacement for the former
`embedding_delta` field. KB facts section updated: global-scope facts stored as
plain strings (sentences in the KB language), parsed on read (§4.1).
AND-OR hypergraph description updated to reflect parallel-rules model (§4.1).
**Changes in 2.7:** KB grammar simplified to plain PCFG (§4.1, §4.2):
`verb` and `preconditions` fields removed from production rule schema —
context encoded in node name; absence of a rule replaces guards; action
catalog `preconditions` are unaffected. §4.2.1 (entry kinds by verb)
removed. Grammar/language duality made explicit in §4.1: KB stores both
production rules (grammar) and global-scope facts from past runs (language).
§6.1 NLP vocabulary updated: derived from KB entry keys only (no `verb`
fields). README updated accordingly.
**Changes in 2.6:** embedding rescoring of branch alternatives added to
§4.2.2: `P(branch) ∝ prior × sim(parent.embedding, branch_targets)` — the
Bayesian update inside each OR-node that ranks gradable qualities without
hard thresholds; connection to SoftDimension weights in the objective
function (§5.3).
**Changes in 2.5:** embeddings restored as first-class elements of the
production rule formalism (§4.2.2, §3.3): node embedding (authored), branch
embedding_delta (per-scenario modification), synthesized embeddings bottom-up
for anonymous nodes (weighted aggregation), inherited top-down (grounder
ranking). Attribute grammar framing — synthesized and inherited attributes.
Appendix: TreeRNN / recursive neural networks as precedent.
**Changes in 2.4:** §4.6 added — KB structural optimization: binarization
(CNF, enables CYK), left-factoring (prefix extraction, reduces branching),
deterministic chain compression (residuals on collapsed chains), macro rules
from frequent subtrees (grammar analog of chain consolidation), split-merge
EM (Petrov 2006 — structural optimization beyond probability fitting), prefix
trie and BDD storage. Prior art rows added to appendix.
**Changes in 2.3:** §4.3 rewritten — corpus reading as production rule
extraction is the primary bootstrapping strategy; two explicit steps: rule
extraction (parse corpus in recognition direction, unmatched subgraphs →
candidate rules) and probability optimization (EM/inside-outside over the
AND-OR hypergraph — identical to PCFG training); NL parsing works by the
same algorithm over the same grammar (§6.1). §4.5 framed as minimal seed
floor. Manual seeding demoted to fallback.
**Changes in 2.2:** §0 added — the unifying principle (reasoning and language
are formally the same operation; the KB is a probabilistic grammar; all
operations are parsing in different directions). KB formally characterized as a
probabilistic context-sensitive grammar and AND-OR hypergraph (§4.1), with
algorithm consequences (belief propagation, HTN planning, hypergraph
Earley/CYK). Generation is top-down derivation; recognition/hypothesis
formation is parsing in the recognition direction (§13.2, §13.5.1, §6.5).
Appendix extended with PCFG, probabilistic graph grammar, and AND-OR
hypergraph prior art.
**Changes in 2.1:** §4.2 rewritten — KB entries unified as production rules
(verb + preconditions + probability-distributed branches, sum-to-1 uniform
across all entry types; context encoded in node name). Causal multi-branch
entries as the mechanism for planner hypothesis formation added to §6.5.
§6.1 vocabulary derivation: domain no longer provides a separate vocabulary
list — entity names and verbs are compiled from KB content at startup. §10
domain responsibilities table updated accordingly.
**Changes in 2.0:** the spec is now the single design reference. Added §13
(the KB closure), §14 (code semantics layer — absorbs the former
code-semantics design document and the pattern-matching proposal it resolved),
§15 (plausibility multitree), and the prior-art appendix. Sections marked
*design direction* are agreed but not yet probe-validated; everything else is
probe-validated. The implementation record and probe plan live in
`docs/implementation_handoff.md` — the only other living document.
