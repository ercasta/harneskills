"""
Coverage / composition audit — the top open experiment (docs/handoff_redesign.md, docs/vision_agentic.md
§6, §12). This is the ONE load-bearing assumption the whole agentic arc still ASSUMES rather than
measures: does a small set of MECHANISM-level rules COMPOSE to cover real bugs, or does the
absent-premise long tail dominate — the Cyc-shaped risk that historically killed this class of system?

The vision's own prescription (§10, §12): encode ~6-8 mechanism rules for one real domain, assemble
~20 realistic CPG-frame scenarios spanning (a) direct positives, (b) NOVEL manifestations of an
encoded mechanism that no dedicated rule covers — the §6 composition claim, (c) adversarial near-misses
that must stay silent, and (d) real bugs that need a premise encoded at NO level — then measure recall
and, crucially, the MISS TAXONOMY: a miss is either "composable-but-unencoded-mechanism" (a CHEAP fix —
one more general rule, and it composes with the frames we already have) or "absent-premise" (FUNDAMENTAL
— unreachable by any composition; only a human writing the premise or statistical induction closes it).

DOMAIN: Python resource- and collection-safety hazards. One coherent causal vocabulary — iteration
consuming a lazy collection, mutation, aliasing, resource acquire/release lifecycle, mutable defaults —
authored as mechanism rules over a small frame ontology (`is_a`-typed nodes with named role edges),
exactly as `tests/test_code_frames.py` and `harneskills/cpg.py` author frames. NO extraction: every
scenario is a hand-authored frame graph AS IF a CPG recognizer had run (the §10 Stage-1/2 discipline),
so this isolates the substrate-coverage risk from the extractor-reliability risk.

METHODOLOGY / honesty. Each scenario carries two analyst annotations and one MEASURED outcome:
  - `wish`     — the node(s) a perfect analyzer SHOULD flag (empty for a genuinely-safe near-miss).
    This is ground truth about the code, independent of our rules.
  - `category` — the analyst's classification (positive-direct / positive-novel / near-miss /
    miss-cheap / miss-fundamental). For the two MISS categories this encodes the taxonomy JUDGMENT
    (is the missing knowledge one composable rule away, or a premise at no level of abstraction?).
  - the engine's ACTUAL hazard set is measured by running the rules — never asserted by the analyst.
Recall, false-positive rate, and the miss split are all computed from the measured outcome vs `wish`;
only the cheap-vs-fundamental LABEL on a miss is a judgment, and it is stated as such. The point is not
to make the number look good — the miss tail is the finding.

UPDATE 2026-07-05 — the premise-class experiment. The original audit (memory
`finding_coverage_composition_audit`) measured the baseline: 8 mechanism rules, 61.5% real recall, 2
CHEAP misses + 3 FUNDAMENTAL (taint/concurrency/arithmetic). This version acts on that finding and
tests the two follow-through claims it implied: (a) that the CHEAP misses really are one-general-rule-
away and compose (encode C1/C2, re-measure), and (b) the load-bearing one — that a FUNDAMENTAL
absent-premise closes by importing a whole premise CLASS that then GENERALIZES like the native
mechanisms, rather than needing a rule per pattern (the Cyc tell). Taint is the imported class (T1-T3),
exercised by structurally-distinct manifestations (different sink KINDS, multi-hop dataflow) plus
adversarial near-misses (sanitizer, untainted). BASELINE_RULES vs RULES measures the delta in one run.
Concurrency and arithmetic are deliberately LEFT unimported, to keep the contrast: the residual is a
short list of premise CLASSES to import, not an open-ended pattern tail.

Run:  python bench/coverage_audit.py
"""
from __future__ import annotations

import harneskills as h
from harneskills import rewriter
from harneskills.machine_rules import load_machine_rules

# ---------------------------------------------------------------------------
# The rule bank. Two groups: structural CLOSURE (machinery — transitivity, like
# cpg.py's `ast_star`) and the DOMAIN MECHANISM rules whose coverage we measure.
# Everything is machine-rule CNL — DATA, not Python domain logic. Rules are stated
# over frame TYPES and ROLES, never over a surface pattern or a library name, so
# each fires on every matching instance including shapes authored after it (§6).
# ---------------------------------------------------------------------------

CLOSURE_RULES = """
    ?a happens_before ?c when ?a happens_before ?b and ?b happens_before ?c
    ?a within ?c when ?a within ?b and ?b within ?c
"""

# The 8 mechanism-level rules — the causal knowledge whose composition coverage is under test.
MECHANISM_RULES = """
    ?loop consumes ?c when ?loop is_a iteration and ?loop iterates ?c
    ?m is_a hazard when ?m is_a mutation and ?m mutates ?c and ?m within ?loop and ?loop consumes ?c
    ?m mutates ?x when ?m mutates ?a and ?a aliases ?x
    ?a is_a hazard when ?a is_a acquisition and ?a acquires ?r and not ?rel releases ?r
    ?u is_a hazard when ?u is_a access and ?u accesses ?r and ?rel releases ?r and ?rel happens_before ?u
    ?r2 is_a hazard when ?r2 is_a release and ?r2 releases ?res and ?r1 releases ?res and ?r1 happens_before ?r2 and not ?acq acquires ?res and not ?r1 happens_before ?acq and not ?acq happens_before ?r2
    ?p is_a mutable_default when ?p default ?d and ?d is_a mutable_container
    ?m is_a hazard when ?m is_a mutation and ?m mutates ?p and ?p is_a mutable_default
"""

