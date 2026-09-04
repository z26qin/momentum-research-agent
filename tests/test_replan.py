from __future__ import annotations

from momentum_research_agent.coordinator.replan import (
    REPLAN_TITLE_PREFIX,
    already_replanned,
    engine_failure_replan_specs,
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


def test_engine_failure_replan_from_trajectory(tmp_path) -> None:
    from momentum_research_agent.state.trajectory import append_tool_event

    session = tmp_path / "session"
    session.mkdir()
    append_tool_event(
        session,
        agent="momentum_analyst",
        tool="engine_query",
        arguments={"ticker": "NVDA"},
        result="MOCK DATA — no momentum-tail-risk-monitor snapshot found.",
        task_id="abcd",
    )
    specs = engine_failure_replan_specs(session, "Is this a crash?")
    assert len(specs) == 1
    assert specs[0].kind.value == "replan"
    assert "live engine" in specs[0].title
    assert "mock_engine" in specs[0].assignment
    assert specs[0].profile == "momentum_analyst"
    assert engine_failure_replan_specs(tmp_path / "empty", "q") == []
