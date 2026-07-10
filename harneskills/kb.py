"""
Rule bank — a thin container of Rule objects (the "bank").

In the one-substrate vision (docs/vision.md) the world and its facts live in a
`Graph`; rules are applied to it by `rewriter.run()`. This holds the rule set and
nothing else — there are no scopes, no KV layer, no fact store here (facts are
nodes in the Graph).

Note: "rules as graph nodes" — picking up CNL rules as-is so rules are themselves
part of the one substrate — is a later step (the forms/normalization work). For
now a rule is a `Rule` object and the bank is a plain collection of them.
"""
from __future__ import annotations

from collections.abc import Iterable, Iterator

from ugm.production_rule import Rule


class RuleBank:
    """A collection of `Rule`s to hand to `rewriter.run(graph, bank.all())`."""

    def __init__(self, rules: Iterable[Rule] | None = None) -> None:
        self._rules: list[Rule] = list(rules or [])

    def add(self, rule: Rule) -> Rule:
        self._rules.append(rule)
        return rule

    def extend(self, rules: Iterable[Rule]) -> None:
        self._rules.extend(rules)

    def all(self) -> list[Rule]:
        return list(self._rules)

    def by_key(self, key: str) -> list[Rule]:
        return [r for r in self._rules if r.key == key]

    def __iter__(self) -> Iterator[Rule]:
        return iter(self._rules)

    def __len__(self) -> int:
        return len(self._rules)

    def __repr__(self) -> str:
        return f"RuleBank({len(self._rules)} rules)"


# Transitional alias.
KnowledgeBase = RuleBank
