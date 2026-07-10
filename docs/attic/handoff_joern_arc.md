# Handoff — code-reasoning / real-Joern MDI arc (next rung)

> Focused resume point for the "does the substrate work past toy on real code" arc. Read this
> first, then the memory findings it cites. Parent plan: `docs/implementation_plan.md`
> (index `docs/reference.md`); philosophy `docs/vision.md` + `docs/vision_agentic.md`. Keep this SHORT —
> current state + the immediate next rung; land history in `docs/CHANGELOG.md`.

## What this arc is

The vertical slice that answers "past toy": detect a real code defect (mutate-during-iteration,
MDI) end-to-end through **real Joern**, and measure it. Every stage is now real: extraction
(pysrc2cpg + joern-export), decode (`parse_graphson`), recognition (frames), reasoning (hazard).

## Current state (2026-07-05) — 285 tests green (`.venv/Scripts/python.exe -m pytest -q`, ~24-31s)

**LATEST (next-rung option 1 STARTED — real noisy Django): a nested-loop FP class found + FIXED.** Ran the
MDI detector over real `django/utils` + `django/db/models` compiled by LIVE joern (per-file, crash-skip,
cached — scratch bench, not committed). `django/utils` flagged 4 hazards, all in `translation/template.py`:
`singular.append`/`plural.append` (accumulators) inside a `for t in Lexer(src).tokenize():` loop that has
read-only `for part in singular:`/`for part in plural:` loops NESTED inside it. **FALSE POSITIVES.** Root
cause (traced — NOT the new `same_as` rule): the shape-B `looptmp` recognizer bound the WHILE to its iterator
via `?w ast_star ?nc` (transitive), so an OUTER loop ABSORBED nested loops' `__next__`/iterator temps → the
outer loop appeared to `iterate` the inner collections → any mutation of them in the outer body false-flagged.
**FIX (one clause in `cpg.py` `JOERN_RECOGNIZER_RULES`, no engine change):** bind the loop to its OWN iterator
via the BOUNDED path `?w ast ?blk and ?blk ast ?nasgn and ?nasgn argument ?nc` (while → body BLOCK → the
`x=tmp.__next__()` assignment → the __next__ CALL; joern lowers this at a uniform 3 AST hops). Same class as
the shape-A `ast_star`→`ast` fix. Result: template.py 4→0, all `django/utils` (35 analyzed) 0 flags, curated
corpus STILL 8/8, and the FP shape is PINNED as `neg_readloop_nested_in_mutating_loop` (285 tests). Memory
[[finding-real-corpus-django]]. **Precision number is honestly THIN** —
0 true positives in mature library code (no positive denominator; a % needs code with real MDI bugs). **Two
real-world limits surfaced (each a rung):** (1) joern's dataflow overlay CRASHES on ~24% of Django files
(11/46 in utils; no `--repr` skips it — a `DdgGenerator` bug on closures), so the run is per-file with skip;
(2) `analyze` is ~O(n²) (106n→0.1s … 5175n→124s), so big modules (query.py) don't finish → the next scaling
rung is demand-driving `ast_star` instead of materializing the full closure.

**(next-rung option 2 DONE earlier this session): the documented alias miss is CLOSED.** `hard_alias_mutate`
(`a = xs; for x in xs: a.remove(x)`) is now `pos_alias_mutate` and CAUGHT — real-corpus recall is
**8/8, precision 8/8** through the live joern pipeline (fixture regenerated). Two rules added to
`cpg.py` (no engine change): a `same_as` recognizer (a plain two-identifier `<operator>.assignment`
aliases its two decls; `JOERN_RECOGNIZER_RULES`) + a `consumes`-propagation across `same_as`
(`MECHANISM_RULES`), so the EXISTING hazard rule composes UNCHANGED (vision §6). Precision is preserved
for free: a `list(xs)`/`xs[:]` COPY has a CALL rhs, so it yields one `asgnvar` and links no distinct
decls — copies stay silent. Staged to dodge the clause-order trap (see below): `asgnvar` threads a
SINGLE identifier (O(N)-linear, same shape as `itercoll`), the `same_as` join seeds from the rare
derived `asgnvar`. `analyze` on the corpus = 2.81s. Bench/test: `bench/joern_corpus.py`,
`tests/test_joern_corpus.py::test_alias_mutation_now_caught`. Memory [[finding-joern-lowering]].

Four earlier things landed this session, each with a bench + pinned test + a memory finding:

1. **Coverage/composition audit EXTENDED** (`bench/coverage_audit.py`, `tests/test_coverage_audit.py`).
   Acted on the audit's own follow-ups: closed the 2 CHEAP misses (one general rule each) and
   **imported `taint` as a premise CLASS** (3 kind-agnostic rules). The class GENERALIZED — caught a
   different sink kind + multi-hop dataflow it wasn't written for, near-misses silent. Baseline 53.3%
   → augmented 86.7% (8→13/15). Central bet cleared; no Cyc tell. Memory
   [[finding-coverage-composition-audit]]. Residual = 2 unimported premise classes (concurrency,
   arithmetic).

