"""
Coffee with EXTERNAL costs — rules demand a value, a tool fetches it (vision §6/§8).

Here the cost of the two water sources is NOT in the knowledge base. It lives in an
external price "DB" (a plain dict standing in for a real query / web call). Planning
fetches it ON DEMAND: a rule emits a request token when it needs to rank a viable
option, the generic dispatcher runs the registered lookup tool, the tool emits the
price as an in-graph FACT (or an `<error>` on a miss), and the commitment rules select
over it. Nothing about the planner changed — the tool boundary is just token-passing,
exactly like the `act` boundary.

Freshness is vision §5: a re-fetch SUPERSEDES the old price (an added marker, never a
deletion) and is read through a guard ("current" = nothing supersedes it). A replan
re-validates prices, so when the world changes the plan follows.

Run:  python examples/coffee_external.py
"""
from __future__ import annotations

import harneskills as h


def build() -> h.Graph:
    g = h.Graph()
    h.seed_operator(g, "make_coffee", pre=["water", "beans"], add=["have_coffee"])
    h.seed_operator(g, "get_beans", add=["beans"])
    # the two water sources carry NO in-KB cost — their price is fetched externally
    h.seed_operator(g, "fetch_water", add=["water"], priced=True)
    h.seed_operator(g, "deliver_water", add=["water"], priced=True)
    h.seed_state(g, [])
    h.seed_goal(g, "have_coffee")
    return g


def _has(g: h.Graph, s: str, rel: str, o: str = "<yes>") -> bool:
    return any(g.name(r) == rel and g.name(ob) == o
               for si in g.nodes_named(s) for r, ob in g.relations_from(si))


def _price(g: h.Graph, op: str) -> str:
    cur = h.results_for(g, "price", g.nodes_named(op)[0])     # current (non-superseded)
    return h.result_value(g, cur[0]) if cur else "?"


def show(g: h.Graph) -> None:
    for op in ("fetch_water", "deliver_water"):
        mark = "chosen" if _has(g, op, "chosen") else \
               ("dominated" if _has(g, op, "dominated") else "-")
        print(f"  {op:14} price={_price(g, op):>3}  {mark}")


def main() -> None:
    # the external world — the KB holds none of this
    prices = {"fetch_water": 1, "deliver_water": 5}
    registry = {"price": h.price_handler(prices)}

    print("Coffee with EXTERNAL costs (rules demand prices; a tool fetches them):\n")
    g = build()
    h.plan(g, registry=registry)
    print("Fetched on demand, then ranked:")
    show(g)

    print("\nThe world changes (delivery now undercuts fetching) and we replan:")
    prices["fetch_water"], prices["deliver_water"] = 9, 1
    replan = g.add_node("<replan>")
    g.add_relation(replan, "active", g.nodes_named("<yes>")[0])
    h.run_rules(g, h.TEARDOWN_RULES)
    for n in list(g.nodes_named("<replan>")):
        g.remove_node(n)
    h.plan(g, registry=registry)
    show(g)
    print("  (the old prices are kept as superseded facts, not deleted - vision sec.5)")

    print("\nA missing price (delivery unavailable) -> an <error> fact + yield to a rival:")
    g = build()
    h.plan(g, registry={"price": h.price_handler({"fetch_water": 1})})
    show(g)
    errs = [g.name(ob) for e in g.nodes_named("<error>")
            for r, ob in g.relations_from(e) if g.name(r) == "about"]
    print(f"  <error> about: {errs}")


if __name__ == "__main__":
    main()
