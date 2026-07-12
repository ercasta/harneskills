"""
The planning loop — goal -> plan -> act -> replan, entirely as rules (vision §4-§6).

There is NO smart planner. "Planning" is the fixpoint of a rule bank rewriting the
graph (vision §6: the scheduler only fires enabled rules). The full design — including
the alternatives that were rejected — is in `docs/planning_design.md`; this is its
first implementation slice. Read that doc first.

The computation rides the two-layer split (vision §5):
  - the MONOTONE FACT layer holds domain causal knowledge (operators) and observed
    world state (`<now> --true--> C`);
  - the NON-MONOTONE CONTROL layer holds the planning scaffolding (needs, candidates,
    reachability, blocks, viability, the chosen plan, the execution cursor) which is
    freely built up and — on divergence — torn down. Replanning *is* tearing down the
    control layer and letting the same rules re-fire from the new state.

Vocabulary (all nodes + relations, nothing typed — see the design doc's table):
  condition C            a node, e.g. `have_coffee`
  current state          `<now> --true--> C`                       (fact, observed)
  operator O             `O --pre--> C`, `O --add--> C`            (fact, authored)
  goal                   `<goal> --want--> C0`                      (seed)
  need / subgoal         `<need> --for--> C`                        (control)
  reachable              `C --reachable--> <yes>`                   (control)
  block                  `O --blocked_by--> C`  (an unmet precondition)   (control)
  viable                 `O --viable--> <yes>`                      (control)
  chosen step            `O --chosen--> <yes>`; ordering `O1 --before--> O2`  (control)
  unmet (at exec time)   `O --unmet--> C`                           (control)
  execution cursor       `<exec> --ready--> O`, `O --done--> <yes>`  (control)
  replan trigger         `<replan> --active--> <yes>`               (control)

A marker like "viable" is its OWN relation predicate (`O --viable--> <yes>`) rather
than `O --is--> viable`. This is deliberate: `stratify` (vision §11) is predicate-NAME
granular, so overloading one `is` predicate across reachable/viable/chosen would make
the stratifier unable to tell them apart and see a false negation cycle. Distinct
predicates keep the strata clean (`block`<`viable`); `<yes>` is a shared truth sink.

WHY A FIXPOINT LOOP, NOT A SINGLE STRATIFIED PASS. Reachability grows: a viable
operator's effects (`reach_effect`) make new conditions reachable, which unblock more
operators, which become viable, and so on. That is negation through a cycle
(`reachable` is NAC'd by `block`, whose `blocked_by` is NAC'd by `viable`, which feeds
`reach_effect` back into `reachable`) — not classically stratifiable in one pass. The
`block`/`unblock` retraction idiom computes the least fixpoint: `plan()` re-runs the
(stratified) bank until the graph stops changing. Stratification within a pass only
prevents the within-step NAC race (a premature `viable` firing before `block` has
established its blocks — which, being monotone, would never be retracted and would
poison `reach_effect`). The outer loop does the real semi-naive iteration.

RANKED COMMITMENT among several viable operators is DONE (see the commitment rules (corpus/planning.cnl) +
`rank_by_cost`): when >1 viable op produces one need, the cheaper (by the fact-layer
`cost` criterion) is chosen and the costlier is `dominated`. The hard comparison is a
§8 tool that emits `cheaper_than` FACTS; the rules only select over them — the standing
guardrail (criterion in facts, gadget enacts). Equal costs stay an honest tie (both
commit) rather than a fabricated pick.

KNOWN LIMITATIONS of this slice (none affect the demonstrated domain):
  - Replan is FULL teardown (design decision #4); partial repair (keep the valid plan
    prefix) is the deferred optimization (alt-5).
  - Re-planning re-derives already-satisfied subgoals (re-executed as idempotent no-ops).
  - The shared hub/sink nodes (`<now>`, `<need>`, `<exec>`, `<yes>`) are high-degree, so
    they weaken the locality bound (`within` from the frontier reaches the whole hub).
    Fine at this scale; a larger domain would want hub-aware locality.
"""
from __future__ import annotations