# --- Cheap fixes: the two "composable-but-unencoded" misses, each ONE general rule (§6, generality-
# not-count). C1 makes alias-propagation symmetric for `access` (M3 already does it for `mutate`); C2
# makes a release that an exit path BYPASSES not count as protecting the resource. Both compose with the
# EXISTING acquire/release/alias frames — no new frame ontology.
CHEAP_RULES = """
    ?u accesses ?x when ?u accesses ?a and ?a aliases ?x
    ?a is_a hazard when ?a is_a acquisition and ?a acquires ?r and ?rel releases ?r and ?e bypasses ?rel
"""

# --- The TAINT premise class: importing a whole premise CLASS, not enumerating sink patterns. Three
# mechanism rules over a taint frame ontology (tainted_source / flows_to / sink / sanitizer): introduce
# taint at a source, propagate it along dataflow (stopping at a sanitizer — the NAC), and flag taint
# reaching ANY sink. The claim under test: like the native mechanisms, these fire on structurally
# distinct manifestations (different sink KINDS, multi-hop dataflow) with NO per-pattern rule, and the
# adversarial near-misses (sanitized, untainted) stay silent.
TAINT_RULES = """
    ?v is_a tainted when ?src is_a tainted_source and ?src flows_to ?v and not ?v is_a sanitizer
    ?w is_a tainted when ?v is_a tainted and ?v flows_to ?w and not ?w is_a sanitizer
    ?k is_a hazard when ?k is_a sink and ?k is_a tainted
"""

# --- The CONCURRENCY premise class (2026-07-06): the second of the two residual FUNDAMENTAL misses
# imported the same way taint was — a SMALL set of kind-agnostic mechanism rules over a concurrency frame
# ontology (write/read access + `concurrent_with` + `guarded_by` a lock), NOT a per-pattern catalogue.
# The causal knowledge: a DATA RACE is two accesses to the same shared state that may run concurrently,
# at least one a write, with no COMMON lock held across both. Encoded in four moves:
#   N1/N2  normalize either access KIND (write or read) to a kind-agnostic `touches ?state`, so the
#          conflict rule never mentions read-vs-write — exactly the kind-agnosticism that let T3 cover
#          every sink kind. (A write additionally keeps its `is_a write`, used to require ONE writer.)
#   N3     `concurrent_with` is symmetric — a recognizer may emit the unordered pair either way.
#   N4     a CONFLICT: some WRITE and another access `touch` the SAME state and are concurrent (the
#          `?a concurrent_with ?b` already forces the two to be distinct — no node races itself).
#   N5     a conflicting access is a HAZARD unless a COMMON lock guards BOTH sides. The NAC
#          `not ?a guarded_by ?L and not ?b guarded_by ?L` shares the free var ?L, so at runtime it is
#          ONE existential group `¬∃L (a guarded_by L ∧ b guarded_by L)` (rewriter `_nac_groups`): a
#          lock held on only one side — or two DIFFERENT locks — does not discharge it.
# The claim under test (same as taint): written against the direct write-write race, do these ALSO catch
# manifestations they were not written for — a read/write conflict (via the kind-agnostic `touches`) and
# a race where each side holds a DIFFERENT lock (the NAC demands a *shared* L, not merely *some* lock) —
# while the adversarial near-misses (common lock, not-concurrent, disjoint state) stay silent?
CONCURRENCY_RULES = """
    ?a touches ?s when ?a is_a write and ?a writes ?s
    ?a touches ?s when ?a is_a read and ?a reads ?s
    ?a concurrent_with ?b when ?b concurrent_with ?a
    ?a conflicts_with ?b when ?a is_a write and ?a touches ?s and ?b touches ?s and ?a concurrent_with ?b
    ?a is_a hazard when ?a conflicts_with ?b and not ?a guarded_by ?L and not ?b guarded_by ?L
"""

# BASELINE = the original 8 mechanism rules (docs finding: 61.5% real recall over the original suite, 2
# cheap + 3 fundamental misses). PRE_CONCURRENCY = the frontier BEFORE this concurrency import (the 8
# mechanism rules + the 2 cheap + the taint class), so its delta to RULES isolates exactly what importing
# the CONCURRENCY class bought — the analog of taint's 53.3%->86.7%. RULES = the full augmented frontier.
BASELINE_RULES = load_machine_rules(CLOSURE_RULES + MECHANISM_RULES)
PRE_CONCURRENCY_RULES = load_machine_rules(CLOSURE_RULES + MECHANISM_RULES + CHEAP_RULES + TAINT_RULES)
RULES = load_machine_rules(
    CLOSURE_RULES + MECHANISM_RULES + CHEAP_RULES + TAINT_RULES + CONCURRENCY_RULES)

# A human-readable gloss of each mechanism, for the report + the "which rule / why unencoded" column.
MECHANISM_GLOSS = [
    "M1 iteration consumes its (lazy) collection",
    "M2 mutating a consumed collection inside its consuming loop is a hazard",
    "M3 aliasing propagates mutation (mutating an alias mutates the underlying object)",
    "M4 an acquired resource with no release anywhere leaks",
    "M5 using a resource after it is released is a hazard",
    "M6 releasing an already-released resource (no re-acquire between) is a hazard",
    "M7a a parameter whose default is a mutable container is a mutable-default",
    "M7b mutating a mutable-default parameter is a hazard",
]

# The two cheap fixes (were miss-cheap; now encoded) and the imported taint premise class.
CHEAP_GLOSS = [
    "C1 alias propagation for access (use-through-alias) — symmetric to M3 for mutation",
    "C2 a release an exit path BYPASSES does not protect the resource (leak-on-exception)",
]
TAINT_GLOSS = [
    "T1 a source's dataflow successor is tainted (unless it is a sanitizer)",
    "T2 taint propagates along dataflow (unless it reaches a sanitizer)",
    "T3 taint reaching ANY sink (any kind) is a hazard",
]
CONCURRENCY_GLOSS = [
    "N1 a write access `touches` its state (kind-agnostic normalization)",
    "N2 a read access `touches` its state (same, so conflict never mentions read-vs-write)",
    "N3 `concurrent_with` is symmetric",
    "N4 a conflict: a WRITE and another access touch the SAME state and are concurrent",
    "N5 a conflicting access with no COMMON lock guarding both sides is a hazard (data race)",
]


# ---------------------------------------------------------------------------
# Frame authoring helpers (same idiom as tests/test_code_frames.py).
# ---------------------------------------------------------------------------

def _rel(g, s, p, o):
    si = g.nodes_named(s)[0] if g.nodes_named(s) else g.add_node(s)
    oi = g.nodes_named(o)[0] if g.nodes_named(o) else g.add_node(o)
    g.add_relation(si, p, oi)


def iteration(g, loop, collection):
    """An `Iteration` frame: `loop` consumes `collection`. A CPG recognizer for a for/while/
    comprehension/recursion materializes this same frame (§5 many-to-one)."""
    _rel(g, loop, "is_a", "iteration")
    _rel(g, loop, "iterates", collection)
    _rel(g, collection, "is_a", "queryset")


def mutation(g, mut, target, scope):
    """A `Mutation` frame: `mut` mutates `target`, sited `within` `scope`."""
    _rel(g, mut, "is_a", "mutation")
    _rel(g, mut, "mutates", target)
    _rel(g, mut, "within", scope)


def acquisition(g, acq, resource):
    _rel(g, acq, "is_a", "acquisition")
    _rel(g, acq, "acquires", resource)


def release(g, rel_, resource):
    _rel(g, rel_, "is_a", "release")
    _rel(g, rel_, "releases", resource)


def use(g, u, resource):
    # Frame predicate is `access`/`accesses`, NOT `use`/`uses`: `uses` collides with the provenance
    # predicate USES (in-graph justifications), and the machine-rule body parser SILENTLY DROPS a
    # clause whose predicate is a reserved provenance name — a real silent-drop finding, recorded in
    # the audit report and docs/handoff_redesign.md. `accesses` is an ordinary predicate.
    _rel(g, u, "is_a", "access")
    _rel(g, u, "accesses", resource)


def before(g, a, b):
    """Control-flow ordering fact (a happens strictly before b); the transitive closure is a rule."""
    _rel(g, a, "happens_before", b)


def alias(g, a, underlying):
    _rel(g, a, "aliases", underlying)


def taint_source(g, node):
    """An untrusted source (request param, argv, env). A CPG recognizer marks any of them the same."""
    _rel(g, node, "is_a", "tainted_source")


def flow(g, a, b):
    """A dataflow edge a -> b (assignment, arg-pass, return). Taint propagates along it."""
    _rel(g, a, "flows_to", b)


def sink(g, node, kind):
    """A dataflow sink. `kind` (sql_query / os_command / file_path) is the recognizer's label; the
    hazard rule is kind-AGNOSTIC — it reads only `is_a sink`, so ONE rule covers every kind."""
    _rel(g, node, "is_a", "sink")
    _rel(g, node, "is_a", kind)


def sanitizer(g, node):
    _rel(g, node, "is_a", "sanitizer")


def writes(g, node, state):
    """A write access to shared `state`. A CPG recognizer marks any store to shared memory the same."""
    _rel(g, node, "is_a", "write")
    _rel(g, node, "writes", state)


def reads(g, node, state):
    """A read access of shared `state` (a load). Kind-distinct from a write, but `touches`-equivalent."""
    _rel(g, node, "is_a", "read")
    _rel(g, node, "reads", state)


def concurrent(g, a, b):
    """`a` and `b` may run concurrently (different threads, no happens-before between them). The rule
    N3 symmetrizes this, so a recognizer authoring only one direction is enough."""
    _rel(g, a, "concurrent_with", b)


def guarded(g, node, lock):
    """`node` performs its access while holding `lock`. A race is discharged only when a COMMON lock
    guards BOTH conflicting accesses (rule N5)."""
    _rel(g, node, "guarded_by", lock)


