"""At most one kind=replan after the first dispatch wave.

Not a second follow-up and not AgentBus. Triggers: BLOCKED tasks, or this
session's engine_query was labeled mock or V_D fail. File snapshot /
local_dm / pass_with_caveats do not replan. Reads traces.jsonl only.
"""

from __future__ import annotations

import json
from pathlib import Path

from momentum_research_agent.models.schemas import Task, TaskKind, TaskStatus
from momentum_research_agent.state.traces import load_traces

MAX_REPLAN_TASKS = 1
DEFAULT_REPLAN_PROFILE = "momentum_analyst"


def is_replan_task(task: Task) -> bool:
    return task.kind is TaskKind.REPLAN


def already_replanned(tasks: list[Task]) -> bool:
    return any(is_replan_task(task) for task in tasks)


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
        if payload.get("source") == "mock":
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
        "Replan after the first dispatch wave. A task was BLOCKED or "
        "engine_query returned labeled mock or V_D fail. "
        "Revise the remaining work: name the as-of you will use, call "
        "engine_query with that explicit end, and treat file_snapshot / "
        "local_dm / mock as insufficient for a pass. Do not retry the same "
        "call that already failed. This is not an in-session follow-up.\n\n"
        f"Research question:\n{question}"
    )
