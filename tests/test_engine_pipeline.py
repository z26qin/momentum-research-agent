from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from momentum_research_agent.config import find_project_root
from momentum_research_agent.tools.engine_adapter import resolve_engine_root as adapter_resolve
from momentum_research_agent.tools.engine_pipeline import (
    WARM_TIMEOUT_S,
    resolve_as_of,
    resolve_engine_root,
    resolve_pipeline_root,
    run_pipeline,
)
from momentum_research_agent.tools.engine_query import engine_query
from momentum_research_agent.tools.registry import ToolContext, set_tool_context

ENGINE = find_project_root() / "fixtures" / "engine"


@pytest.fixture
def live_engine(monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.delenv("MOMENTUM_DISABLE_PIPELINE", raising=False)
    monkeypatch.setenv("MOMENTUM_ENGINE_DIR", str(ENGINE))
    monkeypatch.delenv("MOMENTUM_ENGINE_SNAPSHOT", raising=False)
    set_tool_context(ToolContext(project_root=find_project_root(), session_dir=None))
    return ENGINE


def test_resolve_as_of_uses_requested_then_latest_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = tmp_path / "engine"
    (engine / "scripts").mkdir(parents=True)
    (engine / "scripts" / "run_monitor.py").write_text("# stub\n", encoding="utf-8")
    cache = engine / "outputs" / "pipeline_runs"
    cache.mkdir(parents=True)
    (cache / "2026-05-29.json").write_text(
        json.dumps({"as_of_date": "2026-05-29", "overall_risk_state": "normal"}),
        encoding="utf-8",
    )
    (cache / "2026-06-30.json").write_text(
        json.dumps({"as_of_date": "2026-06-30", "overall_risk_state": "normal"}),
        encoding="utf-8",
    )
    monkeypatch.delenv("MOMENTUM_DISABLE_PIPELINE", raising=False)
    monkeypatch.setenv("MOMENTUM_ENGINE_DIR", str(engine))
    assert resolve_as_of("2026-05-29", project_root=tmp_path) == "2026-05-29"
    assert resolve_as_of(None, project_root=tmp_path) == "2026-06-30"


def test_adapter_and_pipeline_share_resolve_engine_root() -> None:
    assert adapter_resolve is resolve_engine_root


def test_missing_engine_dir_does_not_fall_back(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MOMENTUM_ENGINE_DIR", str(tmp_path / "missing-engine"))
    monkeypatch.delenv("MOMENTUM_DISABLE_PIPELINE", raising=False)
    assert resolve_engine_root(find_project_root()) is None
    assert resolve_pipeline_root(find_project_root()) is None


def test_json_only_dir_is_root_but_not_pipeline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MOMENTUM_ENGINE_DIR", str(tmp_path))
    monkeypatch.delenv("MOMENTUM_DISABLE_PIPELINE", raising=False)
    assert resolve_engine_root(tmp_path) == tmp_path
    assert resolve_pipeline_root(tmp_path) is None


def test_run_pipeline_keeps_assessment_after_teardown_abort(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A written run_mvp JSON is success even if the subprocess aborts later."""
    engine = tmp_path / "engine"
    (engine / "scripts").mkdir(parents=True)
    (engine / "scripts" / "run_monitor.py").write_text("# stub\n", encoding="utf-8")
    as_of = "2026-05-29"
    cache = engine / "outputs" / "pipeline_runs" / f"{as_of}.json"

    def fake_run(cmd, **kwargs):  # noqa: ANN001
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(
            json.dumps(
                {
                    "as_of_date": as_of,
                    "overall_risk_state": "normal",
                    "full_run_fingerprint": "abc",
                }
            ),
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(
            cmd,
            1,
            stdout="",
            stderr="terminate called without an active exception",
        )

    monkeypatch.delenv("MOMENTUM_DISABLE_PIPELINE", raising=False)
    monkeypatch.setenv("MOMENTUM_ENGINE_DIR", str(engine))
    monkeypatch.setattr(
        "momentum_research_agent.tools.engine_pipeline.subprocess.run",
        fake_run,
    )
    run = run_pipeline(as_of, project_root=tmp_path)
    assert run.ok, run.error
    assert run.assessment is not None
    assert run.assessment["overall_risk_state"] == "normal"
    assert cache.is_file()


def test_repo_does_not_import_monitor_package() -> None:
    root = find_project_root() / "src" / "momentum_research_agent"
    import re

    pattern = re.compile(
        r"^\s*(from src\.mvp|import src\.mvp|import momentum_crash|from momentum_crash)\b",
        re.M,
    )
    hits: list[str] = []
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if pattern.search(text):
            hits.append(str(path))
    assert hits == []


def test_pipeline_run_mvp_for_frozen_date(live_engine: Path) -> None:
    run = run_pipeline("2026-05-29", project_root=find_project_root(), timeout_s=WARM_TIMEOUT_S)
    assert run.ok, run.error
    assert run.assessment is not None
    assert run.assessment["overall_risk_state"] == "normal"
    assert run.assessment.get("full_run_fingerprint")
    cache = live_engine / "outputs" / "pipeline_runs" / "2026-05-29.json"
    assert cache.is_file()


@pytest.mark.asyncio
async def test_engine_query_pipeline_pass_and_ignores_poisoned_snapshot(
    live_engine: Path,
) -> None:
    run_pipeline("2026-05-29", project_root=find_project_root(), timeout_s=WARM_TIMEOUT_S)
    poison = live_engine / "outputs" / "snapshot_2026-05-29" / "structured_snapshot.json"
    poison.parent.mkdir(parents=True, exist_ok=True)
    poison.write_text(
        json.dumps(
            {
                "as_of_date": "2026-05-29",
                "overall_risk_state": "panic_elevated",
                "mechanical_unwind_state": "UNWIND",
            }
        ),
        encoding="utf-8",
    )
    try:
        raw = await engine_query("NVDA", end="2026-05-29")
        payload = json.loads(raw)
        assert payload["pipeline_run"] is True
        assert payload["delivery_contract"]["verdict"] == "pass"
        assert payload["delivery_contract"]["source"] == "run_mvp"
        assert payload["delivery_contract"]["delivery_hash"]
        assert payload["delivery_hash"] == payload["delivery_contract"]["delivery_hash"]
        assert payload["risk_state"] == "normal"
        assert payload["source"] == "run_mvp"
        assert "does not read structured_snapshot.json" in payload.get("note", "")
        assert payload["risk_state"] != "panic_elevated"
    finally:
        poison.unlink(missing_ok=True)