import pathlib

from ugm import external as ext               # request tokens + dispatcher + freshness (§8)
from ugm.cnl.authoring import run_rules            # stratified forward chaining (vision §11)
from ugm.cnl.machine_rules import load_machine_rules   # the rule banks are all authored in CNL
from ugm.production_rule import Rule
from ugm.world_model import Graph

PRICE = "price"                             # the external-lookup kind (result nodes named "price")


# ---------------------------------------------------------------------------
# Seeding — author a problem instance (operators, state, goal) as graph data
# ---------------------------------------------------------------------------

def _hub(graph: Graph, name: str) -> str:
    """The single node labelled `name` (reused), creating it if absent.

    Used for the control/keyword hubs (`<now>`, `<goal>`, `<exec>`) and for the
    shared condition nodes, so a condition mentioned by several operators is ONE node
    (planning joins on it). There is no name index (vision §1); this is a deliberate
    get-or-create over `nodes_named`, the matching helper.
    """
    existing = graph.nodes_named(name)
    return existing[0] if existing else graph.add_node(name)


def seed_operator(graph: Graph, name: str, *, pre=(), add=(), delete=(), cost=None,
                  priced=False) -> str:
    """Author one operator (domain causal knowledge — a monotone fact).

    `O --pre--> C` / `O --add--> C` / `O --del--> C`. Conditions are shared nodes.

    `cost` (optional) authors the selection CRITERION as a fact: `O --cost--> "n"`,
    where the datum is an OPAQUE node NAMED by the cost string (vision §1: nodes carry
    no values; "3" is just a label the rule layer never reads as a number). The
    `rank_by_cost` TOOL parses these opaque names and emits the `cheaper_than` ordering
    that commitment selects on. Operators with no cost simply have no ordering between
    them (an honest tie — see the commitment rules (corpus/planning.cnl)).

    `priced=True` marks the operator's cost as coming from an EXTERNAL source rather than
    the KB (`O --needs_price--> <yes>`): commitment will demand a lookup for it (see
    `REQUEST_RULES`) and wait until the price is fetched before ranking it. Use this
    instead of `cost=` when the cost lives outside the substrate (a price DB / web call).
    """
    o = _hub(graph, name)
    for c in pre:
        graph.add_relation(o, "pre", _hub(graph, c))
    for c in add:
        graph.add_relation(o, "add", _hub(graph, c))
    for c in delete:
        graph.add_relation(o, "del", _hub(graph, c))
    if cost is not None:
        graph.add_relation(o, "cost", _hub(graph, str(cost)))
    if priced:
        graph.add_relation(o, "needs_price", _hub(graph, "<yes>"))
    return o


def seed_state(graph: Graph, conditions=()) -> str:
    """Assert the observed current state: `<now> --true--> C` for each condition."""
    now = _hub(graph, "<now>")
    have = {graph.name(o) for r, o in graph.relations_from(now) if graph.name(r) == "true"}
    for c in conditions:
        if c not in have:
            graph.add_relation(now, "true", _hub(graph, c))
    return now


def seed_goal(graph: Graph, condition: str) -> str:
    """Seed a goal: `<goal> --want--> C`."""
    goal = _hub(graph, "<goal>")
    graph.add_relation(goal, "want", _hub(graph, condition))
    return goal


# ---------------------------------------------------------------------------
# The rule bank — five phases (vision §6: every rule is local fire-when-enabled)
# ---------------------------------------------------------------------------
#
# Positive-fact dedup is automatic: the engine never creates a duplicate of an
# existing plain-literal relation (rewriter `_relation_exists`), so a NAC is needed
# ONLY for genuine negation (an unmet precondition, the absence of a block, no op yet
# chosen). Using a NAC for mere dedup would also create false negation cycles in
# `stratify` (e.g. two rules both producing AND NAC-ing `<need> --for-->`).

