"""
Procedures — named, ordered action sequences that desugar to planner operators (vision §4-§6).

A procedure NAMES a reusable, ordered set of operators:

    to brew get_water then add_beans then heat

`to NAME` introduces a procedure; the body is a `then`-chain of step names (each a single-token
operator already authored via `seed_operator`). Recognition is CONTROLLED + CNL-emergent exactly
like the other declared grammar (`relation_forms`/`nary_forms`): a header FORM marks
`NAME is_a procedure` + links its first step, the existing `form.then` (forms.py) orders the body
into `before` edges, and a §8 reader (`parse_procedures`) walks the `before`-chain back into an
ordered step list. The declaration is parsed in a THROWAWAY graph (an interaction, like
`query.ask`) so two procedures never cross-link through a shared step name.

Invoking a procedure feeds its ordered operators straight into the EXISTING planning loop: `invoke`
marks each step `chosen` and lays the `before` edges, then `solve` executes them in order. The
`before`-gate readiness rule (`waits_for`, in corpus/planning_execution.cnl) makes the stated
`then`-order bind at execution time even when preconditions don't imply it. A procedure is thus a
PRE-MADE plan — the planner's relevance/connection/commitment phases are bypassed (there is no
goal to spray backward from); execution + divergence/replan are reused unchanged.

FIRST SLICE limits (grow from here): a step is a single-token operator NAME (no verb+object
reification yet — compose with the n-ary event work for that); a procedure is one linear
`then`-chain (no branches/conditionals); operators are still seeded in Python (`seed_operator`) —
only the SEQUENCE is CNL; invoking does NOT let the planner fill gaps, so a step with an unmet
precondition that no earlier step produces simply stalls (an honest stall, not a fabricated plan).
"""
from __future__ import annotations

import pathlib

from ugm.cnl.forms import FORM_RULES, tokenize
from ugm.cnl.machine_rules import load_machine_rules
from .planning import _has_rel, _hub, solve
from ugm.production_rule import Pat, Rule
from ugm.lowering import run_bank
from ugm.world_model import Graph

# Gap-filling bridge: a chosen step's UNMET precondition becomes a `<need>`, handing the gap to
# the goal-directed planner (corpus/procedure.cnl explains why one rule suffices). Added to the
# solve bank only when `run_procedure(..., gap_fill=True)`, so the pure planner stays untouched.
_CORPUS = pathlib.Path(__file__).resolve().parent.parent / "corpus"
PROCEDURE_RULES: list[Rule] = load_machine_rules((_CORPUS / "procedure.cnl").read_text(encoding="utf-8"))

# A procedure header: `to NAME <first step> ...`. Anchored to the sentence's first token being the
# literal `to`, so it only fires at the start and never over-generalizes (the same discipline as
# relation_forms/nary_forms). Marks NAME a procedure and links its first step; the body
# `<first> then <next> then ...` chain is left intact for `form.then` to order into `before` edges.
PROCEDURE_FORMS: list[Rule] = [
    Rule(
        key="form.procedure",
        lhs=[Pat("?s", "first", "to?"), Pat("to?", "next", "?name"),
             Pat("?name", "next", "?first")],
        rhs=[Pat("?name", "is_a", "procedure"), Pat("?name", "step", "?first")],
    ),
]


def _objs(graph: Graph, subj: str, pred: str) -> list[str]:
    return [o for r, o in graph.relations_from(subj) if graph.name(r) == pred]


def _read_one(graph: Graph) -> tuple[str, list[str]] | None:
    """Read the single procedure parsed into `graph` as (name, [ordered step names]).

    The header gave `NAME --step--> FIRST`; the body's `then`-chain became `before` edges (via
    `form.then`). Walk `before` from the first step to recover the order — no membership rule
    needed, the chain IS the membership. A repeated step name terminates the walk (first slice
    assumes a simple linear chain)."""
    name = next((n for n in graph.nodes()
                 if any(graph.name(o) == "procedure" for o in _objs(graph, n, "is_a"))), None)
    if name is None:
        return None
    firsts = _objs(graph, name, "step")
    if not firsts:
        return None
    cur: str | None = firsts[0]
    ordered: list[str] = []
    seen: set[str] = set()
    while cur is not None and graph.name(cur) not in seen:
        ordered.append(graph.name(cur))
        seen.add(graph.name(cur))
        nxt = _objs(graph, cur, "before")
        cur = nxt[0] if nxt else None
    return (graph.name(name), ordered)


