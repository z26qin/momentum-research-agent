from __future__ import annotations

from pathlib import Path

import pytest

from momentum_research_agent.coordinator.task_board import TaskBoard
from momentum_research_agent.models.schemas import InvalidTransition, TaskStatus


def _board(tmp_path: Path, question: str = "q") -> TaskBoard:
    return TaskBoard(tmp_path / "session", question=question, session_id="testsession")


def test_add_activate_complete(tmp_path: Path) -> None:
    board = _board(tmp_path)
    task = board.add_task("Momentum", "Check NVDA regime", "momentum_analyst")
    assert task.status is TaskStatus.PENDING
    assert board.pending[0].id == task.id
    assert board.all_done is False

    active = board.activate(task.id)
    assert active.status is TaskStatus.ACTIVE
    assert active.started_at is not None
    assert board.active[0].id == task.id

    done = board.complete(task.id, report="crowding fading")
    assert done.status is TaskStatus.COMPLETED
    assert done.report == "crowding fading"
    assert done.completed_at is not None
    assert board.completed[0].id == task.id
    assert board.all_done is True
    assert "completed=1" in board.summary


def test_fail_and_cancel(tmp_path: Path) -> None:
    board = _board(tmp_path)
    failing = board.add_task("Credit", "CDS", "credit_analyst")
    board.activate(failing.id)
    blocked = board.fail(failing.id, "timeout")
    assert blocked.status is TaskStatus.BLOCKED
    assert blocked.error == "timeout"
    assert board.all_done is True

    other = board.add_task("Macro", "Rates", "macro_analyst")
    cancelled = board.cancel(other.id, "no longer needed")
    assert cancelled.status is TaskStatus.CANCELLED
    assert board.all_done is True


def test_invalid_transition_complete_cancelled(tmp_path: Path) -> None:
    board = _board(tmp_path)
    task = board.add_task("Tech", "Levels", "technicals_analyst")
    board.cancel(task.id)
    with pytest.raises(InvalidTransition, match="CANCELLED"):
        board.complete(task.id, report="late")


def test_invalid_transition_activate_completed(tmp_path: Path) -> None:
    board = _board(tmp_path)
    task = board.add_task("Flow", "SI", "flow_analyst")
    board.activate(task.id)
    board.complete(task.id, report="ok")
    with pytest.raises(InvalidTransition):
        board.activate(task.id)


def test_save_load_round_trip(tmp_path: Path) -> None:
    board = _board(tmp_path, question="Is this a crash?")
    first = board.add_task("Momentum", "DM state", "momentum_analyst")
    board.activate(first.id)
    board.complete(first.id, report="watch")
    board.record_usage(first.id, tool_calls=3, tokens_used=1200)

    loaded = TaskBoard.load(board.session_dir)
    assert loaded.question == "Is this a crash?"
    assert loaded.session_id == "testsession"
    assert len(loaded.tasks) == 1
    restored = loaded.get(first.id)
    assert restored.title == first.title
    assert restored.assignment == first.assignment
    assert restored.profile == first.profile
    assert restored.status is TaskStatus.COMPLETED
    assert restored.report == "watch"
    assert restored.tool_calls == 3
    assert restored.tokens_used == 1200
    assert restored.created_at == first.created_at
    assert restored.kind.value == "research"


def test_followup_kind_round_trips(tmp_path: Path) -> None:
    board = _board(tmp_path)
    task = board.add_task(
        "Follow-up: crowding",
        "re-check",
        "momentum_analyst",
        kind="followup",
    )
    assert task.kind.value == "followup"
    loaded = TaskBoard.load(board.session_dir)
    assert loaded.get(task.id).kind.value == "followup"


def test_legacy_task_board_defaults_kind_to_research(tmp_path: Path) -> None:
    board = _board(tmp_path)
    payload = board.to_payload()
    payload["tasks"] = [
        {
            "id": "abcd1234",
            "title": "Momentum",
            "assignment": "x",
            "profile": "momentum_analyst",
            "status": "PENDING",
        }
    ]
    from momentum_research_agent.state.persistence import save_json

    save_json(board.path, payload)
    loaded = TaskBoard.load(board.session_dir)
    assert loaded.get("abcd1234").kind.value == "research"


def test_requeue_unfinished(tmp_path: Path) -> None:
    board = _board(tmp_path)
    crashed = board.add_task("Momentum", "x", "momentum_analyst")
    blocked = board.add_task("Credit", "y", "credit_analyst")
    board.activate(crashed.id)
    board.activate(blocked.id)
    board.fail(blocked.id, "boom")

    pending = board.requeue_unfinished()
    ids = {task.id for task in pending}
    assert crashed.id in ids
    assert blocked.id in ids
    assert board.get(crashed.id).status is TaskStatus.PENDING
    assert board.get(blocked.id).status is TaskStatus.PENDING
