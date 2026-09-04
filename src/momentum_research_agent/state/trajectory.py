"""Append-only tool previews for prompt overlay (not the replay ledger)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def trajectory_path(session_dir: Path) -> Path:
    return Path(session_dir) / "trajectory.jsonl"


def append_trajectory(
    session_dir: Path,
    *,
    tool: str,
    arguments: dict[str, Any],
    observation: str,
    agent_id: str | None = None,
    agent_role: str | None = None,
) -> Path:
    path = trajectory_path(session_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    preview = observation if len(observation) <= 500 else observation[:500] + "…"
    row = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "tool": tool,
        "arguments": arguments,
        "preview": preview,
        "agent_id": agent_id,
        "agent_role": agent_role,
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    return path


def load_trajectory(session_dir: Path) -> list[dict[str, Any]]:
    path = trajectory_path(session_dir)
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rows.append(json.loads(line))
    return rows