# ---- The planner rules (relevance + connection + commitment) — AUTHORED IN CNL -----
# Formerly three Python `Rule` banks; now `corpus/planning.cnl`, loaded via the machine rule
# grammar (machine_rules.py). The block/unblock idiom for "all preconditions met", the
# cost_settled gating of commitment, and the ranked-commitment guardrail are explained in the
# module docstring + docs/planning_design.md, and condensed inline in the .cnl. No Python rule
# literals — the live planner is CNL.

_CORPUS = pathlib.Path(__file__).resolve().parent.parent / "corpus"
_CNL_CACHE: dict[str, list[Rule]] = {}


def _load_cnl(name: str) -> list[Rule]:
    """Load (and cache) a planning rule bank from `corpus/<name>` via the machine grammar.
    ALL of planning's RULES are now CNL; only the §8 tools (`rank_by_cost`, `price_handler`,
    `act`), the seeding helpers, and the fixpoint drivers stay Python (tools and drivers, not
    domain rules)."""
    if name not in _CNL_CACHE:
        _CNL_CACHE[name] = load_machine_rules((_CORPUS / name).read_text(encoding="utf-8"))
    return _CNL_CACHE[name]


def load_planning_rules() -> list[Rule]:
    """The planner bank — relevance + connection + commitment — from `corpus/planning.cnl`."""
    return _load_cnl("planning.cnl")


# Phase C': external cost lookup — rules DRIVE the tool (corpus/planning_requests.cnl). Added
# to the bank only when a lookup registry is supplied (`plan(registry=...)`); a viable op that
# needs a price emits a materialized `<call>` the engine's dispatcher fulfils.
REQUEST_RULES: list[Rule] = _load_cnl("planning_requests.cnl")

# Phase D: acting — readiness as token-passing (corpus/planning_execution.cnl).
EXECUTION_RULES: list[Rule] = _load_cnl("planning_execution.cnl")

# Phase E: divergence -> replan (corpus/planning_detect.cnl + planning_teardown.cnl). Detect
# fires when an operator ran but its effect never materialized; teardown then drops ALL control
# scaffolding (gated on `<replan>`) so the same rules re-fire from the new reality. No special
# replanner — observing a divergence and clearing control automatically re-runs A->D.
DETECT_DIVERGENCE: Rule = _load_cnl("planning_detect.cnl")[0]
TEARDOWN_RULES: list[Rule] = _load_cnl("planning_teardown.cnl")

# The planner = relevance + connection + commitment (corpus/planning.cnl), run to a fixpoint.
PLANNING_RULES: list[Rule] = load_planning_rules()
# The full goal->plan->act->replan derivation bank (everything but the act tool).
SOLVE_RULES: list[Rule] = PLANNING_RULES + EXECUTION_RULES + [DETECT_DIVERGENCE]


# ---------------------------------------------------------------------------
# The driver — loop the (stratified) bank until the graph stops changing
# ---------------------------------------------------------------------------

def _is_prov(name: str) -> bool:
    return name in ("proves", "uses") or name.startswith("<j:") or name in ("<axiom>", "<quarantine>")


def _fingerprint(graph: Graph) -> frozenset[tuple[str, str]]:
    """The graph's DOMAIN edge set — a cheap, exact fixpoint witness (creates add edges,
    control retractions remove them; identical edge sets => nothing more to derive).

    Provenance edges (the in-graph justifications `proves`/`uses`/`<j:...>`, see
    provenance.py) are EXCLUDED: they accrete on every firing, so counting them would
    keep the fingerprint changing forever and the fixpoint loop would never settle.
    They are inert to reasoning, so the domain edge set is the true witness."""
    return frozenset((a, b) for a, b in graph.edges()
                     if not _is_prov(graph.name(a)) and not _is_prov(graph.name(b)))


