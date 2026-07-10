"""
Coffee — the planning reference domain authored ENTIRELY in CNL (corpus/coffee_kb.cnl).

The Python twin of this demo is examples/coffee.py, where operators/state/goal are seeded
with seed_operator/seed_state/seed_goal. Here NONE of that is Python: one .cnl file declares
the whole instance and `load_planning_kb` lowers it to the exact same graph edges, which the
unchanged planning loop (`solve`) then drives. This is the "author a problem in CNL" slice
(docs/operator_goal_cnl.md).

Run:  python examples/coffee_cnl.py
"""
from __future__ import annotations

import pathlib

import harneskills as h

_KB = pathlib.Path(__file__).resolve().parent.parent / "corpus" / "coffee_kb.cnl"


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
    print("Coffee planning, authored in CNL (corpus/coffee_kb.cnl):\n")
    print(_KB.read_text(encoding="utf-8").strip(), "\n")

    g = h.load_planning_kb(_KB.read_text(encoding="utf-8"))
    h.plan(g)
    print("Plan (chosen operators; buy_latte dies - needs unreachable money;")
    print("      deliver_water loses to cheaper fetch_water - ranked by fact-layer cost):")
    show_plan(g)

    g = h.load_planning_kb(_KB.read_text(encoding="utf-8"))
    result = h.solve(g)
    print(f"\nExecute -> {result}; have_coffee observed in <now>: "
          f"{_has(g, '<now>', 'true', 'have_coffee')}")
    print("(Same edges, same fixpoint as examples/coffee.py - only the AUTHORING moved to CNL.)")


if __name__ == "__main__":
    main()
