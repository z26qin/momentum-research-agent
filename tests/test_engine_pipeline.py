from __future__ import annotations

import json
from pathlib import Path

import pytest

from momentum_research_agent.tools.engine_adapter import (
    bundled_engine_root,
    is_frozen_replay,
)
from momentum_research_agent.tools.engine_pipeline import (
    clear_pipeline_cache,
    peek_cached_assessment,
    run_monitor_assessment,
    warm_monitor,
)
from momentum_research_agent.tools.engine_query import engine_query
from momentum_research_agent.tools.registry import ToolContext, set_tool_context

STUB = """\
import argparse
import json
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--as-of-date", required=True)
parser.add_argument("--output-json", required=True)
parser.add_argument("--compare-to-date", default=None)
parser.add_argument("--evidence-cutoff", default=None)
parser.add_argument("--horizon-days", type=int, default=20)
args = parser.parse_args()
out = Path(args.output_json)
out.parent.mkdir(parents=True, exist_ok=True)
payload = {
    "as_of_date": args.as_of_date,
    "overall_risk_state": "panic_elevated",
    "mechanical_unwind_state": "UNWIND",
    "mechanism_scores": {"crowded_unwind": 88},
    "pm_posture": "escalate_for_pm_review",
}
out.write_text(json.dumps(payload), encoding="utf-8")
print(json.dumps(payload))
"""


def _stub_engine(root: Path) -> Path:
    script = root / "scripts" / "run_monitor.py"
    script.parent.mkdir(parents=True)
    script.write_text(STUB, encoding="utf-8")
    return root


def _frozen_engine(
    root: Path, dates: tuple[str, ...] = ("2026-05-29", "2026-06-30")
) -> Path:
    _stub_engine(root)
    (root / "SOURCE.txt").write_text("frozen replay\n", encoding="utf-8")
    for day in dates:
        snap = root / "outputs" / f"snapshot_{day}" / "structured_snapshot.json"
        snap.parent.mkdir(parents=True, exist_ok=True)
        snap.write_text(
            json.dumps(
                {
                    "temporal_scope": {"analysis_as_of_date": day},
                    "market_backdrop": {"dm_inspired_market_state": "normal"},
                    "mechanical_unwind": {"unwind_state": "QUIET"},
                    "mechanism_scores": {"crowded_unwind": 10},
                }
            ),
            encoding="utf-8",
        )
    return root


@pytest.fixture(autouse=True)
def _reset_pipeline(monkeypatch: pytest.MonkeyPatch) -> None:
    clear_pipeline_cache()
    monkeypatch.delenv("MOMENTUM_DISABLE_PIPELINE", raising=False)
    monkeypatch.delenv("MOMENTUM_ENGINE_SNAPSHOT", raising=False)
    monkeypatch.setenv("MOMENTUM_DISABLE_LOCAL_DM", "1")
    yield
    clear_pipeline_cache()


