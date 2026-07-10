from __future__ import annotations

from textual.message import Message


class StepEvent(Message):
    """Fired after each run_loop step: action dispatched + result applied."""
    def __init__(
        self,
        step_num: int,
        tool_id: str,
        slots_committed: list[str],
        residuals: list[str],
        rule_line: str = "",
        pre_values: dict[str, str] | None = None,
        post_values: dict[str, str] | None = None,
    ) -> None:
        super().__init__()
        self.step_num = step_num
        self.tool_id = tool_id
        self.slots_committed = slots_committed
        self.residuals = residuals
        self.rule_line = rule_line       # "pre_a, pre_b → post_x, post_y" from KB
        self.pre_values = pre_values or {}   # {slot: short_repr} for preconditions
        self.post_values = post_values or {}  # {slot: short_repr} for committed slots


class GoalReachedEvent(Message):
    def __init__(self, steps_taken: int, evidence: list[str]) -> None:
        super().__init__()
        self.steps_taken = steps_taken
        self.evidence = evidence


class ImpasseEvent(Message):
    def __init__(self, reason: str, evidence: list[str]) -> None:
        super().__init__()
        self.reason = reason
        self.evidence = evidence


class StatusEvent(Message):
    def __init__(self, phase: str, step: int) -> None:
        super().__init__()
        self.phase = phase
        self.step = step


class ErrorEvent(Message):
    def __init__(self, error: str) -> None:
        super().__init__()
        self.error = error
