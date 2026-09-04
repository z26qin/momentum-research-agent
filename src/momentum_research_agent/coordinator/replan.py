"""At most one kind=replan after the first dispatch wave.

Not a second follow-up and not AgentBus. Triggers: BLOCKED tasks, or this
session's engine_query was mock / stale / V_D fail.
"""

from __future__ import annotations

import json
from pathlib import Path

from momentum_research_agent.models.schemas import Task, TaskKind, TaskStatus
from momentum_research_agent.state.traces import load_traces
from momentum_research_agent.state.trajectory import load_trajectory

MAX_REPLAN_TASKS = 1
DEFAULT_REPLAN_PROFILE = "momentum_analyst"


def is_replan_task(task: Task) -> bool:
    return task.kind is TaskKind.REPLAN


def already_replanned(tasks: list[Task]) -> bool:
    return any(is_replan_task(task) for task in tasks)


def _payload_from_preview(preview: str) -> dict | None:
    try:
        parsed = json.loads(preview.rstrip("…"))
    except json.JSONDecodeError:
        start = preview.find("{")
        if start == -1:
            return None
        try:
            parsed = json.loads(preview[start:])
        except json.JSONDecodeError:
            return None
    return parsed if isinstance(parsed, dict) else None


def session_engine_needs_replan(session_dir: Path) -> bool:
    for trace in load_traces(session_dir):
        if trace.tool != "engine_query":
            continue
        try:
            payload = json.loads(trace.observation)
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict):
            continue
        if payload.get("source") in {"mock", "local_dm"}:
            return True
        if payload.get("as_of_match") is False:
            return True
        contract = payload.get("delivery_contract")
        if isinstance(contract, dict) and contract.get("verdict") == "fail":
            return True
        if payload.get("pipeline_run") is not True:
            return True
    for row in load_trajectory(session_dir):
        if row.get("tool") != "engine_query":
            continue
        payload = _payload_from_preview(str(row.get("preview") or ""))
        if payload is None:
            continue
        if payload.get("source") in {"mock", "local_dm"}:
            return True
        contract = payload.get("delivery_contract")
        if isinstance(contract, dict) and contract.get("verdict") == "fail":
            return True
    return False


def should_replan(tasks: list[Task], session_dir: Path) -> bool:
    if already_replanned(tasks):
        return False
    if any(task.status is TaskStatus.BLOCKED for task in tasks):
        return True
    return session_engine_needs_replan(session_dir)


def replan_assignment(question: str) -> str:
    return (
        "Replan after the first dispatch wave. A task was BLOCKED or this "
        "session's engine_query was mock, stale, or V_D failed. "
        "Call engine_query with an explicit end=YYYY-MM-DD (prefer 2026-05-29 "
        "or 2026-06-30). Require pipeline_run=true and delivery_contract.verdict=pass "
        "from live run_mvp. This is not an in-session follow-up.\n\n"
        f"Research question:\n{question}"
    )
