"""
Coffee — the planning loop's reference domain (goal -> plan -> act -> replan).

There is no planner here, no search, no Python control flow over the domain: the whole
thing is a rule bank (`harneskills.planning.SOLVE_RULES`) rewritten to a fixpoint by the
stupid scheduler. "Planning" emerges. Operators are monotone facts; the plan + execution
cursor are control-layer scaffolding torn down on divergence. See docs/planning_design.md.

The multi-step generalization of the reactive `ice_cream` demo, on the same engine.

Run:  python examples/coffee.py
"""
from __future__ import annotations

import harneskills as h


def build() -> h.Graph:
    """Author the problem as graph data (operators = facts; state + goal = seeds)."""
    g = h.Graph()
    # domain causal knowledge
    h.seed_operator(g, "make_coffee", pre=["water", "beans"], add=["have_coffee"])
    h.seed_operator(g, "get_beans", add=["beans"])
    # a DEAD option: it also makes coffee, but needs something nothing can produce, so
    # it never connects to the current state -> never viable -> silently dies (no backtracking)
    h.seed_operator(g, "buy_latte", pre=["money"], add=["have_coffee"])
    # TWO viable ways to get water -> commitment must RANK them by the fact-layer cost
    # criterion (cheap fetch beats costly delivery), not race and commit both.
    h.seed_operator(g, "fetch_water", add=["water"], cost=1)
    h.seed_operator(g, "deliver_water", add=["water"], cost=5)
    h.seed_state(g, [])                       # empty larder: no water, no beans, no money
    h.seed_goal(g, "have_coffee")
    return g


def _has(g: h.Graph, s: str, rel: str, o: str = "<yes>") -> bool:
    return any(g.name(r) == rel and g.name(ob) == o
               for si in g.nodes_named(s) for r, ob in g.relations_from(si))


def show_plan(g: h.Graph) -> None:
    for op in ("fetch_water", "deliver_water", "get_beans", "make_coffee", "buy_latte"):
        if _has(g, op, "chosen"):
            mark = "chosen"
        elif _has(g, op, "dominated"):
            mark = "dominated (costlier rival)"
        elif any(g.name(r) == "blocked_by" for s in g.nodes_named(op)
                 for r, _ in g.relations_from(s)):
            mark = "blocked"
        else:
            mark = "-"
        print(f"  {op:14} {mark}")


def main() -> None:
    print("Coffee planning (no planner - the fixpoint of a rule bank):\n")
    g = build()
    h.plan(g)                                 # derive the plan only (no acting yet)
    print("Plan (chosen operators; buy_latte dies - needs unreachable money;")
    print("      deliver_water loses to cheaper fetch_water - ranked by fact-layer cost):")
    show_plan(g)

    print("\nNow execute, with a simulated one-shot failure of make_coffee:")
    g = build()
    result = h.solve(g, failures={"make_coffee": 1})   # first attempt's effect is withheld
    print(f"  result: {result}")
    print(f"  have_coffee observed in <now>: {_has(g, '<now>', 'true', 'have_coffee')}")
    print("  (the withheld effect triggered detect_divergence -> control teardown ->")
    print("   the same rules re-planned and re-executed from the new state)")


if __name__ == "__main__":
    main()
