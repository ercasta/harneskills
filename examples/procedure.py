"""
Procedures — a NAMED, ordered action sequence that desugars to planner operators.

A procedure is a PRE-MADE plan: instead of giving the planner a goal and letting it spray an
AND-OR tree backward (the coffee demo), you NAME an ordered sequence of operators in CNL and
replay it. Invoking it feeds the ordered operators straight into the SAME goal->plan->act loop
(`harneskills.solve`); the `waits_for` before-gate (corpus/planning_execution.cnl) enforces the
stated `then`-order at execution time, even between steps whose order preconditions don't imply.

Operators are still authored in Python (`seed_operator`) — only the SEQUENCE is CNL. The
declaration is recognized CONTROLLED + CNL-emergent like every other declared form (the `to`
header), parsed in a throwaway graph, and walked back into an ordered step list.

Run:  python examples/procedure.py
"""
from __future__ import annotations

import harneskills as h


def build() -> h.Graph:
    """Author the step operators (causal facts) + empty starting state."""
    g = h.Graph()
    h.seed_operator(g, "get_water", add=["water"])
    h.seed_operator(g, "add_beans", add=["beans"])
    h.seed_operator(g, "heat", pre=["water", "beans"], add=["have_coffee"])
    # a pure-sequencing pair: `tidy` needs nothing `serve` produces, yet must follow it —
    # only the `then`-order (the before-gate) keeps it after serve.
    h.seed_operator(g, "serve", add=["served"])
    h.seed_operator(g, "tidy", add=["tidied"])
    h.seed_state(g, [])
    return g


def _recorder(order):
    def make(name):
        def f(graph, op_id):
            order.append(name)
            h.simulate_effects(graph, op_id)         # still produce the declared effect
        return f
    return make


def main() -> None:
    # The whole procedure lives in CNL — one header line, a `then`-chain of operator names.
    cnl = "to brew get_water then add_beans then heat then serve then tidy"
    procs = h.parse_procedures(cnl)
    print("Procedure (CNL):", cnl)
    print("Parsed ordered steps:", procs["brew"], "\n")

    g = build()
    order: list[str] = []
    rec = _recorder(order)
    actions = {n: rec(n) for n in procs["brew"]}
    result = h.run_procedure(g, "brew", procs, actions=actions)

    print(f"Invoke 'brew' -> solve: {result}")
    print(f"Executed in order: {order}")
    print(f"  have_coffee observed: {any(g.name(o) == 'have_coffee' for n in g.nodes_named('<now>') for r, o in g.relations_from(n) if g.name(r) == 'true')}")
    print(f"  procedure_done(brew): {h.procedure_done(g, 'brew', procs)}")
    print("\n(No planner, no goal: the named sequence WAS the plan. The before-gate held the")
    print(" stated order - `tidy` ran after `serve` though it needs nothing `serve` produced.)")

    # ---- gap-filling: a procedure with a MISSING step, auto-completed by the planner ----
    print("\n" + "=" * 60)
    print("Gap-filling: `to brew2 heat` omits the water producer `heat` needs.")
    g2 = h.Graph()
    h.seed_operator(g2, "get_water", add=["water"])            # a producer the procedure omits
    h.seed_operator(g2, "heat", pre=["water"], add=["have_coffee"])
    h.seed_state(g2, [])
    procs2 = h.parse_procedures("to brew2 heat")
    order2: list[str] = []
    rec2 = _recorder(order2)
    actions2 = {n: rec2(n) for n in ("get_water", "heat")}
    result2 = h.run_procedure(g2, "brew2", procs2, actions=actions2)
    print(f"Declared steps: {procs2['brew2']}  ->  invoke 'brew2' -> solve: {result2}")
    print(f"Executed in order: {order2}")
    print("(The chosen step's unmet precondition became a <need>; the goal-directed planner")
    print(" found `get_water`, committed it, and ordered it BEFORE `heat` - one bridge rule.)")


if __name__ == "__main__":
    main()
