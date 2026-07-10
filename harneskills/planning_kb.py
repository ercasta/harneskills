"""
A CNL surface for authoring a PLANNING PROBLEM — operators, initial state, and a goal.

The planning loop (`planning.py`) runs over three kinds of monotone FACT: an operator's
preconditions/effects/cost (`O --pre/add/del/cost--> C`), the observed current state
(`<now> --true--> C`), and the goal (`<goal> --want--> C`). Today those are authored in
Python (`seed_operator`/`seed_state`/`seed_goal`). This module is the thin CNL surface for
the SAME edges, so a whole problem instance can live in one `.cnl` file and be handed
straight to `planning.solve` — no Python problem-authoring.

The semantics are DATA, not Python branches: each sentence shape is a recognition FORM
(a graph-rewrite rule, `PLANNING_KB_FORMS`) that folds the surface token chain into the
exact target triple. The loader is a mechanical §8 reader (like `procedure.parse_procedures`
and `procedure.invoke`): it parses each line in its OWN throwaway graph, then TRANSFERS every
recognized target relation into the real graph BY NAME through `_hub` (get-or-create), so a
condition mentioned by several operators is ONE shared node exactly as the Python seeders do.
Parsing per-line in a throwaway graph is what keeps two mentions of `water` from tangling on
the surface chain (the tokenizer mints a fresh node per occurrence); the by-name transfer is
where sharing happens — the same discipline `procedure.py` uses.

The sentence forms (single-token operator / condition names, matching the planner's
convention — `make_coffee`, `have_coffee`):

    OPERATOR   make_coffee needs water        ->  make_coffee --pre--> water
               make_coffee produces have_coffee->  make_coffee --add--> have_coffee
               make_coffee removes water      ->  make_coffee --del--> water
               make_coffee costs 3            ->  make_coffee --cost--> "3"
               fetch_water is priced          ->  fetch_water --needs_price--> <yes>
    STATE      we have water                  ->  <now> --true--> water
    GOAL       we want have_coffee            ->  <goal> --want--> have_coffee

`costs X` is deliberately CRITERION-AGNOSTIC: the cost object is an opaque node named `X`
(vision §1 — the rule layer never reads it as a number), exactly as `seed_operator(cost=)`
produces. Scalar comparison is done by the `rank_by_cost` §8 tool today; a graded criterion
(e.g. `costs cheap`, compared by a fuzzy tool) is a drop-in tool change with NO grammar
change — the surface already lowers the datum opaquely, keeping means-selection graded-friendly.

FIRST-SLICE limits (grow from here): a condition / operator name is a SINGLE token (the
planner's own convention; multi-word conditions want the n-ary/decomposition work); one
precondition/effect per line (author several lines — they share condition nodes by name);
`we have`/`we want` are the state/goal surfaces (`the goal is C` is the noted alternative).
"""
from __future__ import annotations

from ugm.cnl.forms import tokenize
from .planning import _has_rel, _hub
from ugm.production_rule import Pat, Rule
from ugm.lowering import run_bank
from ugm.world_model import Graph

# The target relation predicates the forms emit — the EXACT edges the Python seeders produce.
# The reader transfers only these (surface scaffolding `first`/`next` and provenance are ignored).
_TARGET_PREDS = ("pre", "add", "del", "cost", "needs_price", "true", "want", "acts_on")
# Surface-chain predicate names. The goal keyword `want` is ALSO a target predicate, so the surface
# token `want` is a node named `want` distinct from the emitted `want` relation; its neighbours on
# the chain are `next` nodes. Skipping a relation whose subject/object is a chain node keeps that
# surface token from being misread as a spurious `want` fact (the only keyword/predicate collision).
_SCAFFOLD = ("first", "next", "<sentence>")


def _op_form(key: str, verb: str, pred: str) -> Rule:
    """`?op <verb> ?c`  ->  `?op --pred--> ?c`. The NAC pins `?c` as the LAST token, so a
    single-token condition folds and a stray multi-token object is left UNRECOGNIZED (reported
    by absence), never mis-parsed — the same conservatism as the fact/procedure grammars."""
    return Rule(
        key=key,
        lhs=[Pat("?s", "first", "?op"), Pat("?op", "next", f"{verb}?"),
             Pat(f"{verb}?", "next", "?c")],
        nac=[Pat("?c", "next", "?z")],
        rhs=[Pat("?op", pred, "?c")],
    )


def _hub_form(key: str, lead: str, verb: str, hub: str, pred: str) -> Rule:
    """`<lead> <verb> ?c`  ->  `<hub> --pred--> ?c` (state/goal). `lead`/`verb` are surface
    keywords (`we have` / `we want`); `<hub>` is the singleton control token the planner reads."""
    return Rule(
        key=key,
        lhs=[Pat("?s", "first", f"{lead}?"), Pat(f"{lead}?", "next", f"{verb}?"),
             Pat(f"{verb}?", "next", "?c")],
        nac=[Pat("?c", "next", "?z")],
        rhs=[Pat(hub, pred, "?c")],
    )