def _has_rel(graph: Graph, subj: str, rel: str, obj_name: str) -> bool:
    return any(graph.name(r) == rel and graph.name(o) == obj_name
              for r, o in graph.relations_from(subj))


def _control_relation(graph: Graph, subj: str, rel: str, obj: str) -> str:
    """Add `subj -[rel]-> obj` from a §8 tool and stamp the rel node CONTROL when it targets a
    control token (`<...>`). A control MARKER a tool mints (`done <yes>`, `ranked <yes>`,
    `price_known <yes>`) must tear down via `DROP_CTRL` exactly like a rule-minted marker — but a
    tool writes via `add_relation` (a fact rel node), which `DROP_CTRL` would then refuse. Stamping
    the rel node control gives the ISA teardown its teeth. Content-blind: it reads the reserved
    `<...>` syntax (the same criterion as `lowering._is_control_token`/`_rule_touches_control`),
    NEVER a predicate list — a fact a tool writes (`cheaper_than`, a price result) points at a
    domain node and stays a fact. (Under the rewriter teardown, which deletes regardless of the
    fact/control distinction, the stamp is harmless.)"""
    rid = graph.add_relation(subj, rel, obj)
    on = graph.name(obj)
    if on.startswith("<") and on.endswith(">"):
        graph.set_control(rid, True)
    return rid


def _drop_rel(graph: Graph, subj: str, rel: str, obj_name: str) -> None:
    for r, o in graph.relations_from(subj):
        if graph.name(r) == rel and graph.name(o) == obj_name:
            graph.remove_node(r)
            return


def _operator_costs(graph: Graph) -> list[tuple[str, float]]:
    """(operator, cost) from BOTH cost sources, parsing the opaque cost names to floats:
      - authored static facts `O --cost--> "n"` (the in-KB `cost=` path), and
      - CURRENT external `price` result nodes (the on-demand lookup path) — superseded
        results are skipped (the §5 guarded read: "current" = nothing supersedes it).
    """
    costed: list[tuple[str, float]] = []
    for n in graph.nodes():
        for r, c in graph.relations_from(n):
            if graph.name(r) == "cost":
                try:
                    costed.append((n, float(graph.name(c))))
                except ValueError:
                    pass                                  # non-numeric cost: skip silently
    for rnode in graph.nodes_named(PRICE):                # external price results
        if ext.is_superseded(graph, rnode):
            continue
        ofs = [o for rr, o in graph.relations_from(rnode) if graph.name(rr) == ext.OF]
        val = ext.result_value(graph, rnode)
        if ofs and val is not None:
            try:
                costed.append((ofs[0], float(val)))
            except ValueError:
                pass                                      # e.g. an error sentinel: skip
    return costed


def rank_by_cost(graph: Graph) -> None:
    """TOOL (§8): compare operator costs and emit `cheaper_than` FACTS to select on.

    The rule layer cannot compare two opaque cost names — comparison is precisely a
    calculator's job (§8). This tool reads costs (`_operator_costs`, from authored facts
    AND/OR current external `price` results), parses them to floats, and emits the
    comparison *result* as a FACT `O1 --cheaper_than--> O2` for every strictly-cheaper
    pair. Commitment (the commitment rules (corpus/planning.cnl)) then SELECTS over these facts structurally —
    the criterion lives in the fact layer, the rules only enact it (the standing
    guardrail). In general the comparison can be arbitrarily complex (scores, weights,
    lexicographic keys); whatever it is, it stays inside the tool and surfaces only as
    relational results the rules pick over.

    Add-only / idempotent (skips existing relations) so re-running each `plan()` cycle is
    stable. When an external price CHANGES, the lookup handler invalidates the now-stale
    `cheaper_than` incident to that operator (`_invalidate_cheaper_than`), so this tool
    re-derives the correct comparison from the current prices — `cheaper_than` is the
    comparator's maintained output, kept consistent with current cost knowledge.
    """
    costed = _operator_costs(graph)
    for o1, c1 in costed:
        for o2, c2 in costed:
            if c1 < c2 and not _has_rel(graph, o1, "cheaper_than", graph.name(o2)):
                graph.add_relation(o1, "cheaper_than", o2)


