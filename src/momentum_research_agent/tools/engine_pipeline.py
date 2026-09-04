"""Run momentum-tail-risk-monitor via subprocess. Never import src.mvp."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from momentum_research_agent.config import find_project_root

QUERY_TIMEOUT_S = 8.0
WARM_TIMEOUT_S = 90.0
FROZEN_AS_OF = ("2026-05-29", "2026-06-30")
DISABLE_ENV = "MOMENTUM_DISABLE_PIPELINE"


@dataclass(frozen=True)
class PipelineRun:
    ok: bool
    assessment: dict | None
    error: str | None
    cached: bool
    root: Path | None
    elapsed_s: float


def pipeline_disabled() -> bool:
    raw = os.environ.get(DISABLE_ENV, "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def bundled_engine_root(project_root: Path | None = None) -> Path:
    return find_project_root(project_root) / "fixtures" / "engine"


def _has_monitor_entry(root: Path) -> bool:
    return (root / "scripts" / "run_monitor.py").is_file()


def resolve_engine_root(project_root: Path | None = None) -> Path | None:
    """Single engine root for pipeline and file-snapshot fallback.

    `MOMENTUM_ENGINE_DIR` wins. If it is set but missing, do not fall back to
    sibling, bundle, or local_dm. Otherwise sibling checkout, then vendored PIT.
    """
    raw = os.environ.get("MOMENTUM_ENGINE_DIR", "").strip()
    if raw:
        path = Path(raw).expanduser()
        return path if path.is_dir() else None
    root = find_project_root(project_root)
    sibling = root.parent / "momentum-tail-risk-monitor"
    if sibling.is_dir():
        return sibling
    bundled = bundled_engine_root(root)
    if bundled.is_dir() and _has_monitor_entry(bundled):
        return bundled
    return None


def resolve_pipeline_root(project_root: Path | None = None) -> Path | None:
    """Live run_mvp root. Requires scripts/run_monitor.py. Honors MOMENTUM_DISABLE_PIPELINE."""
    if pipeline_disabled():
        return None
    root = resolve_engine_root(project_root)
    if root is None or not _has_monitor_entry(root):
        return None
    return root


def pipeline_cache_path(root: Path, as_of: str) -> Path:
    return root / "outputs" / "pipeline_runs" / f"{as_of}.json"


def _load_cached(path: Path, as_of: str) -> dict | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    if str(payload.get("as_of_date") or "")[:10] != as_of:
        return None
    if not payload.get("overall_risk_state"):
        return None
    return payload


def run_pipeline(
    as_of: str,
    *,
    project_root: Path | None = None,
    timeout_s: float = QUERY_TIMEOUT_S,
    cache_dir: Path | None = None,
) -> PipelineRun:
    """Execute scripts/run_monitor.py → run_mvp. Does not read structured_snapshot.json."""
    started = time.monotonic()
    root = resolve_pipeline_root(project_root)
    if root is None:
        return PipelineRun(False, None, "pipeline root unavailable", False, None, 0.0)
    cache = (
        Path(cache_dir) / f"{as_of}.json"
        if cache_dir is not None
        else pipeline_cache_path(root, as_of)
    )
    cached = _load_cached(cache, as_of)
    if cached is not None:
        return PipelineRun(True, cached, None, True, root, time.monotonic() - started)
    script = root / "scripts" / "run_monitor.py"
    cache.parent.mkdir(parents=True, exist_ok=True)
    try:
        proc = subprocess.run(
            [
                sys.executable,
                str(script),
                "--as-of-date",
                as_of,
                "--output-json",
                str(cache),
            ],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=timeout_s,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return PipelineRun(
            False,
            None,
            f"run_monitor.py timed out after {timeout_s:.0f}s",
            False,
            root,
            time.monotonic() - started,
        )
    except OSError as exc:
        return PipelineRun(False, None, str(exc), False, root, time.monotonic() - started)
    payload = _load_cached(cache, as_of)
    if payload is not None:
        # Judge the artifact, not the process. GitHub runners have seen
        # pyarrow/pandas abort after save_assessment ("terminate called
        # without an active exception"). Deleting a good cache made V_D
        # depend on the exit code.
        return PipelineRun(True, payload, None, False, root, time.monotonic() - started)
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or f"exit {proc.returncode}").strip()
        if cache.is_file():
            cache.unlink(missing_ok=True)
        return PipelineRun(False, None, err[:500], False, root, time.monotonic() - started)
    return PipelineRun(
        False,
        None,
        "run_monitor.py wrote no usable run_mvp assessment",
        False,
        root,
        time.monotonic() - started,
    )


def warm_pipeline(
    project_root: Path | None = None,
    *,
    dates: tuple[str, ...] = FROZEN_AS_OF,
    timeout_s: float = WARM_TIMEOUT_S,
    cache_dir: Path | None = None,
) -> list[PipelineRun]:
    return [
        run_pipeline(as_of, project_root=project_root, timeout_s=timeout_s, cache_dir=cache_dir)
        for as_of in dates
    ]
