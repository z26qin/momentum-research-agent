"""Run momentum-tail-risk-monitor as a subprocess. Do not import that package.

Prefers `scripts/run_monitor.py --as-of-date` so engine_query can obtain a
live PIT assessment from the parquet panels instead of a stale JSON file.
Timeouts and missing checkouts fail closed to the snapshot / local_dm path.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from momentum_research_agent.tools.engine_adapter import (
    looks_like_engine,
    normalize_engine_payload,
    resolve_engine_root,
)
from momentum_research_agent.tools.registry import get_tool_context

MONITOR_SCRIPT = Path("scripts") / "run_monitor.py"
_CACHE: dict[tuple[str, str], dict[str, Any]] = {}


def pipeline_disabled() -> bool:
    return os.environ.get("MOMENTUM_DISABLE_PIPELINE", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }


def pipeline_timeout_s() -> float:
    raw = os.environ.get("MOMENTUM_ENGINE_TIMEOUT", "8")
    try:
        return max(1.0, float(raw))
    except ValueError:
        return 8.0


def monitor_script(root: Path | None) -> Path | None:
    if root is None or not root.is_dir():
        return None
    path = root / MONITOR_SCRIPT
    return path if path.is_file() else None


def _as_of_day(end: str | None) -> str:
    if end and len(end) >= 10:
        return end[:10]
    return datetime.now(timezone.utc).date().isoformat()


def _output_path(as_of: str) -> Path:
    try:
        folder = get_tool_context().session_dir / "engine_runs"
    except RuntimeError:
        folder = Path(os.environ.get("TMPDIR", "/tmp")) / "momentum-engine-runs"
    folder.mkdir(parents=True, exist_ok=True)
    return folder / f"{as_of}.json"


def _python_cmd(engine_root: Path) -> list[str]:
    uv = shutil.which("uv")
    if uv and (engine_root / "pyproject.toml").is_file():
        return [uv, "run", "--directory", str(engine_root), "python", str(MONITOR_SCRIPT)]
    return [sys.executable, str(engine_root / MONITOR_SCRIPT)]


def run_monitor_assessment(
    ticker: str,
    start: str | None = None,
    end: str | None = None,
    *,
    project_root: Path | None = None,
) -> dict[str, Any] | None:
    """Return a normalized engine payload from a live run_monitor.py, or None."""
    if pipeline_disabled():
        return None
    root = resolve_engine_root(project_root)
    script = monitor_script(root)
    if script is None or root is None:
        return None
    as_of = _as_of_day(end)
    cache_key = (str(root.resolve()), as_of)
    cached = _CACHE.get(cache_key)
    if cached is not None:
        payload = dict(cached)
        payload["ticker"] = ticker.upper()
        payload["start"] = start
        payload["end"] = end
        return payload
    output = _output_path(as_of)
    if output.is_file():
        loaded = _load_normalized(output, ticker, start, end, as_of)
        if loaded is not None:
            _CACHE[cache_key] = loaded
            return loaded
    cmd = [
        *_python_cmd(root),
        "--as-of-date",
        as_of,
        "--output-json",
        str(output),
    ]
    try:
        completed = subprocess.run(
            cmd,
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=pipeline_timeout_s(),
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if completed.returncode != 0:
        return None
    loaded = _load_normalized(output, ticker, start, end, as_of)
    if loaded is None:
        return None
    _CACHE[cache_key] = loaded
    return loaded


def _load_normalized(
    path: Path,
    ticker: str,
    start: str | None,
    end: str | None,
    as_of: str,
) -> dict[str, Any] | None:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(raw, dict):
        return None
    payload = normalize_engine_payload(
        raw,
        ticker,
        path,
        start=start,
        end=end or as_of,
        pipeline_run=True,
    )
    return payload


def clear_pipeline_cache() -> None:
    _CACHE.clear()


def engine_has_pipeline(project_root: Path | None = None) -> bool:
    if pipeline_disabled():
        return False
    root = resolve_engine_root(project_root)
    return monitor_script(root) is not None and looks_like_engine(root) if root else False