def rank_handler(graph: Graph, call_id: str) -> set[str]:
    """TOOL (§8) — the request-driven wrapper around `rank_by_cost`.

    A commitment rule materializes `<call> --tool--> rank --arg--> O` once `O`'s cost is
    settled (see corpus/planning.cnl); the engine's dispatcher routes the call here. The
    tool runs the GLOBAL `rank_by_cost` (which re-derives all `cheaper_than` from current
    costs — idempotent, so several ops' rank calls in one sweep just re-run it harmlessly)
    and marks the requesting op `?o --ranked--> <yes>` so the request rule fires once per op
    (the dedup marker — produced by this TOOL, never a rule, so `stratify` sees no cycle).

    This is the fold of the formerly-explicit per-cycle `rank_by_cost` step onto the engine's
    `run(tools=)` dispatch: gating the request on `cost_settled` orders RANK after the price
    FETCH (so `cheaper_than` is derived from fetched prices, never before they arrive), which
    is what the old explicit FETCH->RANK->COMMIT cycle enforced by hand."""
    rank_by_cost(graph)
    arg = ext.call_arg(graph, call_id, ext.ARG)
    if arg is None:
        return set()
    yes = _hub(graph, "<yes>")
    if not _has_rel(graph, arg, "ranked", "<yes>"):
        _control_relation(graph, arg, "ranked", yes)
    return {arg, yes}


def _invalidate_cheaper_than(graph: Graph, op: str) -> None:
    """Drop every `cheaper_than` relation incident to `op` (in either direction), and the
    op's `ranked` marker so it re-ranks.

    Called when a superseding price arrives for `op`: the prior comparison may now be
    wrong, so the comparator's stale output is invalidated and re-derived next cycle from
    the current price (the rank request re-fires once `ranked` is cleared). This is cache
    invalidation at the §8 tool boundary when source knowledge changes — not a reasoning
    rule deleting a fact (vision §5)."""
    for r, _ in list(graph.relations_from(op)):           # op --cheaper_than--> X / --ranked--> <yes>
        if graph.name(r) in ("cheaper_than", "ranked"):
            graph.remove_node(r)
    for pred in list(graph.into(op)):                     # X --cheaper_than--> op
        if graph.name(pred) == "cheaper_than":
            graph.remove_node(pred)


def price_handler(source):
    """Build a dispatcher handler that answers a `price` request from an external `source`.

    `source` is the opaque outside world — a dict `{op_name: price}` or a callable
    `op_name -> price-or-None`; the KB holds none of it. For each requested operator the
    handler dereferences the op's NAME against `source` (the opaque key, §1) and:
      - on HIT: emits a current `price` result FACT (superseding any prior, §5 freshness);
        if it superseded a prior price (the price CHANGED), invalidates the stale
        `cheaper_than` incident to that op so the comparator re-derives;
      - on MISS: emits an `<error>` FACT about the op (for rules to examine);
    then marks `?o --price_known--> <yes>` (resolved, success or error, so the demand rule
    does not re-ask) and consumes the request token. A real DB query / web call slots in
    exactly where `source` is read — nothing else changes.
    """
    get = source.get if isinstance(source, dict) else source

    def handler(graph: Graph, call_id: str) -> set[str]:
        kind = ext.call_tool(graph, call_id)
        arg = ext.call_arg(graph, call_id, ext.ARG)
        if kind is None or arg is None:
            return set()
        touched = {arg}
        value = get(graph.name(arg))
        if value is None:
            touched.add(ext.emit_error(graph, kind, arg, "not_found"))
        else:
            had_prior = bool(ext.results_for(graph, kind, arg, current_only=True))
            touched.add(ext.emit_result(graph, kind, arg, str(value)))
            if had_prior:
                _invalidate_cheaper_than(graph, arg)
        _control_relation(graph, arg, "price_known", _hub(graph, "<yes>"))
        return touched           # service_calls consumes the call afterwards

    return handler