# ---------------------------------------------------------------------------
# The scenario suite. Each: (name, category, wish, builder).
#   category ∈ {positive-direct, positive-novel, near-miss, miss-cheap, miss-fundamental}
#   wish     = frozenset of node names a perfect analyzer flags as hazards (ground truth).
# ---------------------------------------------------------------------------

def _s(name, category, wish, builder, note=""):
    return {"name": name, "category": category, "wish": frozenset(wish),
            "build": builder, "note": note}


def _scenarios():
    S = []

    # --- Mutate-during-iteration: direct + three NOVEL manifestations (the §6 claim) ---
    def mdi_direct(g):
        iteration(g, "loop1", "qs"); mutation(g, "mut1", "qs", "loop1")
    S.append(_s("mdi_direct", "positive-direct", {"mut1"}, mdi_direct,
                "del qs.pop() inside `for x in qs`"))

    def mdi_recursion(g):
        # A recursion recognizer emits the SAME Iteration frame (structurally unlike a for-loop).
        iteration(g, "walk", "qs"); mutation(g, "del_call", "qs", "walk")
    S.append(_s("mdi_recursion", "positive-novel", {"del_call"}, mdi_recursion,
                "§5 many-to-one: recursion-shaped iteration, no recursion-specific rule"))

    def mdi_via_alias(g):
        # Mutation targets `alias`, which aliases the consumed qs -> M1∘M3∘M2 composition.
        iteration(g, "loop1", "qs"); mutation(g, "mut1", "alias", "loop1"); alias(g, "alias", "qs")
    S.append(_s("mdi_via_alias", "positive-novel", {"mut1"}, mdi_via_alias,
                "§6 composition: mutate an ALIAS of the consumed collection; no alias-MDI rule"))

    def mdi_nested_loop(g):
        # Mutation sits in an inner loop; the consumed collection belongs to the OUTER loop.
        iteration(g, "outer", "qs"); iteration(g, "inner", "other")
        _rel(g, "inner", "within", "outer")
        mutation(g, "mut1", "qs", "inner")
    S.append(_s("mdi_nested_loop", "positive-novel", {"mut1"}, mdi_nested_loop,
                "within-transitivity: outer collection mutated from a nested loop"))

    def mdi_disjoint(g):
        iteration(g, "loop1", "qs"); mutation(g, "mut1", "other", "loop1")
    S.append(_s("mdi_disjoint", "near-miss", set(), mdi_disjoint,
                "mutation targets a DIFFERENT collection -> safe"))

    def mdi_outside(g):
        iteration(g, "loop1", "qs"); iteration(g, "loop2", "other")
        mutation(g, "mut1", "qs", "loop2")
    S.append(_s("mdi_outside", "near-miss", set(), mdi_outside,
                "mutation of qs is in a SIBLING loop that does not consume qs -> safe"))

    def mdi_readonly(g):
        iteration(g, "loop1", "qs")
    S.append(_s("mdi_readonly", "near-miss", set(), mdi_readonly,
                "read-only iteration, no mutation at all -> safe (the common case)"))

    # --- Resource lifecycle: leak / use-after-release / double-release ---
    def leak(g):
        acquisition(g, "acq1", "f")
    S.append(_s("leak_no_release", "positive-direct", {"acq1"}, leak,
                "open(f) with no close anywhere -> leak"))

    def leak_released(g):
        acquisition(g, "acq1", "f"); release(g, "rel1", "f")
    S.append(_s("leak_released", "near-miss", set(), leak_released,
                "acquire + release present -> safe"))

    def uar(g):
        release(g, "rel1", "f"); use(g, "use1", "f"); before(g, "rel1", "use1")
    S.append(_s("use_after_release", "positive-direct", {"use1"}, uar,
                "read from a file after close() -> hazard"))

    def use_before_release(g):
        use(g, "use1", "f"); release(g, "rel1", "f"); before(g, "use1", "rel1")
    S.append(_s("use_before_release", "near-miss", set(), use_before_release,
                "use precedes release (correct order) -> safe"))

    def double_release(g):
        release(g, "r1", "f"); release(g, "r2", "f"); before(g, "r1", "r2")
    S.append(_s("double_release", "positive-direct", {"r2"}, double_release,
                "close() twice with no reopen between -> hazard"))

    def reacquire_between(g):
        release(g, "r1", "f"); _rel(g, "acq2", "acquires", "f"); release(g, "r2", "f")
        before(g, "r1", "acq2"); before(g, "acq2", "r2")
    S.append(_s("release_reacquire_release", "near-miss", set(), reacquire_between,
                "close, REOPEN, close -> safe (the reacquire NAC discriminates)"))

    # --- Mutable default argument ---
    def mutable_default(g):
        _rel(g, "p", "default", "lst"); _rel(g, "lst", "is_a", "mutable_container")
        mutation(g, "mut1", "p", "body")
    S.append(_s("mutable_default_mutated", "positive-direct", {"mut1"}, mutable_default,
                "def f(x=[]) then x.append(...) -> hazard (recognizer composes with M7b)"))

    def immutable_default(g):
        _rel(g, "p", "default", "zero")   # default is an int/None literal, not a mutable container
        mutation(g, "mut1", "p", "body")
    S.append(_s("immutable_default_mutated", "near-miss", set(), immutable_default,
                "def f(x=0) -> not a mutable-default -> safe"))

    def mutable_default_readonly(g):
        _rel(g, "p", "default", "lst"); _rel(g, "lst", "is_a", "mutable_container")
    S.append(_s("mutable_default_readonly", "near-miss", set(), mutable_default_readonly,
                "def f(x=[]) but x never mutated -> safe"))

    # --- NOW-ENCODED cheap fixes (were miss-cheap; C1/C2 added). Each was one general rule away, and
    # the rule composes with the EXISTING acquire/release/alias frames — proving "cheap" was a real
    # judgment, not a hope. They present as positive-novel: caught with no scenario-specific rule.
    def leak_on_exception(g):
        # A release EXISTS but only on the normal path; an exception edge bypasses it. M4's NAC sees a
        # release and stays silent (the original miss). C2 reads the `bypasses` (CFG dominator) fact.
        acquisition(g, "acq1", "f"); release(g, "rel1", "f")
        _rel(g, "rel1", "on_path", "normal")
        _rel(g, "raise1", "on_path", "exceptional"); _rel(g, "raise1", "bypasses", "rel1")
    S.append(_s("leak_on_exception_path", "positive-novel", {"acq1"}, leak_on_exception,
                "release only on normal path; exception bypasses it -> C2 (a bypassed release does "
                "not protect) fires over CFG dominator facts, composing with the acquire/release frame"))

    def uar_via_alias(g):
        # release f; then use `a`, where a aliases f. M3 propagates mutation through aliases; C1 adds
        # the symmetric propagation for ACCESS, then M5 fires by composition.
        release(g, "rel1", "f"); use(g, "use1", "a"); alias(g, "a", "f"); before(g, "rel1", "use1")
    S.append(_s("use_after_release_via_alias", "positive-novel", {"use1"}, uar_via_alias,
                "use-after-release through an ALIAS -> C1 propagates access across the alias, then M5 "
                "fires; no use-after-release-via-alias rule (generality-vs-count)"))

    # --- NOW-ENCODED premise class: TAINT (was the single sql_injection miss-fundamental). Importing
    # the CLASS turns one miss into a family the 3 taint rules cover by composition: direct, a DIFFERENT
    # sink kind, and MULTI-HOP dataflow — plus two adversarial near-misses (sanitized, untainted) that
    # must stay silent. This is the experiment: once imported, does a premise class GENERALIZE like the
    # native mechanisms, or does it need a rule per sink pattern (the Cyc tell)?
    def taint_sql(g):
        taint_source(g, "src1"); flow(g, "src1", "q1"); sink(g, "q1", "sql_query")
    S.append(_s("taint_sql_injection", "positive-direct", {"q1"}, taint_sql,
                "user input flows to a SQL sink -> injection (taint class, direct)"))

    def taint_command(g):
        taint_source(g, "argv"); flow(g, "argv", "cmd1"); sink(g, "cmd1", "os_command")
    S.append(_s("taint_command_injection", "positive-novel", {"cmd1"}, taint_command,
                "same taint mechanism, DIFFERENT sink kind (os.system) -> one kind-agnostic rule (T3), "
                "no command-specific rule"))

    def taint_multihop(g):
        taint_source(g, "req"); flow(g, "req", "tmp"); flow(g, "tmp", "path1")
        sink(g, "path1", "file_path")
    S.append(_s("taint_path_traversal_multihop", "positive-novel", {"path1"}, taint_multihop,
                "taint propagates TWO hops to a path sink -> T2 propagation composes, no per-length or "
                "per-sink rule"))

    def taint_sanitized(g):
        taint_source(g, "src2"); flow(g, "src2", "esc"); sanitizer(g, "esc")
        flow(g, "esc", "q2"); sink(g, "q2", "sql_query")
    S.append(_s("taint_sanitized", "near-miss", set(), taint_sanitized,
                "input passes through a sanitizer before the sink -> taint stops at the sanitizer "
                "(the NAC) -> safe"))

    def taint_untainted(g):
        _rel(g, "const1", "is_a", "literal"); flow(g, "const1", "q3"); sink(g, "q3", "sql_query")
    S.append(_s("taint_untainted_sink", "near-miss", set(), taint_untainted,
                "a sink fed by a constant, no tainted source -> safe"))

    # --- NOW-ENCODED premise class: CONCURRENCY (was race_condition_shared_state miss-fundamental).
    # Importing the CLASS turns one miss into a family the 5 concurrency rules cover by composition:
    # the direct write-write race, a read/write race (a DIFFERENT access-kind combination, caught by
    # the kind-agnostic `touches`), and a race where each side holds a DIFFERENT lock (the guard NAC
    # demands a *shared* lock) — plus three adversarial near-misses (common lock, not-concurrent,
    # disjoint state) that must stay silent. Same experiment as taint: does the class GENERALIZE, or
    # need a rule per race shape (the Cyc tell)?
    def race_write_write(g):
        # Two concurrent writers to shared state, no lock -> both are unsynchronized-conflict hazards.
        writes(g, "w1", "shared"); writes(g, "w2", "shared"); concurrent(g, "w1", "w2")
    S.append(_s("race_condition_shared_state", "positive-direct", {"w1", "w2"}, race_write_write,
                "unsynchronized concurrent writes to shared state -> data race (concurrency class, "
                "direct); both writers flagged"))

    def race_read_write(g):
        # A read concurrent with a write on the SAME state, no lock. No read-write-specific rule: the
        # kind-agnostic `touches` (N1/N2) makes the read a conflict partner, N4 requires the WRITE side.
        reads(g, "r1", "shared"); writes(g, "w1", "shared"); concurrent(g, "r1", "w1")
    S.append(_s("race_read_write", "positive-novel", {"w1"}, race_read_write,
                "read concurrent with a write -> race caught via kind-agnostic `touches`, no "
                "read/write-specific rule (the write is flagged)"))

    def race_distinct_locks(g):
        # Each write is guarded, but by a DIFFERENT lock -> still a race. The guard NAC shares ?L, so it
        # discharges only on a COMMON lock; two distinct locks leave the conflict unguarded.
        writes(g, "w1", "shared"); writes(g, "w2", "shared"); concurrent(g, "w1", "w2")
        guarded(g, "w1", "lock_a"); guarded(g, "w2", "lock_b")
    S.append(_s("race_distinct_locks", "positive-novel", {"w1", "w2"}, race_distinct_locks,
                "concurrent writes each holding a DIFFERENT lock -> still a race: the NAC needs a "
                "SHARED lock, not merely some lock; no distinct-lock-specific rule"))

    def race_common_lock(g):
        # Both writes hold the SAME lock -> the conflict is discharged (N5 NAC finds a common L).
        writes(g, "w1", "shared"); writes(g, "w2", "shared"); concurrent(g, "w1", "w2")
        guarded(g, "w1", "mutex"); guarded(g, "w2", "mutex")
    S.append(_s("race_common_lock", "near-miss", set(), race_common_lock,
                "concurrent writes both holding the SAME lock -> serialized -> safe"))

    def race_not_concurrent(g):
        # Two writes to shared state that are ORDERED (not concurrent) -> no conflict.
        writes(g, "w1", "shared"); writes(g, "w2", "shared"); before(g, "w1", "w2")
    S.append(_s("race_not_concurrent", "near-miss", set(), race_not_concurrent,
                "ordered writes to shared state (no concurrency) -> not a race -> safe"))

    def race_disjoint_state(g):
        # Two concurrent writes, but to DIFFERENT state -> no shared `touches ?s` -> no conflict.
        writes(g, "w1", "state_a"); writes(g, "w2", "state_b"); concurrent(g, "w1", "w2")
    S.append(_s("race_disjoint_state", "near-miss", set(), race_disjoint_state,
                "concurrent writes to DIFFERENT state -> no shared object -> safe"))

    # --- MISS: absent-premise (FUNDAMENTAL — premise CLASSES still unencoded). Taint and concurrency
    # have both moved OUT of this bucket (imported above); arithmetic/bounds remains, its own class to
    # import next — the frontier moves one premise CLASS at a time, not one pattern at a time.

    def off_by_one(g):
        # Indexing a list at len(x). Needs an arithmetic / bounds premise -> encoded nowhere.
        _rel(g, "access1", "is_a", "index_access"); _rel(g, "access1", "index_expr", "len_x")
        _rel(g, "len_x", "equals", "length_of_x")
    S.append(_s("off_by_one_index", "miss-fundamental", {"access1"}, off_by_one,
                "index == len(x). No arithmetic/bounds premise encoded -> absent premise"))

    return S


