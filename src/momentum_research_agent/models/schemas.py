"""Pydantic models for the task board, sub-reports, and synthesis."""

from __future__ import annotations

import re
import secrets
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, field_validator


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_task_id() -> str:
    return secrets.token_hex(4)


def new_session_id() -> str:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{stamp}_{secrets.token_hex(4)}"


class TaskStatus(str, Enum):
    PENDING = "PENDING"
    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
    BLOCKED = "BLOCKED"
    CANCELLED = "CANCELLED"


class InvalidTransition(ValueError):
    """Raised when a TaskBoard status change is not allowed."""


ALLOWED_TRANSITIONS: dict[TaskStatus, set[TaskStatus]] = {
    TaskStatus.PENDING: {TaskStatus.ACTIVE, TaskStatus.CANCELLED},
    TaskStatus.ACTIVE: {TaskStatus.COMPLETED, TaskStatus.BLOCKED, TaskStatus.CANCELLED},
    TaskStatus.BLOCKED: {TaskStatus.ACTIVE, TaskStatus.CANCELLED},
    TaskStatus.COMPLETED: set(),
    TaskStatus.CANCELLED: set(),
}


class Task(BaseModel):
    id: str = Field(default_factory=new_task_id)
    title: str
    assignment: str
    profile: str
    status: TaskStatus = TaskStatus.PENDING
    report: Optional[str] = None
    error: Optional[str] = None
    created_at: datetime = Field(default_factory=utcnow)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    tool_calls: int = 0
    tokens_used: int = 0


class TaskSpec(BaseModel):
    title: str
    assignment: str
    profile: str

    @field_validator("profile")
    @classmethod
    def normalize_profile(cls, value: str) -> str:
        return value.strip().removesuffix(".md")


class DecompositionResult(BaseModel):
    tasks: list[TaskSpec]
    reasoning: str


class SubReport(BaseModel):
    task_id: str
    title: str
    findings: str
    confidence: Literal["high", "medium", "low"] = "medium"
    key_data_points: list[str] = Field(default_factory=list)
    risks_flagged: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)


class SynthesisReport(BaseModel):
    question: str
    executive_summary: str
    analysis_by_dimension: dict[str, str] = Field(default_factory=dict)
    risk_assessment: str
    actionable_signals: list[str] = Field(default_factory=list)
    confidence_level: str
    dissenting_views: list[str] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=utcnow)


class UsageEvent(BaseModel):
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0


class UsageSummary(BaseModel):
    events: list[UsageEvent] = Field(default_factory=list)

    def add(self, model: str, prompt_tokens: int, completion_tokens: int) -> None:
        self.events.append(
            UsageEvent(
                model=model,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
            )
        )

    def totals(self) -> dict[str, dict[str, int]]:
        by_model: dict[str, dict[str, int]] = {}
        for event in self.events:
            bucket = by_model.setdefault(
                event.model, {"prompt_tokens": 0, "completion_tokens": 0, "calls": 0}
            )
            bucket["prompt_tokens"] += event.prompt_tokens
            bucket["completion_tokens"] += event.completion_tokens
            bucket["calls"] += 1
        return by_model

    @property
    def prompt_tokens(self) -> int:
        return sum(event.prompt_tokens for event in self.events)

    @property
    def completion_tokens(self) -> int:
        return sum(event.completion_tokens for event in self.events)

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


def extract_json_text(text: str) -> str:
    """Strip markdown fences and isolate the outermost JSON object/array."""
    cleaned = text.strip()
    fence = re.match(r"^```(?:json)?\s*\n?(.*)```\s*$", cleaned, re.DOTALL)
    if fence:
        cleaned = fence.group(1).strip()
    start_obj = cleaned.find("{")
    start_arr = cleaned.find("[")
    starts = [index for index in (start_obj, start_arr) if index != -1]
    if not starts:
        return cleaned
    start = min(starts)
    end_char = "}" if cleaned[start] == "{" else "]"
    end = cleaned.rfind(end_char)
    if end == -1:
        return cleaned[start:]
    return cleaned[start : end + 1]


def parse_model_json(model_cls: type[BaseModel], text: str) -> Any:
    return model_cls.model_validate_json(extract_json_text(text))