def plan(graph: Graph, rules: list[Rule] = PLANNING_RULES, *,
         registry: dict | None = None, extra_tools: dict | None = None,
         max_cycles: int = 100) -> None:
    """Run `rules` to a fixpoint over `graph` in place (vision §6).

    Each cycle is one stratified pass (stratification only prevents the within-pass
    NAC race — see the module docstring); the OUTER loop is the semi-naive iteration
    that propagates reachability through successive operator layers. `max_cycles` is
    the §12 backstop: crossing into the control layer (retraction) forfeits the
    monotone termination guarantee, so a real bound is mandatory, not a nicety.

    The price lookup AND the cost ranking are now BOTH request-driven tools serviced by the
    engine's `run(tools=)` dispatch — there is no explicit per-cycle `rank_by_cost`/
    `service_calls` step. A rule emits a `<call>` (price demand, or rank demand once cost is
    settled) and the engine services it at the rule-fixpoint, folding the result back in. The
    `tools` registry always carries the `rank` tool; a supplied lookup `registry` (e.g. the
    `price` handler) is merged in and the `REQUEST_RULES` (the price-demand + error rules) are
    added to the bank, so external lookups are also rule-driven (vision §6/§8). Without a
    registry the pure-static `cost=` path runs the same way (the rank tool reads authored costs).

    WHY THIS FOLDS NOW (it did not before): the FETCH-prices → RANK → COMMIT ordering the old
    explicit cycle enforced by hand is now enforced by DATA — the rank request is gated on
    `cost_settled`, which for an externally-priced op requires `price_known` (set by the price
    tool). So `cheaper_than` is only ever derived (by the rank tool) AFTER prices are fetched,
    and `best`/`choose` (a later stratum than `dominated`, which reads `cheaper_than`) only fire
    once that ranking exists. The `ranked` marker dedups the rank request per op.

    `extra_tools` (default None) merges in further engine-serviced tools — `solve` passes the
    `act` tool so the act/observe boundary fires inline as operators become ready (the readiness
    rule lives only in the SOLVE bank, so a standalone `plan()` still never acts)."""
    tools = {"rank": rank_handler}
    if registry is not None:
        tools = {**tools, **registry}
        bank = rules + REQUEST_RULES
    else:
        bank = rules
    if extra_tools:
        tools = {**tools, **extra_tools}
    for _ in range(max_cycles):
        before = _fingerprint(graph)
        # Control layer on the ISA forward Machine (`run_bank`): the "one engine" move — recognition
        # AND reasoning AND control (DROP_CTRL teardown) now all run on the Machine (Phase 0.3). The
        # reasoning-parity gate that blocked this is closed: literal head endpoints INTERN to their
        # graph-wide node and reified relations DEDUP (rewriter.resolve_so/_relation_exists), so a
        # downstream rule joins head-derived literals by identity and the `_fingerprint` loop settles.
        run_rules(graph, bank, provenance=False, tools=tools)
        if _fingerprint(graph) == before:
            return


# ---------------------------------------------------------------------------
# The world boundary — the only tool (vision §8): perform + observe
# ---------------------------------------------------------------------------

def simulate_effects(graph: Graph, op_id: str) -> None:
    """The DEFAULT action: assume an operator's DECLARED effects materialize exactly —
    assert `<now> --true--> C` for each `O --add--> C`, retract for each `O --del--> C`.
    Used when no real action tool is registered for the operator (and by tests)."""
    now = _hub(graph, "<now>")
    for r, c in graph.relations_from(op_id):
        if graph.name(r) == "add" and not _has_rel(graph, now, "true", graph.name(c)):
            graph.add_relation(now, "true", c)
        elif graph.name(r) == "del":
            _drop_rel(graph, now, "true", graph.name(c))