2. **CPG matcher-scaling probe** (`bench/cpg_scaling.py`, `tests/test_cpg_scaling.py`). An `ast`→CPG
   feeder over 31 real modules: the matcher SURVIVES real code graphs — `ast_star` closure is LINEAR
   (tree, not the dense/cyclic hub-flooding Tier-4 case). Surfaced + FIXED a recognizer PRECISION cliff
   (over-recognized `iterates` ~4× → 89 false hazards) by keying on the loop's DIRECT iterator child
   (`?loop ast ?id`). Memory [[finding-cpg-scaling-precision]].

3. **Real Joern SET UP + `parse_graphson` built** (`harneskills/cpg.py`, `tests/test_cpg_graphson.py`).
   JDK 21 + joern-cli installed; `parse_graphson` decodes TinkerPop GraphSON v3; `cpg.export_cpg(path)`
   runs the whole pipeline from Python. FINDING: real Joern DESUGARS Python `for` → `while` + iterator
   protocol (`tmp = coll.__iter__()` … `while: x = tmp.__next__()`) with fieldAccess receivers, so the
   fixture-tuned recognizer fired ZERO frames until rewritten. Memory [[finding-joern-lowering]].

4. **Recognizer rewritten for real Joern + real-corpus number** (`bench/joern_corpus.py`,
   `tests/test_joern_corpus.py`). Shape-B rules match Joern's WHILE/iterator lowering (kept shape-A for
   the fixtures/feeder; the two are structurally disjoint). On a labeled 15-shape corpus compiled by
   real Joern: **recall 100% (7/7), precision 100% (0 FP), 1 documented alias miss.** Memory
   [[finding-joern-lowering]].

## Environment (a fresh session needs this)

- **Python**: `.venv/Scripts/python.exe` (system Python has no pytest). ASP calculator needs `clingo`
  (already in venv).
- **Joern** (only needed to regenerate fixtures / analyze new source; the committed benches run OFFLINE
  from fixtures): `JOERN_HOME` = `C:\Users\ercas\tools\joern\joern-cli`, `JAVA_HOME` =
  `C:\Users\ercas\tools\jdk21\jdk-21.0.11+10` — both persisted at user scope. `cpg.export_cpg(path)`
  reads `JOERN_HOME`. Manual pipeline: `pysrc2cpg.bat <f.py> --output cpg.bin` then
  `joern-export.bat cpg.bin --repr all --format graphson --out <dir>` → `export.json`.
- **GOTCHA — downloads**: Windows `curl.exe` fails with schannel `CRYPT_E_NO_REVOCATION_CHECK` on this
  network; use PowerShell `Invoke-WebRequest` (or `curl --ssl-no-revoke`).
- **GOTCHA — CRLF**: the Edit tool has occasionally written CRLF; check `tr -cd '\r' < file | wc -c` == 0
  on touched files.

## The next rung (pick one; none is load-bearing — the go/no-go already passed)

1. ~~Bigger, NOISIER real corpus~~ **STARTED (django/utils + db/models); surfaced+fixed a nested-loop FP
   class, see Current state + [[finding-real-corpus-django]].** The honest precision number is still THIN —
   0 true positives in mature Django (no positive denominator). To finish it, point at code that actually
   HAS MDI bugs (student code, a known-bug corpus, or older Django/lib commits with the bug still present),
   not hardened stdlib-grade code. The scratch bench (`corpus_run.py`, per-file crash-skip + normalized-CPG
   cache) is in the session scratchpad; it's the reusable harness. TWO blockers to clear first (below).
   1a. **joern coverage (~24% of Django files skip).** joern-export always computes the DDG overlay and
       crashes on closures (`DdgGenerator`, no `--repr` skips it). We don't need the DDG. Rung: find/patch a
       way to export the base CPG (AST/REF/RECEIVER/ARGUMENT/control) without the dataflow pass → +~24%
       coverage, and lets whole-DIR export replace the slow per-file loop.
   1b. **`analyze` scaling (~O(n²): 106n→0.1s … 5175n→124s).** Big modules (query.py) don't finish. This is
       the real wall for real code. Rung: demand-drive `ast_star` (don't materialize the full transitive
       closure) or seed the recognizer off a rare anchor without needing `ast_star` materialized. Cross-ref
       [[finding-cpg-scaling-precision]], [[finding-matcher-is-matching-bound]].

2. ~~Close the alias/dataflow miss~~ **DONE** (see Current state above) — `same_as` alias resolution;
   recall 8/8, precision 8/8. The NEXT dataflow gap in this vein: aliasing through a COPY that is later
   mutated-and-iterated (`a = list(xs); for x in a: a.remove(x)` — a real bug our copy-is-safe assumption
   currently treats as safe because the iterable is a CALL). And multi-hop alias chains (`b = a; a = xs`).