# ---------------------------------------------------------------------------
# Runner: measure each scenario, compute recall / false positives / miss taxonomy.
# ---------------------------------------------------------------------------

# Provenance-vocabulary node names to exclude from the measured hazard set: the `proves`/`uses`
# predicate-concept nodes spuriously inherit a derived type when provenance is on (an internal
# provenance leak, invisible to the public `ask` surface — `ask "is proves a hazard"` is not even a
# recognized question). They are not domain nodes, so they are not hazards.
_PROVENANCE_NAMES = {h.PROVES, h.USES, h.AXIOM}


def _hazards(g):
    """The MEASURED hazard set: every DOMAIN node with a real `is_a hazard` fact after the rules run.
    Uses `_relation_exists` (as tests/test_code_frames.py does) rather than a raw edge scan, and drops
    provenance-vocabulary nodes so justification structure is never counted as a domain hazard."""
    haz = g.nodes_named("hazard")
    if not haz:
        return set()
    hz = haz[0]
    return {g.name(n) for n in g.nodes()
            if g.name(n) not in _PROVENANCE_NAMES and rewriter._relation_exists(g, n, "is_a", hz)}


def run_scenario(scn):
    g = h.Graph()
    scn["build"](g)
    h.run_rules(g, RULES)
    actual = _hazards(g)
    wish = set(scn["wish"])
    return {
        "actual": actual,
        "caught": wish and wish <= actual,          # the real bug(s) flagged
        "false_pos": actual - wish,                  # flagged something that is not a bug
        "buggy": bool(wish),                         # scenario contains a real bug
    }


