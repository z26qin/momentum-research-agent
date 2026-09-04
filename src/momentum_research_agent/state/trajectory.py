"""Replayable tool-call log for one session.

Written as JSONL next to the task board. This is the raw material for later
prompt/tool evolution; it is not a training run by itself.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from momentum_research_agent.state.persistence import append_jsonl, read_jsonl

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


def trajectory_failure_brief(
    reports_dir: Path,
    *,
    exclude: Path | None = None,
    max_sessions: int = 3,
    max_lines: int = 6,
) -> str:
    """Scan recent session traces for engine/tool failure patterns.

    Injected into decompose and runtime profile hints so the next run can
    change retrieval, not model weights.
    """
    if not reports_dir.is_dir():
        return ""
    skip = exclude.resolve() if exclude is not None else None
    sessions = sorted(
        (
            path
            for path in reports_dir.iterdir()
            if path.is_dir() and (path / TRAJECTORY_NAME).is_file()
        ),
        key=lambda path: path.name,
        reverse=True,
    )
    lines: list[str] = []
    seen: set[str] = set()
    used_sessions = 0
    for session in sessions:
        if skip is not None and session.resolve() == skip:
            continue
        contributed = False
        for raw in _read_events(session / TRAJECTORY_NAME):
            marker = _failure_marker(raw)
            if marker is None:
                continue
            tool = str(raw.get("tool") or "tool")
            key = f"{tool}:{marker}"
            if key in seen:
                continue
            seen.add(key)
            preview = str(raw.get("result_preview") or "").replace("\n", " ")
            if len(preview) > 100:
                preview = preview[:97] + "..."
            lines.append(f"{session.name} {tool} [{marker}] {preview}")
            contributed = True
            if len(lines) >= max_lines:
                return "\n".join(lines)
        if contributed:
            used_sessions += 1
            if used_sessions >= max_sessions:
                break
    return "\n".join(lines)


def _read_events(path: Path) -> list[dict[str, Any]]:
    return [row for row in read_jsonl(path) if isinstance(row, dict)]


def _failure_marker(event: dict[str, Any]) -> str | None:
    preview = str(event.get("result_preview") or "")
    blob = f"{event.get('tool') or ''} {preview}"
    if '"verdict": "fail"' in preview or "'verdict': 'fail'" in preview:
        return "vd_fail"
    if "MOCK DATA" in preview:
        return "mock_engine"
    if "Unauthorized" in blob:
        return "unauthorized"
    if "Traceback" in preview:
        return "traceback"
    lowered = preview.lower()
    if "as_of_match" in preview and "false" in lowered:
        return "stale_as_of"
    if "no snapshot" in lowered:
        return "no_snapshot"
    return None
