"""Bounded in-session retry for BLOCKED tasks.

One extra dispatch wave, at most one replacement task. Coordinator-owned.
Not AgentBus, not a second follow-up round, not a GAP ledger seed.
"""

from __future__ import annotations

from dataclasses import dataclass

from momentum_research_agent.models.schemas import Task, TaskKind
from momentum_research_agent.tools import RESEARCH_PROFILES

REPLAN_TITLE_PREFIX = "Replan:"
DEFAULT_REPLAN_PROFILE = "momentum_analyst"
MAX_REPLAN_TASKS = 1


@dataclass(frozen=True)
class ReplanSpec:
    title: str
    assignment: str
    profile: str
    original_task_id: str
    kind: TaskKind = TaskKind.REPLAN


def is_replan_task(task: Task) -> bool:
    return task.kind is TaskKind.REPLAN


def already_replanned(tasks: list[Task]) -> bool:
    return any(is_replan_task(task) for task in tasks)


def replan_specs(
    blocked: list[Task],
    question: str,
    *,
    max_tasks: int = MAX_REPLAN_TASKS,
) -> list[ReplanSpec]:
    if max_tasks <= 0 or not blocked:
        return []
    specs: list[ReplanSpec] = []
    for task in blocked[:max_tasks]:
        profile = task.profile.removesuffix(".md")
        if profile not in RESEARCH_PROFILES:
            profile = DEFAULT_REPLAN_PROFILE
        error = task.error or "none"
        error_type = task.error_type or "unknown"
        short = task.title.strip().replace("\n", " ")
        title_claim = short if len(short) <= 48 else short[:45] + "..."
        specs.append(
            ReplanSpec(
                title=f"{REPLAN_TITLE_PREFIX} {title_claim}",
                assignment=(
                    "The previous attempt at this investigation was BLOCKED at "
                    "runtime. Retry the same mandate. Prefer a live engine "
                    "snapshot over mock data. Do not invent a second follow-up "
                    "loop.\n\n"
                    f"Research question:\n{question}\n\n"
                    f"Prior error ({error_type}): {error}\n\n"
                    f"Original assignment:\n{task.assignment}"
                ),
                profile=profile,
                original_task_id=task.id,
            )
        )
    return specs