def _perform_op(graph: Graph, o: str, actions: dict, failures: dict[str, int]) -> None:
    """The act/observe boundary for ONE operator. WHAT becomes true in `<now>` comes from:
      - a REAL action tool `actions[op_name](graph, op_id)` if registered — it performs
        externally and emits the OBSERVED effects (which may differ from the operator's
        DECLARED `add`; that gap is real divergence, caught by `detect_divergence`); else
      - a withheld effect (`failures[op_name] > 0`) — a simulated divergence for testing; else
      - `simulate_effects` — the operator's declared effects, materialized exactly."""
    oname = graph.name(o)
    if oname in actions:
        actions[oname](graph, o)                          # the real §8 action tool observes
    elif failures.get(oname, 0) > 0:
        failures[oname] -= 1                              # withhold effects this once
    else:
        simulate_effects(graph, o)


def _consume_ready(graph: Graph, o: str) -> None:
    """Drop every `<exec> --ready--> o` token (the op has been performed)."""
    for ex in graph.nodes_named("<exec>"):
        for rid, ob in list(graph.relations_from(ex)):
            if graph.name(rid) == "ready" and ob == o:
                graph.remove_node(rid)


def act_handler(actions: dict | None = None, failures: dict[str, int] | None = None):
    """Build the `act` dispatch tool (dispatch.py: `handler(graph, call_id) -> touched ids`).

    Services a `<call> --tool--> act --arg--> O` materialized by the readiness rule
    (corpus/planning_execution.cnl): perform O at the act/observe boundary, emit the OBSERVED
    effect into `<now>`, mark O `done`, and consume its `ready` token. This is the act/observe
    boundary as an ordinary engine-serviced tool — the dual of the lookup boundary
    (`external.py`): lookups READ the world, actions WRITE it and observe back. `failures`
    (op_name -> withhold count) injects a simulated divergence for testing replan; a real tool
    expresses failure by simply not emitting the expected effect."""
    actions = actions or {}
    failures = failures if failures is not None else {}

    def handler(graph: Graph, call_id: str) -> set[str]:
        o = ext.call_arg(graph, call_id, ext.ARG)
        if o is None or not graph.has(o) or _has_rel(graph, o, "done", "<yes>"):
            return set()
        _perform_op(graph, o, actions, failures)
        _control_relation(graph, o, "done", _hub(graph, "<yes>"))
        _consume_ready(graph, o)
        return {o, _hub(graph, "<now>")}

    return handler


def act(graph: Graph, *, actions: dict | None = None,
        failures: dict[str, int] | None = None) -> list[str]:
    """TOOL boundary (§8): perform every ready, not-done operator and OBSERVE its effects.

    The BATCH form (perform all currently-ready ops at once). `solve` no longer uses it — it
    folds acting into the rule fixpoint via `act_handler` (the materialized `<call>` boundary,
    uniform with price/rank); this is kept for direct/standalone use and back-compat. See
    `_perform_op` for the per-op act/observe boundary and `failures` semantics. Returns the
    operator names performed."""
    actions = actions or {}
    failures = failures if failures is not None else {}
    performed: list[str] = []
    for ex in graph.nodes_named("<exec>"):
        for rid, o in graph.relations_from(ex):
            if graph.name(rid) != "ready" or _has_rel(graph, o, "done", "<yes>"):
                continue
            _perform_op(graph, o, actions, failures)
            _control_relation(graph, o, "done", _hub(graph, "<yes>"))
            graph.remove_node(rid)                        # consume the ready token
            performed.append(graph.name(o))
    return performed


