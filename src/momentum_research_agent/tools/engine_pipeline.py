"""Run momentum-tail-risk-monitor as a subprocess. Do not import that package.

Prefers `scripts/run_monitor.py --as-of-date` so engine_query can obtain a
live PIT assessment from the parquet panels instead of a stale JSON file.
Vendored `fixtures/engine` ships the same CLI as a frozen replay stub
(SOURCE.txt present) so known as-of dates can still set pipeline_run and
pass V_D without a sibling monitor checkout. Timeouts and missing
checkouts fail closed to the snapshot / local_dm path.
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
    frozen_snapshot_dates,
    is_frozen_replay,
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


def warm_timeout_s() -> float:
    raw = os.environ.get("MOMENTUM_ENGINE_WARM_TIMEOUT", "90")
    try:
        return max(pipeline_timeout_s(), float(raw))
    except ValueError:
        return 90.0


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
    session_path = _session_output_path(as_of)
    if session_path is not None:
        return session_path
    folder = Path(os.environ.get("TMPDIR", "/tmp")) / "momentum-engine-runs"
    folder.mkdir(parents=True, exist_ok=True)
    return folder / f"{as_of}.json"


def _session_output_path(as_of: str) -> Path | None:
    try:
        ctx = get_tool_context()
    except RuntimeError:
        return None
    if ctx.session_dir is None:
        return None
    folder = ctx.session_dir / "engine_runs"
    folder.mkdir(parents=True, exist_ok=True)
    return folder / f"{as_of}.json"


def _python_cmd(engine_root: Path) -> list[str]:
    uv = shutil.which("uv")
    if uv and (engine_root / "pyproject.toml").is_file():
        return [uv, "run", "--directory", str(engine_root), "python", str(MONITOR_SCRIPT)]
    return [sys.executable, str(engine_root / MONITOR_SCRIPT)]


def _cache_key(root: Path, as_of: str) -> tuple[str, str]:
    return (str(root.resolve()), as_of)


def _from_cache(
    cached: dict[str, Any],
    ticker: str,
    start: str | None,
    end: str | None,
) -> dict[str, Any]:
    payload = dict(cached)
    payload["ticker"] = ticker.upper()
    payload["start"] = start
    payload["end"] = end
    return payload


def peek_cached_assessment(
    ticker: str,
    start: str | None = None,
    end: str | None = None,
    *,
    project_root: Path | None = None,
) -> dict[str, Any] | None:
    """Return a warmed pipeline payload from memory or session engine_runs/. No subprocess."""
    if pipeline_disabled():
        return None
    root = resolve_engine_root(project_root)
    if root is None:
        return None
    as_of = _as_of_day(end)
    cache_key = _cache_key(root, as_of)
    cached = _CACHE.get(cache_key)
    if cached is not None:
        return _from_cache(cached, ticker, start, end)
    output = _session_output_path(as_of)
    if output is None or not output.is_file():
        return None
    loaded = _load_normalized(output, ticker, start, end, as_of)
    if loaded is None:
        return None
    _CACHE[cache_key] = loaded
    return loaded


def run_monitor_assessment(
    ticker: str,
    start: str | None = None,
    end: str | None = None,
    *,
    project_root: Path | None = None,
    timeout_s: float | None = None,
) -> dict[str, Any] | None:
    """Return a normalized engine payload from a live run_monitor.py, or None."""
    if pipeline_disabled():
        return None
    root = resolve_engine_root(project_root)
    script = monitor_script(root)
    if script is None or root is None:
        return None
    as_of = _as_of_day(end)
    cached = peek_cached_assessment(ticker, start, end, project_root=project_root)
    if cached is not None:
        return cached
    output = _output_path(as_of)
    if output.is_file():
        loaded = _load_normalized(output, ticker, start, end, as_of)
        if loaded is not None:
            _CACHE[_cache_key(root, as_of)] = loaded
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
            timeout=pipeline_timeout_s() if timeout_s is None else max(1.0, float(timeout_s)),
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if completed.returncode != 0:
        return None
    loaded = _load_normalized(output, ticker, start, end, as_of)
    if loaded is None:
        return None
    _CACHE[_cache_key(root, as_of)] = loaded
    return loaded


def warm_monitor(
    ticker: str = "SPY",
    start: str | None = None,
    end: str | None = None,
    *,
    project_root: Path | None = None,
    timeout_s: float | None = None,
) -> dict[str, Any] | None:
    """Prefetch a live or frozen-replay PIT run so ReAct's 10s tool budget hits cache.

    Frozen replay (`SOURCE.txt`) also warms every vendored snapshot_* date when
    `end` is omitted, so engine_query(end=2026-05-29) hits cache. No-op when
    `scripts/run_monitor.py` is absent.
    """
    if pipeline_disabled() or not engine_has_pipeline(project_root):
        return None
    timeout = warm_timeout_s() if timeout_s is None else timeout_s
    root = resolve_engine_root(project_root)
    if is_frozen_replay(root) and end is None and root is not None:
        as_ofs: list[str | None] = frozen_snapshot_dates(root) or [end]
    else:
        as_ofs = [end]
    last: dict[str, Any] | None = None
    for as_of in as_ofs:
        peeked = peek_cached_assessment(ticker, start, as_of, project_root=project_root)
        if peeked is not None:
            last = peeked
            continue
        loaded = run_monitor_assessment(
            ticker,
            start,
            as_of,
            project_root=project_root,
            timeout_s=timeout,
        )
        if loaded is not None:
            last = loaded
    return last


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
