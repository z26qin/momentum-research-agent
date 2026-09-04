"""Replayable tool-call log for one session.

Written as JSONL next to the task board. This is the raw material for later
prompt/tool evolution; it is not a training run by itself.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from momentum_research_agent.state.persistence import append_jsonl

TRAJECTORY_NAME = "trajectory.jsonl"
_PREVIEW = 240


def trajectory_path(session_dir: Path) -> Path:
    return Path(session_dir) / TRAJECTORY_NAME


def append_tool_event(
    session_dir: Path,
    *,
    agent: str,
    tool: str,
    arguments: dict[str, Any],
    result: str,
    task_id: str | None = None,
) -> None:
    preview = result if len(result) <= _PREVIEW else result[:_PREVIEW] + "…"
    append_jsonl(
        trajectory_path(session_dir),
        {
            "ts": datetime.now(timezone.utc).isoformat(),
            "agent": agent,
            "task_id": task_id,
            "tool": tool,
            "arguments": arguments,
            "result_preview": preview,
            "result_chars": len(result),
        },
    )
