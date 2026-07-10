"""
The rule-linter — check the RULES against the system's own invariants (vision §2/§5).

Because rules are data (`Rule` objects; `rule_graph.py` round-trips them to/from the
substrate), a rule bank can be checked the way any other graph structure is. This is a
§8 analysis TOOL: it reads a rule bank and EMITS findings (`Smell`s) — it never rewrites.
It is the homoiconic payoff (rules are inspectable like facts), and the static-analysis
counterpart of the runtime guardrails the vision names:

  - §5 / §12.3: "a control rule that is not gated by a control token is a bug — exactly
    what the linter must flag." (check `ungated-delete`)
  - reasoning rules never delete facts; deletion is control-layer only. (same check)
  - stratified negation must hold (no negation cycle). (check `negation-cycle`, reusing
    `authoring.stratify`)

HONEST SCOPE. This catches STRUCTURAL / STATIC defects. It does NOT catch dynamic
dataflow-ordering bugs (e.g. a rule committing before a TOOL has supplied a value — the
commit-timing race in `planning.py`). That needs a tool/rule ordering analysis and is a
separate, more advanced check (see docs/consistency_design.md, roadmap step 6).
"""
from __future__ import annotations

from dataclasses import dataclass

from ugm.cnl.authoring import stratify
from ugm.production_rule import Rule, is_bound_literal, is_var, literal_name
from ugm.world_model import Graph


@dataclass(frozen=True)
class Smell:
    """One linter finding. `rule_key` is the offending rule (or '<bank>' for a
    whole-bank property like a negation cycle)."""
    rule_key: str
    kind: str
    detail: str

    def __str__(self) -> str:
        return f"[{self.kind}] {self.rule_key}: {self.detail}"


def is_control_token(tok: str) -> bool:
    """A token names a CONTROL node iff its label is `<...>` (the keyword-node
    convention — `<now>`, `<yes>`, `<replan>`, …). Control gates and control edges are
    written this way throughout, so this is how the linter recognizes a control context."""
    name = literal_name(tok)
    return name.startswith("<") and name.endswith(">")


def _produced_predicates(rules: list[Rule]) -> set[str]:
    """Plain-literal predicates that some rule's RHS creates (a head produces them)."""
    return {pat.p for r in rules for pat in r.rhs if not is_var(pat.p)}


def lint_rules(
    rules: list[Rule],
    *,
    base_predicates: frozenset[str] = frozenset(),
    check_dead_predicates: bool = False,
) -> list[Smell]:
    """Check `rules` against the system's invariants; return findings (does NOT mutate).

    High-confidence checks (always on):
      - `ungated-delete`  — a rule with a `drop` whose LHS has no control (`<...>`) token.
        Deletion is control-layer only and must be gated by a control token (vision §5).
      - `unbound-drop`    — a `drop` references a node the LHS never bound (you cannot
        delete what you did not match).
      - `no-op`           — a rule with neither RHS nor drop (it can never change anything).
      - `negation-cycle`  — the bank is not stratifiable (NAC through a cycle), reusing
        `authoring.stratify`.

    Heuristic check (opt-in, `check_dead_predicates=True`):
      - `dead-predicate?` — an LHS plain-literal predicate that no rule's RHS produces and
        that is not in `base_predicates` (the fact/form/seed predicates supplied from
        outside the bank). Off by default because without a `base_predicates` allowlist it
        flags ordinary fact predicates; pass the allowlist to use it.
    """
    smells: list[Smell] = []
    produced = _produced_predicates(rules)

    for r in rules:
        if r.drop and not any(is_control_token(t) for pat in r.lhs for t in pat.tokens()):
            smells.append(Smell(r.key, "ungated-delete",
                                "deletes an edge but no <control> token gates the LHS"))
        if r.drop and not r._drops_only_bound():
            smells.append(Smell(r.key, "unbound-drop",
                                "a drop pattern references a node the LHS did not bind"))
        if not r.rhs and not r.drop and not r.propagate:
            smells.append(Smell(r.key, "no-op",
                                "rule has no RHS, drop, or propagate effect - it does nothing"))
        if check_dead_predicates:
            for pat in r.lhs:
                p = pat.p
                if (not is_var(p) and not is_bound_literal(p) and not is_control_token(p)
                        and p not in produced and p not in base_predicates):
                    smells.append(Smell(r.key, "dead-predicate?",
                                        f"LHS predicate '{p}' is produced by no rule and is "
                                        "not in base_predicates"))

    try:
        stratify(rules)
    except ValueError as e:
        smells.append(Smell("<bank>", "negation-cycle", str(e)))

    return smells


def lint_graph(graph: Graph, **kwargs) -> list[Smell]:
    """Lint rules that live in the substrate as rule-nodes (via `rule_graph.rules_in_graph`).

    Only the structural fields (lhs/rhs/nac/drop) round-trip through the rule-graph, which
    is exactly what the linter inspects, so this is the in-substrate entry point.
    """
    from ugm.cnl.rule_graph import rules_in_graph
    return lint_rules(rules_in_graph(graph), **kwargs)


def emit_smells(graph: Graph, smells: list[Smell]) -> None:
    """Materialize findings into the substrate as `<rule-smell>` nodes (the in-graph view,
    cf. `surface.explain` as a reader). Each: `<rule-smell> --about--> <rule key>`,
    `<rule-smell> --kind--> <kind>`. Rules/tools/humans can then read them like any node."""
    for s in smells:
        node = graph.add_node("<rule-smell>")
        graph.add_relation(node, "about", graph.add_node(s.rule_key))
        graph.add_relation(node, "kind", graph.add_node(s.kind))


def format_smells(smells: list[Smell]) -> str:
    """A short multi-line report (empty string if clean)."""
    return "\n".join(str(s) for s in smells)
