"""The single generic driver (vision §6) — the one dumb loop that runs the substrate.

It has NO domain knowledge. It runs an ordered PLAN of phases; each phase reflects its rules
from the graph (rules live as nodes / are reflected by §8 tools) and runs them to a fixpoint,
and between phases the driver services any pending tool `<request>`s through a registry (the
§8 / §12.5 handshake — a rule emits a request, a registered handler answers, never the other
way round). Sequencing, rule banks, and tool handlers are all DATA; the driver only fires
rules and routes requests until the plan is exhausted.

This is what replaces bespoke Python pipelines like the old `Session.reason()`: the "what runs
when" stops being a method body and becomes a `plan` (a list of `Phase`s) handed to one stupid
loop. A phase that needs stratified negation (a NAC over derived facts) sets `stratified=True`;
otherwise the plain fixpoint runner is used (a single stratified bank can't always hold both
reasoning and constraint-detection — they would look like a negation cycle — so detection is
just a later phase, which is the data-level expression of "detect after reasoning settles").
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from ugm.cnl.authoring import run_rules
from ugm.lowering import run_bank
from ugm.production_rule import Firing, Rule
from ugm.world_model import Graph


@dataclass
class Phase:
    """One step of a plan. `build` reflects this phase's rules from the current graph (so
    rule-creation done by earlier phases is picked up); `stratified` selects the stratified
    runner when the phase has NAC-over-derived negation."""
    name: str
    build: Callable[[Graph], list[Rule]]
    stratified: bool = False


def drive(graph: Graph, plan: list[Phase], *, registry: dict | None = None,
          seeds: list[str] | None = None) -> list[Firing]:
    """Run `plan` over `graph` to completion: each phase's rules to a fixpoint, in order.
    Returns the firing journal. A `registry` of tools (dispatch.py) is passed straight to the
    engine as `tools`, so materialized `<call>`s are serviced inside each phase's fixpoint —
    no separate dispatch pass; the engine manages it (the §6/§12.5 handshake).

    The driver is stupid by design — it knows nothing about forms, reasoning, coreference, or
    detection. Which banks run, in what order, and which tools answer requests are entirely
    the `plan` + `registry` (data, vision §6).

    `seeds` is the initial change frontier for semi-naive matching — e.g. an incremental
    Session assert seeds reasoning on the new line's nodes. Defaults to the whole graph (None).
    (Matching itself is unbounded; the hop-radius neighbourhood is retired, walkers doc §6.)"""
    journal: list[Firing] = []
    for phase in plan:
        rules = phase.build(graph)
        # Both runners are on the ISA forward Machine now (`rewriter` is retired from production).
        # A stratified phase (NAC-over-derived negation) goes through `run_rules` (per-stratum
        # `run_bank`); a non-stratified phase is a PLAIN fixpoint = `run_bank` directly (which does no
        # stratification, so a bank that would look like a negation cycle under stratification runs to
        # fixpoint as intended). Neither surfaces a `Firing` journal (recognition/control firings are
        # not explained; `explain` reads the backward `GoalSolver` trace), so the journal stays empty —
        # every `drive` caller (session) already discards the return. `seeds` is a spent perf hint under
        # the naive driver (matching is correctness-equivalent whole-graph; walkers §6).
        if phase.stratified:
            run_rules(graph, rules, tools=registry)
        else:
            run_bank(graph, rules, tools=registry)
    return journal
