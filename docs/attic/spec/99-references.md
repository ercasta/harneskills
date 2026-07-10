> Part of the **Harneskills Architectural Specification** — see [`harness_arch_spec.md`](../harness_arch_spec.md) for the index and section map. Section numbers (§) are global across all parts.

## Appendix — Prior Art Index (§13–§15)

| Design element | Closest precedent |
|---|---|
| KB as probabilistic grammar; generation = derivation; recognition = parsing (§4.1, §13.2, §13.5) | Probabilistic context-free grammars (PCFGs); probabilistic graph grammars (Della Pietra et al.); stochastic attribute grammars |
| Binarization to CNF; left-factoring; deterministic chain compression (§4.6.1–4.6.3) | Chomsky Normal Form transformation; LL/LR compiler left-factoring; grammar compression (Lehman & Shelat) |
| Macro rules from frequent derivation subtrees (§4.6.4) | SEQUITUR (Nevill-Manning & Witten 1997); frequent subtree mining (Zaki 2002); chain consolidation |
| Split-merge EM for grammar structure optimization (§4.6.5) | Petrov et al., "Learning Accurate, Compact, and Interpretable Tree Annotation" (ACL 2006) |
| Prefix trie over branch targets; BDD distributions (§4.6.6) | Aho-Corasick; term indexing tries (E prover); algebraic decision diagrams (Bahar et al. 1993) |
| KB as probabilistic AND-OR hypergraph; OR-nodes = branch points; AND-nodes = co-occurring targets (§4.1) | AND-OR graphs (Nilsson 1971); AND-OR hypergraph search (Martelli & Montanari 1978); AO* algorithm |
| Inference over AND-OR hypergraph (belief propagation, max-product) (§4.1, §5.2) | Pearl, Probabilistic Reasoning in Intelligent Systems (1988); factor graphs (Kschischang et al. 2001) |
| Context-sensitive production rules; guards gate rule application (§4.2) | Indexed grammars; attribute grammars (Knuth 1968); conditional random fields |
| Embeddings as synthesized/inherited attributes on production rules (§4.2.2, §3.3) | Attribute grammars (Knuth 1968); Tree-structured RNNs / TreeLSTM (Socher 2011; Tai et al. 2015); recursive neural networks |
| Planner as parser over KB grammar; HTN planning as grammar derivation (§6.5) | Earley parsing; CYK; probabilistic chart parsing; HTN planning (Sacerdoti 1977; Erol et al. 1994) |
| Parameterised structural patterns, hand-authored, at scale | Coccinelle semantic patches (Linux kernel) |
| Bottom-up summary composition over call graph | Facebook Infer (bi-abduction); Godefroid SMART |
| Bottom-up cliché recognition | Wills' GRASPR (Programmer's Apprentice lineage) |
| Verb/plan interlingua between NL and code | Programmer's Apprentice (Rich & Waters) |
| Fingerprint pruning before matching | Term indexing in E / Vampire |
| Likely-invariant inference from traces | Daikon |
| Boundary-input search + shrinking | Hypothesis |
| Off-the-shelf symbolic execution for Python | CrossHair (deferred catalog tool) |
| Contract-generated mocks | Pact; Specmatic/OpenAPI |
| Learned-from-corpus fix patterns (future KB channel) | Getafix; Refazer |
| Spec skeleton bounding synthesis search | Sketch; SyGuS; Synquid (type-directed pruning) |
| Learned proposal prior + exact verifier | DeepCoder → LLM-proposes/verifier-checks |
| Mining patterns by recursion schemes | Meijer et al., "bananas and lenses" |
| Structured intermediate spec → generated artifacts (§13.2) | Model-driven architecture; contract-first API development |
| Domain-semantic dimension checking (§13.4) | F# units of measure; Frink; Pint |
| Code-fragment → domain-concept mapping (§13.5) | Biggerstaff, concept assignment (1994) |
| Selectional preferences with graded strength (§15.2) | Katz & Fodor (1963); Resnik (1996); Erk et al. (2010) |
| Typed verb-class argument restrictions (§15.2) | VerbNet; FrameNet frame elements |
| Spatial composition tables (§15.2) | RCC-8 (Randell et al. 1992) |
| Early category assignment to prune parse search (§15.2) | Supertagging (Bangalore & Joshi 1999) |
| Weighted prefix structures over semantics (§15.2) | WFSA composition (Mohri 1997) |
| Cross-domain type coercion (§15.3) | Pustejovsky, Generative Lexicon (1995); HPSG/LFG typed unification |
| Populated commonsense relation stores (§15) | ConceptNet; ATOMIC |