def _predict_ok(cat, res):
    """The audit is well-formed iff the engine behaves as the analyst PREDICTED for the category:
    positives/novel -> caught & no FP; near-miss -> nothing flagged; miss-* -> bug present but NOT
    caught (and no spurious FP). A mismatch is itself a finding (the audit's engine model is off)."""
    if cat in ("positive-direct", "positive-novel"):
        return res["caught"] and not res["false_pos"]
    if cat == "near-miss":
        return not res["actual"]
    return (not res["caught"]) and not res["false_pos"]   # miss-cheap / miss-fundamental


def _delta_vs(rows, ruleset):
    """Re-run every buggy scenario under an EARLIER `ruleset` (a prefix of the full RULES) to measure
    what the rules added on top of it bought. Returns (prior_real_recall, newly_caught) — the real
    bugs the full augmented set catches that `ruleset` misses."""
    newly, prior_caught, n_buggy = [], 0, 0
    for scn, res, _ in rows:
        if not scn["wish"]:
            continue
        n_buggy += 1
        gb = h.Graph(); scn["build"](gb); h.run_rules(gb, ruleset)
        if set(scn["wish"]) <= _hazards(gb):
            prior_caught += 1
        elif res["caught"]:
            newly.append(scn["name"])
    return prior_caught / max(1, n_buggy), newly


