"""Harneskills — iterative LLM harness with TUI, SLM, and knowledge authoring.

This package is a *harness on top of* UGM: it imports the reasoning substrate
from ``ugm`` (e.g. ``ugm.world_model.Graph``, ``ugm.cnl.authoring.run_rules``)
rather than re-exporting it. Consumers that need UGM primitives should import
them from ``ugm`` directly; ``harneskills`` exports only harness-owned symbols.
"""
from __future__ import annotations

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

__all__ = [
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
]
