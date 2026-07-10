"""
Universal consistency — domain-independent "laws" that catch errors in ANY domain.

A property declared on a relation/category (in CNL) expands, via the relation-property
tool, into rules that DERIVE a `<contradiction>` marker on any offending configuration.
Detection only ADDS a marker (vision sec.5: a monotone layer never rejects/deletes — it is
paraconsistent, a local contradiction marks itself without exploding the KB). The same
laws fire for any specific thing via `is_a` generalization, with no domain-specific rule.

Run:  python examples/consistency.py
"""
from __future__ import annotations

import harneskills as h

DECLARATIONS = """\
liquid is disjoint from solid
part_of is acyclic
before is asymmetric
"""

# A scenario with three independent errors (and some fine facts).
FACTS = [
    ("ice", "is_a", "frozen_thing"), ("frozen_thing", "is_a", "solid"),
    ("ice", "is_a", "liquid"),            # ERROR: solid (via is_a) AND liquid
    ("a", "part_of", "b"), ("b", "part_of", "c"), ("c", "part_of", "a"),  # ERROR: cycle
    ("monday", "before", "tuesday"), ("tuesday", "before", "monday"),     # ERROR: both before
    ("rex", "is_a", "dog"),               # fine
]


def build() -> h.Graph:
    g = h.Graph()
    for line in DECLARATIONS.splitlines():
        if line.strip():
            h.tokenize(g, line)
    h.run(g, h.FORM_RULES + h.CONSTRAINT_FORMS)   # CNL -> constraint facts
    for s, r, o in FACTS:
        def node(n): return g.nodes_named(n)[0] if g.nodes_named(n) else g.add_node(n)
        g.add_relation(node(s), r, node(o))
    return g


def main() -> None:
    print("Universal consistency (declare a law once, check any domain):\n")
    print("Laws (CNL):")
    for line in DECLARATIONS.splitlines():
        print(f"  {line}")

    g = build()
    rules = h.rules_in_graph(h.expand_relation_properties(g))   # laws -> concrete rules
    h.run(g, rules + h.UNIVERSAL_RULES)              # detect (+ is_a transitivity)

    print(f"\nConsistent? {h.is_consistent(g)}")
    print("Contradictions found:")
    for c in h.contradictions(g):
        print(f"  about {c['about']}  violates {c['violates']}")
    print("\n(ice is both solid-via-is_a and liquid; a->b->c->a is a part_of cycle;")
    print(" monday/tuesday are mutually 'before'. rex is just a dog - no contradiction.)")


if __name__ == "__main__":
    main()
