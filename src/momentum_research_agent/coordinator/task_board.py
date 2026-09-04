"""Task state machine with file persistence after every mutation."""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from momentum_research_agent.models.schemas import (
    ALLOWED_TRANSITIONS,
    InvalidTransition,
    Task,
    TaskKind,
    TaskStatus,
    utcnow,
)
from momentum_research_agent.state.persistence import load_json, save_json


class TaskBoard:
    """Single source of truth for investigation progress.

    A human should be able to `cat reports/{session}/task_board.json` at any
    time and see exactly what is running, done, or blocked.
    """

    def __init__(
        self,
        session_dir: Path,
        question: str = "",
        session_id: str | None = None,
    ) -> None:
        self.session_dir = Path(session_dir)
        self.session_dir.mkdir(parents=True, exist_ok=True)
        self.question = question
        self.session_id = session_id or self.session_dir.name
        self._tasks: dict[str, Task] = {}
        self._lock = threading.RLock()

    @property
    def path(self) -> Path:
        return self.session_dir / "task_board.json"

    def add_task(
        self,
        title: str,
        assignment: str,
        profile: str,
        task_id: str | None = None,
        kind: TaskKind | str = TaskKind.RESEARCH,
    ) -> Task:
        kwargs: dict = {
            "title": title,
            "assignment": assignment,
            "profile": profile,
            "kind": kind,
        }
        if task_id:
            kwargs["id"] = task_id
        task = Task(**kwargs)
        with self._lock:
            if task.id in self._tasks:
                raise ValueError(f"Task {task.id} already exists")
            self._tasks[task.id] = task
            self._save_unlocked()
        return task

    def activate(self, task_id: str) -> Task:
        return self._transition(
            task_id,
            TaskStatus.ACTIVE,
            started_at=utcnow(),
            error=None,
            error_type=None,
        )

    def complete(self, task_id: str, report: str | None = None) -> Task:
        return self._transition(
            task_id,
            TaskStatus.COMPLETED,
            report=report,
            completed_at=utcnow(),
            error=None,
        )

    def fail(self, task_id: str, error: str, error_type: str | None = None) -> Task:
        return self._transition(
            task_id,
            TaskStatus.BLOCKED,
            error=error,
            error_type=error_type,
            completed_at=utcnow(),
        )

    def cancel(self, task_id: str, error: str | None = None) -> Task:
        return self._transition(
            task_id,
            TaskStatus.CANCELLED,
            error=error,
            completed_at=utcnow(),
        )

    def requeue_unfinished(self) -> list[Task]:
        """Crash/resume helper: ACTIVE and BLOCKED tasks become PENDING again."""
        with self._lock:
            for task in self._tasks.values():
                if task.status in {TaskStatus.ACTIVE, TaskStatus.BLOCKED}:
                    task.status = TaskStatus.PENDING
                    task.started_at = None
                    task.completed_at = None
            self._save_unlocked()
        return self.pending

    def record_usage(
        self,
        task_id: str,
        *,
        tool_calls: int | None = None,
        tokens_used: int | None = None,
    ) -> Task:
        with self._lock:
            task = self._require(task_id)
            if tool_calls is not None:
                task.tool_calls = tool_calls
            if tokens_used is not None:
                task.tokens_used = tokens_used
            self._save_unlocked()
            return task.model_copy(deep=True)

    def get(self, task_id: str) -> Task:
        with self._lock:
            return self._require(task_id).model_copy(deep=True)

    @property
    def pending(self) -> list[Task]:
        return self._by_status(TaskStatus.PENDING)

    @property
    def active(self) -> list[Task]:
        return self._by_status(TaskStatus.ACTIVE)

    @property
    def completed(self) -> list[Task]:
        return self._by_status(TaskStatus.COMPLETED)

    @property
    def blocked(self) -> list[Task]:
        return self._by_status(TaskStatus.BLOCKED)

    @property
    def cancelled(self) -> list[Task]:
        return self._by_status(TaskStatus.CANCELLED)

    @property
    def tasks(self) -> list[Task]:
        with self._lock:
            return [task.model_copy(deep=True) for task in self._tasks.values()]

    @property
    def all_done(self) -> bool:
        with self._lock:
            if not self._tasks:
                return False
            return all(
                task.status in {TaskStatus.COMPLETED, TaskStatus.CANCELLED, TaskStatus.BLOCKED}
                for task in self._tasks.values()
            )

    @property
    def summary(self) -> str:
        with self._lock:
            counts = {status: 0 for status in TaskStatus}
            for task in self._tasks.values():
                counts[task.status] += 1
            total = len(self._tasks)
        return (
            f"{total} tasks | "
            f"pending={counts[TaskStatus.PENDING]} "
            f"active={counts[TaskStatus.ACTIVE]} "
            f"completed={counts[TaskStatus.COMPLETED]} "
            f"blocked={counts[TaskStatus.BLOCKED]} "
            f"cancelled={counts[TaskStatus.CANCELLED]}"
        )

    def save(self, session_dir: Path | None = None) -> Path:
        with self._lock:
            if session_dir is not None:
                self.session_dir = Path(session_dir)
                self.session_dir.mkdir(parents=True, exist_ok=True)
            return self._save_unlocked()

    @classmethod
    def load(cls, session_dir: Path) -> TaskBoard:
        path = Path(session_dir) / "task_board.json"
        payload = load_json(path)
        board = cls(
            session_dir=Path(session_dir),
            question=payload.get("question", ""),
            session_id=payload.get("session_id", Path(session_dir).name),
        )
        for raw in payload.get("tasks", []):
            task = Task.model_validate(raw)
            board._tasks[task.id] = task
        return board

    def to_payload(self) -> dict:
        return {
            "session_id": self.session_id,
            "question": self.question,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "summary": self.summary,
            "tasks": [task.model_dump(mode="json") for task in self._tasks.values()],
        }

    def _by_status(self, status: TaskStatus) -> list[Task]:
        with self._lock:
            return [
                task.model_copy(deep=True)
                for task in self._tasks.values()
                if task.status == status
            ]

    def _require(self, task_id: str) -> Task:
        try:
            return self._tasks[task_id]
        except KeyError as exc:
            raise KeyError(f"Unknown task: {task_id}") from exc

    def _transition(
        self,
        task_id: str,
        new_status: TaskStatus,
        **updates: Optional[object],
    ) -> Task:
        with self._lock:
            task = self._require(task_id)
            allowed = ALLOWED_TRANSITIONS[task.status]
            if new_status not in allowed:
                raise InvalidTransition(
                    f"Cannot move task {task_id} from {task.status.value} to {new_status.value}"
                )
            task.status = new_status
            for key, value in updates.items():
                if value is not None or key in {"error", "report", "error_type"}:
                    setattr(task, key, value)
            self._save_unlocked()
            return task.model_copy(deep=True)

    def _save_unlocked(self) -> Path:
        save_json(self.path, self.to_payload())
        return self.path