@pytest.mark.asyncio
async def test_engine_query_runs_monitor_script(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = _stub_engine(tmp_path / "monitor")
    monkeypatch.setenv("MOMENTUM_ENGINE_DIR", str(engine))
    set_tool_context(
        ToolContext(project_root=tmp_path, session_dir=tmp_path / "session")
    )
    raw = await engine_query("NVDA", end="2026-05-29")
    payload = json.loads(raw)
    assert payload["source"] == "momentum-tail-risk-monitor"
    assert payload["pipeline_run"] is True
    assert payload["risk_state"] == "panic_elevated"
    assert payload["regime"] == "UNWIND"
    assert payload["as_of"] == "2026-05-29"
    assert payload["delivery_contract"]["verdict"] == "pass"
    assert "Live PIT" in payload["note"]
    assert (tmp_path / "session" / "engine_runs" / "2026-05-29.json").is_file()


@pytest.mark.asyncio
async def test_stale_snapshot_defers_to_pipeline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = _stub_engine(tmp_path / "monitor")
    snap = engine / "outputs" / "latest_assessment.json"
    snap.parent.mkdir(parents=True)
    snap.write_text(
        json.dumps(
            {
                "as_of_date": "2026-05-29",
                "overall_risk_state": "normal",
                "mechanical_unwind_state": "QUIET",
                "mechanism_scores": {"crowded_unwind": 10},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("MOMENTUM_ENGINE_DIR", str(engine))
    set_tool_context(
        ToolContext(project_root=tmp_path, session_dir=tmp_path / "session")
    )
    raw = await engine_query("SMH", end="2026-08-01")
    payload = json.loads(raw)
    assert payload["pipeline_run"] is True
    assert payload["as_of"] == "2026-08-01"
    assert payload["risk_state"] == "panic_elevated"
    assert payload["delivery_contract"]["verdict"] == "pass"


def test_pipeline_disabled_returns_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = _stub_engine(tmp_path / "monitor")
    monkeypatch.setenv("MOMENTUM_ENGINE_DIR", str(engine))
    monkeypatch.setenv("MOMENTUM_DISABLE_PIPELINE", "1")
    assert run_monitor_assessment("NVDA", end="2026-05-29", project_root=tmp_path) is None


def test_matching_snapshot_skips_pipeline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from momentum_research_agent.tools.engine_adapter import load_engine_state

    engine = _stub_engine(tmp_path / "monitor")
    snap = engine / "outputs" / "latest_assessment.json"
    snap.parent.mkdir(parents=True)
    snap.write_text(
        json.dumps(
            {
                "as_of_date": "2026-05-29",
                "overall_risk_state": "normal",
                "mechanical_unwind_state": "FRAGILITY_BUILDING",
                "mechanism_scores": {"crowded_unwind": 96},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("MOMENTUM_ENGINE_DIR", str(engine))
    loaded = load_engine_state("NVDA", end="2026-05-29", project_root=tmp_path)
    assert loaded is not None
    assert loaded["pipeline_run"] is False
    assert loaded["risk_state"] == "normal"


@pytest.mark.asyncio
async def test_warm_then_engine_query_prefers_pipeline_over_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = _stub_engine(tmp_path / "monitor")
    snap = engine / "outputs" / "latest_assessment.json"
    snap.parent.mkdir(parents=True, exist_ok=True)
    snap.write_text(
        json.dumps(
            {
                "as_of_date": "2026-05-29",
                "overall_risk_state": "normal",
                "mechanical_unwind_state": "QUIET",
                "mechanism_scores": {"crowded_unwind": 10},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("MOMENTUM_ENGINE_DIR", str(engine))
    set_tool_context(
        ToolContext(project_root=tmp_path, session_dir=tmp_path / "session")
    )
    warmed = warm_monitor("NVDA", end="2026-05-29", project_root=tmp_path, timeout_s=5)
    assert warmed is not None
    assert warmed["pipeline_run"] is True
    assert warmed["risk_state"] == "panic_elevated"
    peeked = peek_cached_assessment("SMH", end="2026-05-29", project_root=tmp_path)
    assert peeked is not None
    assert peeked["ticker"] == "SMH"
    assert peeked["pipeline_run"] is True
    raw = await engine_query("NVDA", end="2026-05-29")
    payload = json.loads(raw)
    assert payload["pipeline_run"] is True
    assert payload["risk_state"] == "panic_elevated"
    assert payload["delivery_contract"]["verdict"] == "pass"


def test_warm_is_noop_without_monitor_script(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("MOMENTUM_ENGINE_DIR", raising=False)
    monkeypatch.setenv("MOMENTUM_DISABLE_PIPELINE", "1")
    assert warm_monitor("NVDA", end="2026-05-29", project_root=tmp_path) is None


@pytest.mark.asyncio
async def test_engine_query_matching_snapshot_skips_pipeline_when_not_frozen(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = _stub_engine(tmp_path / "monitor")
    snap = engine / "outputs" / "latest_assessment.json"
    snap.parent.mkdir(parents=True, exist_ok=True)
    snap.write_text(
        json.dumps(
            {
                "as_of_date": "2026-05-29",
                "overall_risk_state": "normal",
                "mechanical_unwind_state": "FRAGILITY_BUILDING",
                "mechanism_scores": {"crowded_unwind": 96},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("MOMENTUM_ENGINE_DIR", str(engine))
    set_tool_context(
        ToolContext(project_root=tmp_path, session_dir=tmp_path / "session")
    )
    raw = await engine_query("NVDA", end="2026-05-29")
    payload = json.loads(raw)
    assert payload["pipeline_run"] is False
    assert payload["risk_state"] == "normal"
    assert payload["delivery_contract"]["verdict"] == "pass_with_caveats"


@pytest.mark.asyncio
async def test_frozen_replay_beats_matching_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = _frozen_engine(tmp_path / "monitor", dates=("2026-05-29",))
    monkeypatch.setenv("MOMENTUM_ENGINE_DIR", str(engine))
    set_tool_context(
        ToolContext(project_root=tmp_path, session_dir=tmp_path / "session")
    )
    raw = await engine_query("NVDA", end="2026-05-29")
    payload = json.loads(raw)
    assert is_frozen_replay(engine)
    assert payload["pipeline_run"] is True
    assert payload["risk_state"] == "panic_elevated"
    assert payload["regime"] == "UNWIND"
    assert payload["delivery_contract"]["verdict"] == "pass"


def test_warm_monitor_prefetches_frozen_snapshot_dates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = _frozen_engine(tmp_path / "monitor")
    monkeypatch.setenv("MOMENTUM_ENGINE_DIR", str(engine))
    set_tool_context(
        ToolContext(project_root=tmp_path, session_dir=tmp_path / "session")
    )
    warmed = warm_monitor("SPY", end=None, project_root=tmp_path, timeout_s=5)
    assert warmed is not None
    assert warmed["pipeline_run"] is True
    peeked_may = peek_cached_assessment("NVDA", end="2026-05-29", project_root=tmp_path)
    peeked_jun = peek_cached_assessment("NVDA", end="2026-06-30", project_root=tmp_path)
    assert peeked_may is not None
    assert peeked_jun is not None
    assert peeked_may["pipeline_run"] is True
    assert peeked_jun["pipeline_run"] is True


def test_pipeline_stub_on_bundled_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("MOMENTUM_ENGINE_DIR", raising=False)
    monkeypatch.delenv("MOMENTUM_ENGINE_SNAPSHOT", raising=False)
    set_tool_context(
        ToolContext(project_root=tmp_path, session_dir=tmp_path / "session")
    )
    bundled = bundled_engine_root()
    assert bundled is not None
    assert is_frozen_replay(bundled)
    payload = run_monitor_assessment("NVDA", end="2026-05-29", project_root=tmp_path)
    assert payload is not None
    assert payload["pipeline_run"] is True
    assert payload["as_of"] == "2026-05-29"
    assert payload["risk_state"] == "normal"
    assert payload["regime"] == "FRAGILITY_BUILDING"


@pytest.mark.asyncio
async def test_engine_query_bundled_replay_passes_vd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("MOMENTUM_ENGINE_DIR", raising=False)
    monkeypatch.delenv("MOMENTUM_ENGINE_SNAPSHOT", raising=False)
    monkeypatch.delenv("MOMENTUM_DISABLE_PIPELINE", raising=False)
    set_tool_context(
        ToolContext(project_root=tmp_path, session_dir=tmp_path / "session")
    )
    raw = await engine_query("NVDA", end="2026-05-29")
    payload = json.loads(raw)
    assert payload["source"] == "momentum-tail-risk-monitor"
    assert payload["pipeline_run"] is True
    assert payload["as_of"] == "2026-05-29"
    assert payload["risk_state"] == "normal"
    assert payload["regime"] == "FRAGILITY_BUILDING"
    assert payload["delivery_contract"]["verdict"] == "pass"


@pytest.mark.asyncio
async def test_frozen_unknown_date_falls_back_to_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("MOMENTUM_ENGINE_DIR", raising=False)
    monkeypatch.delenv("MOMENTUM_ENGINE_SNAPSHOT", raising=False)
    set_tool_context(
        ToolContext(project_root=tmp_path, session_dir=tmp_path / "session")
    )
    raw = await engine_query("NVDA", end="2026-08-01")
    payload = json.loads(raw)
    assert payload["pipeline_run"] is False
    assert payload["as_of_match"] is False
    assert payload["delivery_contract"]["verdict"] == "pass_with_caveats"
