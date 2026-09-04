from __future__ import annotations

from pathlib import Path

from momentum_research_agent.coordinator.replan import (
    already_replanned,
    replan_assignment,
    should_replan,
)
from momentum_research_agent.coordinator.task_board import TaskBoard
from momentum_research_agent.models.schemas import TaskKind, TaskStatus
from momentum_research_agent.state.traces import append_traces
from momentum_research_agent.state.trajectory import load_trajectory
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


def test_replan_ignores_stale_trajectory_file(tmp_path: Path) -> None:
    session = tmp_path / "session"
    session.mkdir()
    board = TaskBoard(session, question="q")
    task = board.add_task("Momentum", "go", "momentum_analyst")
    board.activate(task.id)
    board.complete(task.id, "ok")
    pass_trace = record_trace(
        "engine_query",
        {"ticker": "NVDA", "end": "2026-05-29"},
        '{"source": "run_mvp", "pipeline_run": true, "delivery_contract": {"verdict": "pass"}}',
        agent_id=task.id,
        agent_role="momentum_analyst",
    )
    assert pass_trace is not None
    append_traces(session, [pass_trace])
    (session / "trajectory.jsonl").write_text(
        '{"tool": "engine_query", "preview": "{\\"source\\": \\"mock\\"}"}\n',
        encoding="utf-8",
    )
    assert should_replan(board.tasks, session) is False
    rows = load_trajectory(session)
    assert len(rows) == 1
    assert rows[0]["tool"] == "engine_query"
    assert "run_mvp" in rows[0]["preview"]


def _complete_with_engine(session: Path, observation: str) -> TaskBoard:
    board = TaskBoard(session, question="q")
    task = board.add_task("Momentum", "go", "momentum_analyst")
    board.activate(task.id)
    board.complete(task.id, "ok")
    trace = record_trace(
        "engine_query",
        {"ticker": "NVDA"},
        observation,
        agent_id=task.id,
        agent_role="momentum_analyst",
    )
    assert trace is not None
    append_traces(session, [trace])
    return board


def test_file_snapshot_does_not_replan(tmp_path: Path) -> None:
    session = tmp_path / "session"
    session.mkdir()
    board = _complete_with_engine(
        session,
        '{"source": "file_snapshot", "pipeline_run": false, '
        '"delivery_contract": {"verdict": "pass_with_caveats"}}',
    )
    assert should_replan(board.tasks, session) is False


def test_local_dm_caveats_does_not_replan(tmp_path: Path) -> None:
    session = tmp_path / "session"
    session.mkdir()
    board = _complete_with_engine(
        session,
        '{"source": "local_dm", "pipeline_run": false, '
        '"delivery_contract": {"verdict": "pass_with_caveats"}}',
    )
    assert should_replan(board.tasks, session) is False


def test_pipeline_false_alone_does_not_replan(tmp_path: Path) -> None:
    session = tmp_path / "session"
    session.mkdir()
    board = _complete_with_engine(
        session,
        '{"source": "run_mvp", "pipeline_run": false, '
        '"delivery_contract": {"verdict": "pass_with_caveats"}}',
    )
    assert should_replan(board.tasks, session) is False


def test_vd_fail_still_replans(tmp_path: Path) -> None:
    session = tmp_path / "session"
    session.mkdir()
    board = _complete_with_engine(
        session,
        '{"source": "run_mvp", "pipeline_run": true, '
        '"delivery_contract": {"verdict": "fail"}}',
    )
    assert should_replan(board.tasks, session) is True


def test_replan_assignment_does_not_prescribe_frozen_retry() -> None:
    text = replan_assignment("Is NVDA a crash?")
    assert "2026-05-29" not in text
    assert "2026-06-30" not in text
    assert "Do not retry the same call" in text