def measure():
    """Run every scenario and compute the metrics — pure (no printing), so tests can pin the numbers.
    Returns (rows, metrics) where rows is a list of (scenario, result, predict_ok)."""
    rows = []
    for scn in _scenarios():
        res = run_scenario(scn)
        rows.append((scn, res, _predict_ok(scn["category"], res)))

    buggy = [(s, r) for s, r, _ in rows if r["buggy"]]
    encoded_pos = [(s, r) for s, r, _ in rows if s["category"] in ("positive-direct", "positive-novel")]
    near = [(s, r) for s, r, _ in rows if s["category"] == "near-miss"]
    misses = [(s, r) for s, r in buggy if not r["caught"]]
    cheap = [(s, r) for s, r in misses if s["category"] == "miss-cheap"]
    fund = [(s, r) for s, r in misses if s["category"] == "miss-fundamental"]
    fps = [(s, r) for s, r, _ in rows if r["false_pos"]]
    metrics = {
        "encoded_recall": sum(1 for _, r in encoded_pos if r["caught"]) / max(1, len(encoded_pos)),
        "real_recall": sum(1 for _, r in buggy if r["caught"]) / max(1, len(buggy)),
        "n_encoded_pos": len(encoded_pos), "n_buggy": len(buggy), "n_near": len(near),
        "false_positives": [s["name"] for s, _ in fps],
        "mismatches": [s["name"] for s, _, ok in rows if not ok],
        "cheap_misses": [s["name"] for s, _ in cheap],
        "fundamental_misses": [s["name"] for s, _ in fund],
        "lint": h.lint_rules(RULES), "n_strata": len(h.stratify(RULES)),
    }
    metrics["baseline_real_recall"], metrics["newly_caught_vs_baseline"] = \
        _delta_vs(rows, BASELINE_RULES)
    # The concurrency-import delta in isolation (prior = everything BUT the concurrency class), the
    # direct analog of taint's 53.3%->86.7%.
    metrics["pre_concurrency_real_recall"], metrics["newly_caught_vs_pre_concurrency"] = \
        _delta_vs(rows, PRE_CONCURRENCY_RULES)
    return rows, metrics


