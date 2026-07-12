"""Harneskills — iterative LLM harness with TUI, SLM, and knowledge authoring."""
from __future__ import annotations

import sys
from importlib import import_module

import ugm as _ugm
from ugm import *  # noqa: F401,F403
from ugm import external, provenance, retraction, dispatch, intake, focus, rule_control
from ugm.cnl import forms, surface, authoring, universal, machine_rules, query, rule_graph

from .interaction import (
    Oracle, auto_oracle, scripted_oracle, terminal_oracle,
    disambiguation_resolver, ask_user_handler,
)
from .kb import RuleBank, KnowledgeBase
from .lint import Smell, lint_rules, lint_graph, emit_smells, format_smells, is_control_token
from .planning import (
    seed_operator, seed_state, seed_goal,
    PLANNING_RULES, EXECUTION_RULES, TEARDOWN_RULES, SOLVE_RULES, DETECT_DIVERGENCE, REQUEST_RULES,
    plan, act, act_handler, solve, goal_satisfied, rank_by_cost, price_handler,
    simulate_effects, observe, load_planning_rules,
)
from .procedure import (
    PROCEDURE_FORMS, PROCEDURE_RULES, parse_procedures, invoke, run_procedure, procedure_done,
)
from .planning_kb import PLANNING_KB_FORMS, load_planning_kb, load_planning_program
from .session import Session, LineResult, RECOGNITION_FORMS
from ugm.external import (
    ARG, request, pending, consume_request,
    emit_result, emit_error, results_for, result_value, is_superseded,
    lookup_handler, request_hub,
)


def _alias(name: str, target: str) -> None:
    module = import_module(target)
    sys.modules[f"{__name__}.{name}"] = module
    if "." not in name:
        globals()[name] = module


for _name, _target in {
    "world_model": "ugm.world_model",
    "production_rule": "ugm.production_rule",
    "dispatch": "ugm.dispatch",
    "external": "ugm.external",
    "retraction": "ugm.retraction",
    "provenance": "ugm.provenance",
    "mode_calls": "ugm.mode_calls",
    "intake": "ugm.intake",
    "focus": "ugm.focus",
    "rule_control": "ugm.rule_control",
    "surface": "ugm.cnl.surface",
    "universal": "ugm.cnl.universal",
    "forms": "ugm.cnl.forms",
    "rule_graph": "ugm.cnl.rule_graph",
    "query": "ugm.cnl.query",
    "authoring": "ugm.cnl.authoring",
    "machine_rules": "ugm.cnl.machine_rules",
}.items():
    _alias(_name, _target)

_alias("isa", "ugm")
for _sub in [
    "attrgraph", "machine", "apply", "chain", "check", "choose",
    "suppose", "lowering",
]:
    _alias(f"isa.{_sub}", f"ugm.{_sub}")

__all__ = list(getattr(_ugm, "__all__", [])) + [
    "external", "provenance", "retraction", "dispatch", "intake", "focus", "rule_control",
    "forms", "surface", "authoring", "universal", "machine_rules", "query", "rule_graph",
    "Oracle", "auto_oracle", "scripted_oracle", "terminal_oracle",
    "disambiguation_resolver", "ask_user_handler",
    "RuleBank", "KnowledgeBase",
    "Smell", "lint_rules", "lint_graph", "emit_smells", "format_smells", "is_control_token",
    "seed_operator", "seed_state", "seed_goal",
    "PLANNING_RULES", "EXECUTION_RULES", "TEARDOWN_RULES", "SOLVE_RULES", "DETECT_DIVERGENCE",
    "REQUEST_RULES", "plan", "act", "act_handler", "solve", "goal_satisfied", "rank_by_cost",
    "price_handler", "simulate_effects", "observe", "load_planning_rules",
    "PROCEDURE_FORMS", "PROCEDURE_RULES", "parse_procedures", "invoke", "run_procedure", "procedure_done",
    "PLANNING_KB_FORMS", "load_planning_kb", "load_planning_program",
    "Session", "LineResult", "RECOGNITION_FORMS",
    "ARG", "request", "pending", "consume_request",
    "emit_result", "emit_error", "results_for", "result_value", "is_superseded",
    "lookup_handler", "request_hub",
]
