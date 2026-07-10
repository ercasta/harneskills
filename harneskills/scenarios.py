"""
A test-scenario harness for a policy-driven KB — author scenarios, see how the KB/agent performs.

A KB like `corpus/cards_kb.cnl` holds PERSISTENT knowledge (operators, action classes, standing
norms). A *scenario* is a TRANSIENT day laid over it: a goal, an optional deontic policy, and the
outcome you expect. This module rebuilds the KB fresh for each scenario, applies the transient
lines, drives the planner (`planning.solve` with the deontic-policy bank `corpus/policy.cnl`), and
reports pass/fail — so a scenario is at once a unit test and a runnable demo of the SAME KB
deciding differently as the policy changes. It is the KB-level analogue of `bench/`: behaviour you
can author and re-check, not Python you have to edit.

The KB file is read by BOTH loaders — `planning_kb.load_planning_kb` (operators + start state) and
`deontic.load_deontic` (action classes, standing norms, priorities). Their surfaces are disjoint
line-by-line, so one file carries both; `load_cards_kb` just runs the two in turn on one graph.

Scenario file format (see `corpus/cards_scenarios.txt`) — `scenario NAME` blocks, each with:
    goal C              seed a transient goal (may repeat)
    expect done|stuck   the required planner outcome
    expect chosen O     operator O must be in the committed plan (may repeat)
    expect not chosen O  operator O must NOT be in the plan (may repeat)
    <anything else>     a transient deontic/priority line applied on top of the KB
"""
from __future__ import annotations

import pathlib
from dataclasses import dataclass, field

from ugm.cnl.authoring import load_facts, load_rules
from .deontic import load_deontic
from ugm.cnl.machine_rules import load_machine_rules
from .planning import _has_rel, _hub, seed_goal, solve
from .planning_kb import load_planning_kb
from ugm.world_model import Graph

_CORPUS = pathlib.Path(__file__).resolve().parent.parent / "corpus"
# The generic deontic-policy machinery (override + guarded-read exclusion), added to the planner's
# solve bank so a prohibited operator is dropped from candidacy.
POLICY_RULES = load_machine_rules((_CORPUS / "policy.cnl").read_text(encoding="utf-8"))
# The generic graded RISK-appetite filter (prose rules — a graded condition parses only there).
# A `caution is high|medium|low` mood cuts operators by their hedged risk quality.
RISK_RULES = load_rules((_CORPUS / "risk.cnl").read_text(encoding="utf-8"))
# The generic deontic PREFERENCE ranking (encouraged > neutral > discouraged) — soft demotion via
# the planner's `dominated` marker, no calculator (discrete tiers, an authored `outranks` order).
PREFERENCE_RULES = load_machine_rules((_CORPUS / "preference.cnl").read_text(encoding="utf-8"))
# The card-trader DOMAIN reasoning (deductive value + market-driven trading stance) — prose rules
# that DERIVE facts the generic machinery acts on (e.g. a hot market -> `sell encouraged today`).
REASONING_RULES = load_rules((_CORPUS / "cards_reasoning.cnl").read_text(encoding="utf-8"))
# The full bank the planner runs alongside the domain: generic policy machinery (prohibition + risk
# exclusion, encourage/discourage ranking) PLUS the domain reasoning, all in one planning fixpoint.
SOLVE_POLICY = POLICY_RULES + RISK_RULES + PREFERENCE_RULES + REASONING_RULES


def _strip_comments(text: str) -> str:
    """Drop full-line and inline `# …` comments (the planning loader only strips full-line ones)."""
    return "\n".join(line.split("#", 1)[0] for line in text.splitlines())


def _transfer_facts(graph: Graph, text: str) -> None:
    """Fold fact-shaped lines (graded risk gradings, copula moods like `caution is medium`) into
    `graph` BY NAME, via an ISOLATED `load_facts`.

    `load_facts` runs `canonicalize`, which merges same-named nodes — and it treats planning's
    reified `add`/`pre` predicate nodes as entity mentions, collapsing them and corrupting every
    operator's effects. So we NEVER run it over the planning graph: we run it in a throwaway graph
    (which has no planning relations, so canonicalize is safe), then copy just the results we want —
    embedding degrees and copula/`is_a` facts — into `graph` by name, leaving its reified relations
    untouched. This is the same by-name transfer discipline `load_planning_kb` / `load_deontic` use."""
    tmp = Graph()
    load_facts(tmp, text)
    for n in tmp.nodes():
        emb = tmp.get_embedding(n)
        if emb:                                          # graded risk degree -> the operator node
            graph.set_embedding(_hub(graph, tmp.name(n)), dict(emb))
    for n in tmp.nodes():                                # copula moods / classes, add-only by name
        for r, o in tmp.relations_from(n):
            pred, sname, oname = tmp.name(r), tmp.name(n), tmp.name(o)
            if pred in ("is", "is_a") and not _has_rel(graph, _hub(graph, sname), pred, oname):
                graph.add_relation(_hub(graph, sname), pred, _hub(graph, oname))