---

## §N Literature References — Graph Grammar and Rewrite Formalisms (§4.7, §7.3–7.4)

### Graph Grammars and Graph Transformation Systems

**Double Pushout (DPO) approach** — algebraic foundation for `RewriteRule` (§4.7):
- Ehrig, H., Pfender, M., Schneider, H.J. (1973). "Graph-grammars: An algebraic approach." *Proc. FOCS*, pp. 167–180. *(Original DPO paper)*
- Ehrig, H., Ehrig, K., Prange, U., Taentzer, G. (2006). *Fundamentals of Algebraic Graph Transformation*. Springer. *(Modern self-contained treatment)*

**Handbook (main reference):**
- Rozenberg, G. (ed.) (1997). *Handbook of Graph Grammars and Computing by Graph Transformation, Vol. 1: Foundations*. World Scientific.

### Hyperedge Replacement Grammar (HRG)

The formalism underlying the WM graph composition operators (§C.5 of addendum):
- Habel, A., Kreowski, H.J. (1987). "May we introduce to you: Hyperedge Replacement." *LNCS 291*, pp. 15–26.
- Drewes, F., Habel, A., Kreowski, H.J. (1997). "Hyperedge Replacement Graph Grammars." In Rozenberg (1997), Ch. 2.

### Interaction Nets

The fork/copy node formalism, relevant to AND-fanout in `Branch` (§4.2):
- Lafont, Y. (1990). "Interaction Nets." *Proc. 17th ACM POPL*, pp. 95–108.

### String Diagrams / Monoidal Categories

For sequential `;` and tensor `‖` composition operators as categorical structures:
- Selinger, P. (2010). "A Survey of Graphical Languages for Monoidal Categories." *Lecture Notes in Physics* 813, Springer, pp. 289–355.

### Rewriting Logic

For "rewriting as a computation mode" (§2.5) and term/graph rewriting:
- Meseguer, J. (1992). "Conditional Rewriting Logic as a Unified Model of Concurrency." *Theoretical Computer Science* 96(1), pp. 73–155.

### Term Rewriting (Confluence and Termination)

For the theoretical basis of §4.7.3 termination arguments:
- Baader, F., Nipkow, T. (1998). *Term Rewriting and All That*. Cambridge University Press. *(Standard reference; Chapter 2 covers confluence and termination)*

### Subgraph Isomorphism (Pattern Matching — §4.7.2, Probe L7)

- Ullmann, J.R. (1976). "An Algorithm for Subgraph Isomorphism." *Journal of the ACM* 23(1), pp. 31–42.
- Cordella, L.P., Foggia, P., Sansone, C., Vento, M. (2004). "A (Sub)Graph Isomorphism Algorithm for Matching Large Graphs." *IEEE TPAMI* 26(10), pp. 1367–1372. *(VF2 algorithm — recommended implementation)*

### Production Rule Systems (for System-1 efficiency — §7.3)

The RETE algorithm, relevant if System-1 expansion scales to large KBs:
- Forgy, C.L. (1982). "Rete: A Fast Algorithm for the Many Pattern/Many Object Pattern Match Problem." *Artificial Intelligence* 19(1), pp. 17–37. *(Foundation of OPS5, Drools, most production rule engines)*