def parse_procedures(text: str) -> dict[str, list[str]]:
    """Parse CNL procedure declarations into `{name: [ordered step names]}` (a §8 reader).

    Each non-empty line is one declaration, parsed in its OWN throwaway graph (an interaction,
    like `query.ask`) so procedures never cross-link via a shared step name. A line that no
    procedure form recognizes is silently skipped (controlled recognition)."""
    out: dict[str, list[str]] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        tmp = Graph()
        tokenize(tmp, line)
        # header marks the procedure + first step; form.then (in FORM_RULES) orders the body.
        run_bank(tmp, list(FORM_RULES) + PROCEDURE_FORMS)
        proc = _read_one(tmp)
        if proc is not None:
            out[proc[0]] = proc[1]
    return out


def invoke(graph: Graph, name: str, procedures: dict[str, list[str]]) -> None:
    """Stage a procedure as a PRE-MADE plan in `graph`: mark each step `chosen` and lay the
    `before` ordering between consecutive steps. The existing execution rules
    (corpus/planning_execution.cnl) then run the steps in order — the `waits_for` before-gate
    enforces the stated sequence even for steps whose order preconditions don't imply. Unknown
    procedure name => no-op. Idempotent (skips edges already present)."""
    steps = procedures.get(name)
    if not steps:
        return
    yes = _hub(graph, "<yes>")
    nodes = [_hub(graph, s) for s in steps]
    for o in nodes:
        if not _has_rel(graph, o, "chosen", "<yes>"):
            graph.add_relation(o, "chosen", yes)
    for a, b in zip(nodes, nodes[1:]):
        if not _has_rel(graph, a, "before", graph.name(b)):
            graph.add_relation(a, "before", b)


def procedure_done(graph: Graph, name: str, procedures: dict[str, list[str]]) -> bool:
    """True once every step of `name` has executed (`O --done--> <yes>`). A read-only check
    (no `_hub` — does not mint nodes): an un-run / unknown step reads as not-done."""
    steps = procedures.get(name, [])
    if not steps:
        return False
    for s in steps:
        ns = graph.nodes_named(s)
        if not (ns and _has_rel(graph, ns[0], "done", "<yes>")):
            return False
    return True


def run_procedure(graph: Graph, name: str, procedures: dict[str, list[str]], *,
                  gap_fill: bool = True, **solve_kwargs) -> str:
    """Convenience: `invoke` the procedure, then `solve` (execute it). Returns `solve`'s result
    ("done"/"stuck"). `solve_kwargs` pass through (`actions=` for real §8 action tools,
    `failures=` to inject a divergence, etc.).

    `gap_fill` (default True) adds `PROCEDURE_RULES` to the solve bank so a step's UNMET
    precondition — one the procedure didn't list a producer for — becomes a `<need>` the
    goal-directed planner fills (finding/committing/ordering a producer before the step; see
    corpus/procedure.cnl). Set it False for a STRICT procedure that stalls on a missing pre
    rather than auto-completing. With no `<goal>` seeded the planner's goal-spray is otherwise
    inert; "done" means the procedure (and any gap-fillers) ran to completion (check
    `procedure_done` for the per-step witness)."""
    invoke(graph, name, procedures)
    if gap_fill:
        solve_kwargs.setdefault("extra_rules", PROCEDURE_RULES)
    result = solve(graph, **solve_kwargs)
    # `solve` reports "done" off `<goal>` satisfaction; a procedure seeds no goal, so its "done"
    # is vacuous. Report completion off the actual step witnesses instead: a stalled strict
    # procedure (an unmet precondition with gap-fill off) is "stuck", not "done".
    if result == "done" and not procedure_done(graph, name, procedures):
        return "stuck"
    return result