def observe(added=(), removed=()):
    """Build a real action tool that OBSERVES a fixed set of effects, ignoring the
    operator's declared `add`/`del`. The returned handler asserts `<now> --true--> C` for
    each `added` and retracts each `removed`. Use it to model a real-world action whose
    observed result MATCHES the plan's expectation (success) or DIFFERS from it (the
    declared effect doesn't appear → `detect_divergence` fires → replan). A real
    integration would perform an external effect here and read back what actually changed."""
    def handler(graph: Graph, op_id: str) -> None:
        now = _hub(graph, "<now>")
        for c in added:
            if not _has_rel(graph, now, "true", c):
                graph.add_relation(now, "true", _hub(graph, c))
        for c in removed:
            _drop_rel(graph, now, "true", c)
    return handler


# ---------------------------------------------------------------------------
# The full loop — goal -> plan -> act -> replan
# ---------------------------------------------------------------------------

def goal_satisfied(graph: Graph) -> bool:
    """True once every `<goal> --want--> C` has `<now> --true--> C`."""
    for goal in graph.nodes_named("<goal>"):
        for r, c in graph.relations_from(goal):
            if graph.name(r) == "want" and not _has_rel(graph, _hub(graph, "<now>"),
                                                        "true", graph.name(c)):
                return False
    return True


def _replan_pending(graph: Graph) -> bool:
    return any(_has_rel(graph, n, "active", "<yes>") for n in graph.nodes_named("<replan>"))


def _clear_replan(graph: Graph) -> None:
    """Operational reset of the `<replan>` marker AFTER teardown (so the gate survives
    the whole teardown pass). Removing a disconnected control node is GC, not reasoning."""
    for n in list(graph.nodes_named("<replan>")):
        graph.remove_node(n)


def solve(graph: Graph, *, actions: dict | None = None, failures: dict[str, int] | None = None,
          registry: dict | None = None, extra_rules: list[Rule] = (), max_cycles: int = 100) -> str:
    """Drive goal -> plan -> act -> replan to a result (vision §6: the loop is the bank).

    Returns "done" (goal reached), or "stuck" (planning quiesced short of the goal with no
    divergence to replan from) — bounded by `max_cycles` (the §12 backstop for the non-monotone
    control layer). `actions` (op_name -> real §8 action tool) backs the act/observe boundary
    with real external effects; un-backed operators simulate their declared effects (see
    `_perform_op`). `failures` injects simulated divergences. `registry` (kind -> handler)
    enables on-demand external lookups (e.g. fetching costs); each replan re-validates them
    (teardown clears `price_known`, so the demand rule re-asks → a fresh fetch).

    `extra_rules` (default none) are appended to the solve bank — e.g. `procedure.PROCEDURE_RULES`,
    the gap-filling bridge that turns a chosen step's unmet precondition into a `<need>` the same
    planner phases solve (so a procedure with a missing step auto-completes). They compose with
    the planner bank and are torn down/replanned by the existing control teardown.

    Acting is FOLDED into the planning fixpoint: `plan` is given the `act` tool, so a chosen op
    is performed (and its effect observed) the moment it becomes ready, the domino cascading the
    whole plan within one `plan()` call. The outer loop then exists ONLY for divergence → replan:
    a real/simulated effect that misses its declared target trips `detect_divergence`
    (`<replan>`), and a cycle tears down control and re-plans from the new observed state.
    """
    act_tool = {"act": act_handler(actions, failures)}
    bank = SOLVE_RULES + list(extra_rules) if extra_rules else SOLVE_RULES
    for _ in range(max_cycles):
        plan(graph, bank, registry=registry, extra_tools=act_tool, max_cycles=max_cycles)
        if goal_satisfied(graph):
            return "done"
        if _replan_pending(graph):                        # control teardown, then retry
            run_rules(graph, TEARDOWN_RULES, provenance=False)   # teardown via DROP_CTRL
            _clear_replan(graph)
            continue
        return "stuck"                                    # planning quiesced short of the goal
    return "stuck"
