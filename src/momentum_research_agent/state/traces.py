"""Append-only engine/search traces for a session. verification.json compiles them."""

from __future__ import annotations

import json
from pathlib import Path

from momentum_research_agent.models.schemas import ToolTrace


def traces_path(session_dir: Path) -> Path:
    return Path(session_dir) / "traces.jsonl"


def append_traces(session_dir: Path, traces: list[ToolTrace]) -> Path:
    path = traces_path(session_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for item in traces:
            handle.write(item.model_dump_json() + "\n")
    return path


def load_traces(session_dir: Path) -> list[ToolTrace]:
    path = traces_path(session_dir)
    if not path.exists():
        return []
    loaded: list[ToolTrace] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        loaded.append(ToolTrace.model_validate(json.loads(line)))
    return loaded