PLANNING_KB_FORMS: list[Rule] = [
    # operator preconditions / effects / cost
    _op_form("planning.kb.pre", "needs", "pre"),
    _op_form("planning.kb.add", "produces", "add"),
    _op_form("planning.kb.del", "removes", "del"),
    _op_form("planning.kb.cost", "costs", "cost"),
    # `?op acts_on ?obj` -> `?op --acts_on--> ?obj` (the operator's DOMAIN object — what it buys /
    # sells / grades). Read by object-scoped norms (corpus/policy.cnl `forbidden_for`) and by
    # value->plan bridges; inert for operators that carry no object.
    _op_form("planning.kb.acts_on", "acts_on", "acts_on"),
    # `?op is priced` -> `?op --needs_price--> <yes>` (external cost lookup, seed_operator priced=)
    Rule(key="planning.kb.priced",
         lhs=[Pat("?s", "first", "?op"), Pat("?op", "next", "is?"), Pat("is?", "next", "priced?")],
         nac=[Pat("priced?", "next", "?z")],
         rhs=[Pat("?op", "needs_price", "<yes>")]),
    # initial state + goal
    _hub_form("planning.kb.state", "we", "have", "<now>", "true"),
    _hub_form("planning.kb.goal", "we", "want", "<goal>", "want"),
]


def _transfer(tmp: Graph, graph: Graph) -> None:
    """Copy every recognized target relation from a parsed line's throwaway graph `tmp` into
    `graph`, BY NAME through `_hub` (get-or-create) so conditions/operators/hubs are shared.

    A relation is the predicate node `r`; its subject is the non-inert node into `r` and its
    object the node out of `r` (the same read `authoring.degree_thresholds` uses). Add-only /
    idempotent (skips an edge already present)."""
    for r in tmp.nodes():
        pred = tmp.name(r)
        if pred not in _TARGET_PREDS:
            continue
        subj = next((n for n in tmp.into(r) if not tmp.is_inert(n)), None)
        obj = next(iter(tmp.out(r)), None)
        if subj is None or obj is None:
            continue
        sname, oname = tmp.name(subj), tmp.name(obj)
        if sname in _SCAFFOLD or oname in _SCAFFOLD:
            continue                              # a surface token misread as a predicate (see above)
        if not _has_rel(graph, _hub(graph, sname), pred, oname):
            graph.add_relation(_hub(graph, sname), pred, _hub(graph, oname))


def load_planning_kb(text: str, graph: Graph | None = None) -> Graph:
    """Parse a CNL KB declaring operators + initial state + goal; return a graph seeded so that
    `planning.solve(graph, ...)` (or `planning.plan`) can run. Creates a graph if none given.

    Each non-empty, non-`#` line is one declaration, parsed in its own throwaway graph (an
    interaction, like `query.ask` / `procedure.parse_procedures`) so two mentions of a name never
    cross-link on the surface chain; the recognized target triples are then transferred by name.
    A line no form recognizes contributes nothing (controlled recognition — it is silently
    skipped, exactly like `parse_procedures`). The result lowers to the SAME edges as
    `seed_operator` / `seed_state` / `seed_goal`."""
    graph = graph if graph is not None else Graph()
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        tmp = Graph()
        tokenize(tmp, line)
        run_bank(tmp, PLANNING_KB_FORMS)
        _transfer(tmp, graph)
    return graph


def load_planning_program(text: str, graph: Graph | None = None) -> tuple[Graph, dict[str, list[str]]]:
    """Load a MIXED planning KB — operators + state + goal AND procedures — from one `.cnl`.

    Returns `(graph, procedures)` where `graph` is exactly what `load_planning_kb` produces (the
    operator/state/goal edges `planning.solve`/`plan` run over) and `procedures` is
    `{name: [ordered step names]}` for every `to NAME s1 then s2 ...` declaration in the same text
    (parsed by `procedure.parse_procedures`). The two surfaces are DISJOINT — a procedure line
    starts with the literal `to` and matches no operator/state/goal form; an operator line matches
    no procedure header — so a single file cleanly carries both. Procedures are read but NOT
    invoked here: staging one (marking its steps `chosen`) is `procedure.invoke`/`run_procedure`,
    kept a separate step so the goal-directed `solve` over the same graph is unaffected by merely
    DECLARING a procedure.

    This is the entry point for the "rules + facts + procedures in one KB" surface; `load_planning_kb`
    remains the goal-only entry (a procedure-free graph is just the empty-procedures case)."""
    from .procedure import parse_procedures        # local import: procedure.py imports planning (no cycle)
    graph = load_planning_kb(text, graph)
    return graph, parse_procedures(text)
