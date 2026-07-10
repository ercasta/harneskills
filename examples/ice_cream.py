"""
Ice cream — the reference domain, authored ENTIRELY in CNL (`corpus/icecream.cnl`).

There is no Python domain logic here: this file only *loads* the CNL and prints the
result. Facts, the graded layer, the routing rules, a lexicon frame, and a looser
frame-driven phrasing all live in ONE unsectioned `.cnl`, parsed and run by the
one-substrate engine. There is no classifier deciding fact-vs-rule: `load_corpus`
loads the whole corpus into one graph and what each statement IS emerges from which
form recognizes it. The earlier Python `Rule` objects (MARK_RULES / SERVE_RULES) and
the `#:`-section splitter are both gone.

Routing falls out with NO planner:
  - `urgent is gradable` + `alice is very urgent`  -> an embedding (graded layer);
  - `?c is urgent when ... ?c is very urgent`       -> a crisp marker (graded firing);
  - express / regular / alternative                 -> plain rules routed on stock
    and the urgent marker, mutually exclusive via NAC, stratified so each NAC sees
    the derived marker;
  - the express lane is authored in the LOOSE form `serve urgent customers first`,
    translated to native by the CNL lexicon frame.

Run:  python examples/ice_cream.py
"""
from __future__ import annotations

import pathlib

import harneskills as h

_CNL = pathlib.Path(__file__).resolve().parent.parent / "corpus" / "icecream.cnl"


def build_scenario() -> h.Graph:
    """The substrate, recognized from the CNL corpus: facts + the graded layer, plus
    the recognized rule structure (which reasoning ignores by data)."""
    kb, _ = h.load_corpus(_CNL.read_text(encoding="utf-8"))
    return kb


def serve_all(g: h.Graph) -> None:
    """Reflect the recognized rules out of the same graph and run them, stratified."""
    rules = h.expand_rules(g) + h.expand_loose_from_graph(g)
    h.run_rules(g, rules)


def outcomes(g: h.Graph) -> dict[str, str]:
    """{customer_name: outcome} for every node that is_a customer."""
    cust = g.nodes_named("customer")[0]
    res: dict[str, str] = {}
    for c in g.nodes():
        if not any(g.name(r) == "is_a" and cust in g.out(r) for r in g.out(c)):
            continue
        outcome = "(unserved)"
        for r in g.out(c):
            obj = next(iter(g.out(r)), None)
            if obj is None:
                continue
            if g.name(r) == "served":
                outcome = f"served {g.name(obj)}"
            elif g.name(r) == "offered":
                outcome = f"offered {g.name(obj)}"
        res[g.name(c)] = outcome
    return res


def main() -> None:
    g = build_scenario()
    serve_all(g)
    print("Ice cream service (authored in CNL - no Python domain logic, no planner):")
    for name, outcome in sorted(outcomes(g).items()):
        print(f"  {name:6} -> {outcome}")


if __name__ == "__main__":
    main()
