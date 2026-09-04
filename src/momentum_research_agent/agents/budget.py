"""Per-run budgets for the ReAct loop."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LoopBudget:
    max_turns: int = 8
    overall_deadline_s: float = 45.0
    llm_timeout_s: float = 20.0
    tool_timeout_s: float = 10.0