def load_cards_kb(text: str, graph: Graph | None = None) -> Graph:
    """Load a card-trader KB into one graph, across three surfaces on the same text (their line
    types are disjoint, so each loader takes its own and skips the rest):
      - operators + start state       via `load_planning_kb` (`X produces Y` / `we have Y`)
      - action classes + norms + prio via `load_deontic`      (`X is a Y` / `don't …` / `A outranks B`)
      - graded facts (risk gradings)  via `_transfer_facts`   (`X is very risky`, sets embeddings)
    No goal — scenarios supply that."""
    graph = graph if graph is not None else Graph()
    text = _strip_comments(text)                        # inline comments break the last-token NACs
    load_planning_kb(text, graph)
    load_deontic(graph, text)
    _transfer_facts(graph, text)                        # graded risk facts -> embedding degrees
    return graph


def chosen_operators(graph: Graph) -> set[str]:
    """The operators the planner committed to (`O --chosen--> <yes>`)."""
    return {graph.name(n) for n in graph.nodes()
            for r, _ in graph.relations_from(n) if graph.name(r) == "chosen"}


# ---------------------------------------------------------------------------
# Scenarios — parse, run, report
# ---------------------------------------------------------------------------

@dataclass
class Scenario:
    name: str
    goals: list[str] = field(default_factory=list)
    policy: list[str] = field(default_factory=list)     # transient deontic/priority CNL lines
    outcome: str | None = None                           # 'done' | 'stuck' | None (don't check)
    chosen: list[str] = field(default_factory=list)      # operators that MUST be chosen
    not_chosen: list[str] = field(default_factory=list)  # operators that must NOT be chosen


@dataclass
class Result:
    scenario: Scenario
    got_outcome: str
    got_chosen: set[str]
    failures: list[str]

    @property
    def ok(self) -> bool:
        return not self.failures


def parse_scenarios(text: str) -> list[Scenario]:
    """Parse `scenario NAME` blocks. Blank/`#` lines ignored; a line before any `scenario` header
    is an error only in spirit — it is skipped."""
    scenarios: list[Scenario] = []
    cur: Scenario | None = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("scenario "):
            cur = Scenario(name=line[len("scenario "):].strip())
            scenarios.append(cur)
            continue
        if cur is None:
            continue
        if line.startswith("goal "):
            cur.goals.append(line[len("goal "):].strip())
        elif line.startswith("expect "):
            _parse_expect(cur, line[len("expect "):].strip())
        else:
            cur.policy.append(line)
    return scenarios


def _parse_expect(sc: Scenario, rest: str) -> None:
    if rest in ("done", "stuck"):
        sc.outcome = rest
    elif rest.startswith("not chosen "):
        sc.not_chosen.append(rest[len("not chosen "):].strip())
    elif rest.startswith("chosen "):
        sc.chosen.append(rest[len("chosen "):].strip())
    else:
        raise ValueError(f"unrecognized expectation: expect {rest}")


def run_scenario(kb_text: str, sc: Scenario) -> Result:
    """Rebuild the KB fresh, apply the scenario's transient policy + goal, drive the planner with
    the deontic-policy bank, and check the expectations. Fresh rebuild keeps scenarios independent
    (no leaked state between days)."""
    graph = load_cards_kb(kb_text)
    if sc.policy:
        policy = "\n".join(sc.policy)
        load_deontic(graph, policy)                     # deontic advice / priorities
        _transfer_facts(graph, policy)                  # a mood fact (`caution is medium`)
    for c in sc.goals:
        seed_goal(graph, c)
    outcome = solve(graph, extra_rules=SOLVE_POLICY)
    got = chosen_operators(graph)
    failures: list[str] = []
    if sc.outcome is not None and outcome != sc.outcome:
        failures.append(f"outcome: expected {sc.outcome}, got {outcome}")
    for o in sc.chosen:
        if o not in got:
            failures.append(f"expected chosen '{o}' (chosen: {sorted(got) or 'none'})")
    for o in sc.not_chosen:
        if o in got:
            failures.append(f"expected NOT chosen '{o}' but it was")
    return Result(sc, outcome, got, failures)


def run_scenarios(kb_text: str, scenarios_text: str) -> list[Result]:
    return [run_scenario(kb_text, sc) for sc in parse_scenarios(scenarios_text)]


def format_report(results: list[Result]) -> str:
    """A one-line-per-scenario pass/fail report (the harness's human face)."""
    lines: list[str] = []
    for r in results:
        tag = "PASS" if r.ok else "FAIL"
        chosen = ", ".join(sorted(r.got_chosen)) or "-"
        lines.append(f"[{tag}] {r.scenario.name:22s} outcome={r.got_outcome:5s} chosen={chosen}")
        for f in r.failures:
            lines.append(f"         ! {f}")
    passed = sum(r.ok for r in results)
    lines.append(f"\n{passed}/{len(results)} scenarios passed")
    return "\n".join(lines)


def main(kb: str = "corpus/cards_kb.cnl", scenarios: str = "corpus/cards_scenarios.txt") -> int:
    """Run a KB's scenarios and print the report. Returns the count of FAILED scenarios (exit code)."""
    kb_text = pathlib.Path(kb).read_text(encoding="utf-8")
    scn_text = pathlib.Path(scenarios).read_text(encoding="utf-8")
    results = run_scenarios(kb_text, scn_text)
    print(format_report(results))
    return sum(not r.ok for r in results)


if __name__ == "__main__":
    import sys
    sys.exit(main(*sys.argv[1:]))