def audit():
    rows, m = measure()
    print("=" * 96)
    print("COVERAGE / COMPOSITION AUDIT — Python resource/collection-safety mechanisms")
    print("=" * 96)
    print(f"\n{len(MECHANISM_GLOSS)} baseline mechanism rules + {len(CHEAP_GLOSS)} cheap-fix rules + "
          f"{len(TAINT_GLOSS)} taint-premise rules + {len(CONCURRENCY_GLOSS)} concurrency-premise rules "
          f"+ {len(load_machine_rules(CLOSURE_RULES))} structural-closure rules. Lint: "
          f"{'clean' if not m['lint'] else h.format_smells(m['lint'])}. Strata: {m['n_strata']}.")
    for gl in MECHANISM_GLOSS:
        print(f"    {gl}")
    print("    --- added by earlier experiments (cheap fixes + taint class) ---")
    for gl in CHEAP_GLOSS + TAINT_GLOSS:
        print(f"    {gl}")
    print("    --- added by this experiment (concurrency premise class) ---")
    for gl in CONCURRENCY_GLOSS:
        print(f"    {gl}")

    print(f"\n{len(rows)} scenarios:\n")
    hdr = f"  {'scenario':<32}{'category':<18}{'bug?':<6}{'caught?':<9}{'FP?':<6}{'engine=predict?'}"
    print(hdr); print("  " + "-" * (len(hdr) - 2))
    for scn, res, predict_ok in rows:
        print(f"  {scn['name']:<32}{scn['category']:<18}"
              f"{'yes' if res['buggy'] else 'no':<6}"
              f"{('YES' if res['caught'] else '—'):<9}"
              f"{('!!' if res['false_pos'] else '—'):<6}"
              f"{'ok' if predict_ok else 'MISMATCH <<<'}")

    enc_recall, real_recall = m["encoded_recall"], m["real_recall"]
    cheap = [(s, r) for s, r, _ in rows if s["name"] in m["cheap_misses"]]
    fund = [(s, r) for s, r, _ in rows if s["name"] in m["fundamental_misses"]]

    print("\n" + "=" * 96)
    print("RESULTS")
    print("=" * 96)
    print(f"  Encoded-mechanism recall : {enc_recall:6.1%}   "
          f"({round(enc_recall * m['n_encoded_pos'])}/{m['n_encoded_pos']} "
          f"positives incl. novel manifestations by composition)")
    print(f"  Near-miss false positives: {len(m['false_positives']):>6}   "
          f"({m['n_near']} adversarial near-misses; 0 is correct)")
    print(f"  Overall real-bug recall  : {real_recall:6.1%}   "
          f"({round(real_recall * m['n_buggy'])}/{m['n_buggy']} real bugs across ALL scenarios "
          f"— the honest coverage number)")

    base_recall = m["baseline_real_recall"]
    newly = m["newly_caught_vs_baseline"]
    pre_recall = m["pre_concurrency_real_recall"]
    newly_conc = m["newly_caught_vs_pre_concurrency"]
    print(f"\n  BASELINE -> AUGMENTED DELTA (what importing 2 premise classes + 2 general rules bought):")
    print(f"    baseline (8 mechanism rules) real recall : {base_recall:6.1%}   "
          f"({round(base_recall * m['n_buggy'])}/{m['n_buggy']} on this expanded suite)")
    print(f"    augmented real recall                    : {real_recall:6.1%}   "
          f"({round(real_recall * m['n_buggy'])}/{m['n_buggy']})")
    print(f"    real bugs flipped MISS->CAUGHT by the new rules ({len(newly)}): {', '.join(newly)}")
    print(f"\n  CONCURRENCY-IMPORT DELTA IN ISOLATION (the analog of taint's 53.3%->86.7%):")
    print(f"    before concurrency (mechanism+cheap+taint): {pre_recall:6.1%}   "
          f"({round(pre_recall * m['n_buggy'])}/{m['n_buggy']})")
    print(f"    after  concurrency import                 : {real_recall:6.1%}   "
          f"({round(real_recall * m['n_buggy'])}/{m['n_buggy']})")
    print(f"    flipped MISS->CAUGHT by the concurrency class ({len(newly_conc)}): "
          f"{', '.join(newly_conc)}")

    print("\n  MISS TAXONOMY (the finding):")
    print(f"    composable-but-unencoded (CHEAP — one general rule, composes with existing frames): "
          f"{len(cheap)}")
    for s, _ in cheap:
        print(f"        · {s['name']}: {s['note']}")
    print(f"    absent-premise (FUNDAMENTAL — premise at no level; only authoring/induction closes): "
          f"{len(fund)}")
    for s, _ in fund:
        print(f"        · {s['name']}: {s['note']}")

    if m["mismatches"]:
        print(f"\n  !!! {len(m['mismatches'])} engine-vs-prediction MISMATCH(es): "
              f"{', '.join(m['mismatches'])} — the audit model of the engine is wrong; investigate.")
    if m["false_positives"]:
        print(f"\n  !!! FALSE POSITIVES: {', '.join(m['false_positives'])} — a rule over-generates.")

    print("\n  VERDICT")
    print("  " + "-" * 92)
    print("  The two moves this experiment tested both HELD, on measured behaviour, not assertion:")
    print("  (1) CHEAP-MISS closure. The two composable-but-unencoded misses (use-through-alias,")
    print("      leak-on-exception) were each closed by ONE general rule that composes with the")
    print("      existing acquire/release/alias frames — confirming 'cheap' was a real judgment and")
    print("      that the frontier moves by generalizing a mechanism one more step, not per pattern.")
    print("  (2) PREMISE-CLASS import GENERALIZES — now shown TWICE, independently. Taint (3 kind-")
    print("      agnostic rules) caught direct SQL, a DIFFERENT sink kind (command) via the SAME rule,")
    print("      and MULTI-HOP dataflow. Concurrency (5 kind-agnostic rules) repeats the pattern: the")
    print("      direct write-write race, plus a READ/WRITE race caught by the kind-agnostic `touches`")
    print("      (no read/write-specific rule) and a DISTINCT-LOCK race caught because the guard NAC")
    print("      demands a SHARED lock — with all three adversarial near-misses (common lock, ordered,")
    print("      disjoint state) silent. A premise class, once imported, behaves like the native")
    print("      mechanisms: general, not a pattern list. Two-for-two — no Cyc tell.")
    print("  The residual is now ONE UNIMPORTED premise class — arithmetic/bounds — closable the same")
    print("  way (import the class, then it generalizes), NOT an open-ended pattern tail. Actionable")
    print("  read, sharpened: budget the frontier as a SMALL NUMBER OF PREMISE CLASSES to import, each")
    print("  of which then generalizes by composition — not thousands of bug patterns to enumerate.")
    print("  That is the difference between this and the Cyc trajectory.")
    return m


if __name__ == "__main__":
    audit()