3. **Import the next premise CLASS** (concurrency or arithmetic) into `coverage_audit.py`, per the
   audit's lever — the clearest demonstration that the frontier moves by importing classes.

## Strategic crossroads — is it time for the engine refactor (label-less nodes / graph-ISA)?

The arc's go/no-go PASSED (real defect, real joern, measured), and this session's two hardest limits are
BOTH engine-shaped, not domain-shaped:
- the **lexical clause-ordering trap** (compiler seeds `pats[0]` = the token-sorted-first pattern, not the
  most-selective one) — worked around by hand-splitting rules + rare-anchor seeding, but that's a recurring
  tax on every non-trivial rule;
- **`analyze` ~O(n²)** from materializing the full `ast_star` transitive closure — the wall that stops real
  big modules.
Both are EXACTLY what [[decision-labelless-substrate]] + [[decision-rule-isa]] target: demand-forward
matching (magic-sets + walkers, no full-closure materialization) and dynamic most-constrained-clause
ordering, with the §5 invariant enforced by the opcode set. So the motivation is now concrete and MEASURED,
not just aesthetic. That is the honest case FOR starting.

The case for CAUTION: both decisions are marked "not built, NOT critical path," and the current engine is a
working **behavioral oracle** — reasoning coverage still advances as one-clause rule edits (this session:
alias, two precision fixes). A big-bang rewrite of the matching core risks churning that.

RECOMMENDED ENTRY (de-risked, matches what the decisions already prescribe): do the **"cheap experiment
first"** from [[decision-rule-isa]] — write the opcode-ISA spec + a REFERENCE interpreter and validate it
reproduces `tests/test_contract.py` (and ideally `test_joern_corpus.py` 8/8) with the production engine
untouched. Make the two measured limits the interpreter's first design targets: prove demand-forward
matching kills the `ast_star` O(n²) and that selectivity-ordered seeding removes the clause-order tax. Only
if the reference interpreter cleanly expresses both + passes the oracle do you migrate the production
matcher. Sequencing note: the ISA-with-current-labels interpreter is the tractable first slice; full
label-less re-encoding (attribute bundles, reified relations) is the larger follow-on it was extended to
accommodate. This work lives under the parent `docs/implementation_plan.md` + `docs/graph low level machine/`,
not this arc — but the joern corpus + coverage audit are now part of the oracle it must not regress.

## Open findings / gotchas that WILL bite (read before writing rules)

- **ENGINE — the rule compiler sorts LHS clauses LEXICALLY, not by selectivity.** So the seed for a
  multi-clause rule is the lexically-first pattern, and high-df predicates (`argument`, `ast_star`,
  `is_a`) sort early and seed on huge candidate sets while rare gates (`__iter__`/`__next__`/literals)
  prune too late — a combinatorial blowup (a monolithic 14-clause rule = 25s / hung on a 15-func corpus).
  **Workaround until the engine does dynamic most-constrained-clause ordering: SPLIT a big rule into
  small staged rules that each materialize an intermediate frame and are seeded from a RARE anchor**
  (see `JOERN_RECOGNIZER_RULES` in `cpg.py` — the iteration recognizer split → 1.4s, 18×). This is the
  single most reusable lesson from this session.
- **Shape-B is gated in `cpg.analyze`** on `graph.name_count("__next__")` — it runs ONLY on
  joern-lowered CPGs, because it is not cheaply inert on a FOR-shaped graph. A content-blind structural
  gate (orchestration, not domain logic).
- **The hand-authored fixtures (`tests/fixtures/cpg_*.json`) are schema-faithful but
  LOWERING-UNfaithful** — they assume `for`-as-`FOR`; real Joern lowers to `WHILE`+iterator. They still
  serve `load_cpg` folding + the shape-A path. The real-Joern fixtures are `joern_*_graphson.json`.
- **Two silent-drop findings** (pinned in `test_coverage_audit.py`): the machine-rule body parser
  silently DROPS a clause whose predicate is a reserved provenance name (`uses`/`proves`/`axiom` —
  that's why the frame predicate is `accesses`), and a `proves` node spuriously inherits a derived type
  (exclude `{h.PROVES, h.USES, h.AXIOM}` from any raw hazard scan).

## Pointers

- Memory: [[finding-joern-lowering]], [[finding-cpg-scaling-precision]],
  [[finding-coverage-composition-audit]] (each has the full detail + numbers + next steps).
- Benches: `bench/{coverage_audit,cpg_scaling,joern_corpus}.py` (all run offline from committed
  fixtures). Tests: `tests/test_{coverage_audit,cpg_scaling,cpg_graphson,cpg_adapter,joern_corpus}.py`.
- Engine surfaces touched: `harneskills/cpg.py` (recognizer + `parse_graphson`/`export_cpg`). No engine
  (`rewriter.py`) changes were made — the clause-ordering issue is diagnosed but NOT fixed (deliberate;
  a selectivity-based clause order is a separate, higher-risk engine change).
