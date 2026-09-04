"""Disk helpers for session artifacts. Files are the system of record."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def session_path(reports_root: Path, session_id: str) -> Path:
    return reports_root / session_id


def save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def save_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text if text.endswith("\n") else text + "\n", encoding="utf-8")


def append_jsonl(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(payload, ensure_ascii=False, default=str)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def read_jsonl(path: Path) -> list[Any]:
    if not path.exists():
        return []
    rows: list[Any] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows
