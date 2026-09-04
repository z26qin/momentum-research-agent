from __future__ import annotations

from momentum_research_agent.coordinator.replan import (
    REPLAN_TITLE_PREFIX,
    already_replanned,
    replan_specs,
)
from momentum_research_agent.models.schemas import Task, TaskKind, TaskStatus, utcnow


def _blocked(title: str = "Momentum state") -> Task:
    return Task(
        id="abcd1234",
        title=title,
        assignment="Query the engine for NVDA crash risk.",
        profile="momentum_analyst",
        status=TaskStatus.BLOCKED,
        error="engine timeout",
        error_type="TimeoutError",
        completed_at=utcnow(),
    )


def test_replan_specs_one_replacement() -> None:
    specs = replan_specs([_blocked(), _blocked("Credit overlay")], "Is this a crash?")
    assert len(specs) == 1
    assert specs[0].kind is TaskKind.REPLAN
    assert specs[0].title.startswith(REPLAN_TITLE_PREFIX)
    assert specs[0].profile == "momentum_analyst"
    assert "engine timeout" in specs[0].assignment
    assert "Query the engine" in specs[0].assignment


def test_already_replanned() -> None:
    tasks = [
        _blocked(),
        Task(
            title="Replan: Momentum state",
            assignment="retry",
            profile="momentum_analyst",
            kind=TaskKind.REPLAN,
        ),
    ]
    assert already_replanned(tasks) is True
    assert already_replanned([_blocked()]) is False


def test_no_replan_without_blocked() -> None:
    assert replan_specs([], "q") == []
