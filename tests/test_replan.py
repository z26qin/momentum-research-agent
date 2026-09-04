from __future__ import annotations

from pathlib import Path

from momentum_research_agent.coordinator.replan import (
    already_replanned,
    should_replan,
)
from momentum_research_agent.coordinator.task_board import TaskBoard
from momentum_research_agent.models.schemas import TaskKind, TaskStatus
from momentum_research_agent.state.traces import append_traces
from momentum_research_agent.agents.ledger import record_trace


def test_blocked_task_triggers_one_replan(tmp_path: Path) -> None:
    board = TaskBoard(tmp_path / "session", question="q")
    task = board.add_task("Momentum", "go", "momentum_analyst")
    board.activate(task.id)
    board.fail(task.id, "timeout")
    assert should_replan(board.tasks, tmp_path / "session") is True
    board.add_task("Replan: live engine_query", "retry", "momentum_analyst", kind=TaskKind.REPLAN)
    assert already_replanned(board.tasks) is True
    assert should_replan(board.tasks, tmp_path / "session") is False


def test_mock_engine_trace_triggers_replan(tmp_path: Path) -> None:
    session = tmp_path / "session"
    session.mkdir()
    board = TaskBoard(session, question="q")
    task = board.add_task("Momentum", "go", "momentum_analyst")
    board.activate(task.id)
    board.complete(task.id, "ok")
    trace = record_trace(
        "engine_query",
        {"ticker": "NVDA", "end": "2026-05-29"},
        '{"source": "mock", "pipeline_run": false, "delivery_contract": {"verdict": "fail"}}',
        agent_id=task.id,
        agent_role="momentum_analyst",
    )
    assert trace is not None
    append_traces(session, [trace])
    assert should_replan(board.tasks, session) is True
    assert task.status is TaskStatus.COMPLETED
