from __future__ import annotations

import json
from pathlib import Path

import pytest

from momentum_research_agent.tools.engine_adapter import (
    iter_engine_artifacts,
    load_engine_state,
    normalize_engine_payload,
    select_engine_artifact,
)
from momentum_research_agent.tools.engine_query import engine_query


def _isolate_engine_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("MOMENTUM_ENGINE_DIR", str(tmp_path / "missing-engine"))
    monkeypatch.setenv("MOMENTUM_DISABLE_LOCAL_DM", "1")
    monkeypatch.delenv("MOMENTUM_ENGINE_SNAPSHOT", raising=False)


def _write_latest(root: Path) -> Path:
    payload = {
        "as_of_date": "2026-05-29",
        "overall_risk_state": "normal",
        "pm_posture": "escalate_for_pm_review",
        "mechanical_unwind_state": "FRAGILITY_BUILDING",
        "mechanism_scores": {"crowded_unwind": 96, "dm_recovery": 45},
        "mechanism_statuses": {
            "bear_market_recovery_crash": "watch",
            "crowded_theme_unwind": "triggered",
        },
        "score_is_probability": False,
        "theme_cluster": ["CIEN", "NVDA"],
        "retrieved_evidence": [
            {
                "evidence_id": "csu-nvda-1",
                "headline_or_summary": "NVIDIA reports quarter",
                "source": "NVIDIA IR",
            }
        ],
    }
    path = root / "outputs" / "latest_assessment.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


@pytest.mark.asyncio
async def test_engine_query_falls_back_to_labeled_mock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _isolate_engine_env(monkeypatch, tmp_path)
    raw = await engine_query("NVDA", start="2026-01-01", end="2026-05-29")
    payload = json.loads(raw)
    assert payload["source"] == "mock"
    assert payload["ticker"] == "NVDA"
    assert "MOCK DATA" in payload["note"]
    assert payload["risk_state"] in {"normal", "bear_low_volatility", "panic_elevated"}
    assert payload["regime"] in {"QUIET", "FRAGILITY_BUILDING", "UNWIND"}
    assert payload["dm_bear_market_indicator"] == (
        payload["risk_state"] in {"bear_low_volatility", "panic_elevated"}
    )
    assert payload["delivery_contract"]["verdict"] == "pass_with_caveats"
    assert payload["delivery_contract"]["contract"] == "V_D"


@pytest.mark.asyncio
async def test_engine_query_uses_local_dm_when_no_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from momentum_research_agent.tools.local_dm import geometric_closes, score_from_closes

    monkeypatch.setenv("MOMENTUM_ENGINE_DIR", str(tmp_path / "missing-engine"))
    monkeypatch.delenv("MOMENTUM_ENGINE_SNAPSHOT", raising=False)
    monkeypatch.delenv("MOMENTUM_DISABLE_LOCAL_DM", raising=False)
    path = geometric_closes(
        n=520,
        start=100.0,
        daily_mu=-0.001,
        shocks=(0.02, -0.02),
        end="2026-05-29",
        crash_days=21,
        crash_mu=-0.025,
    )
    local = score_from_closes("NVDA", path, path, end="2026-05-29")
    monkeypatch.setattr(
        "momentum_research_agent.tools.engine_query.score_local_dm",
        lambda *args, **kwargs: local,
    )
    raw = await engine_query("NVDA", end="2026-05-29")
    payload = json.loads(raw)
    assert payload["source"] == "local_dm"
    assert payload["risk_state"] == "panic_elevated"
    assert payload["regime"] == "UNWIND"
    assert payload["delivery_contract"]["verdict"] == "pass"


@pytest.mark.asyncio
async def test_engine_query_reads_latest_assessment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_latest(tmp_path)
    monkeypatch.setenv("MOMENTUM_ENGINE_DIR", str(tmp_path))
    monkeypatch.delenv("MOMENTUM_ENGINE_SNAPSHOT", raising=False)
    raw = await engine_query("NVDA", end="2026-05-29")
    payload = json.loads(raw)
    assert payload["source"] == "momentum-tail-risk-monitor"
    assert payload["risk_state"] == "normal"
    assert payload["regime"] == "FRAGILITY_BUILDING"
    assert payload["pm_posture"] == "escalate_for_pm_review"
    assert payload["crowding_score"] == 0.96
    assert payload["conditional_crash_frequency"] is None
    assert payload["scope"] == "market_or_book"
    assert "theme_cluster" in payload["ticker_mentions"]
    assert payload["as_of"] == "2026-05-29"
    assert payload["as_of_match"] is True
    assert payload["delivery_contract"]["verdict"] in {"pass", "pass_with_caveats"}
    assert payload["delivery_contract"]["contract"] == "V_D"


def test_select_prefers_matching_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_latest(tmp_path)
    snap = tmp_path / "outputs" / "snapshot_2026-06-30" / "structured_snapshot.json"
    snap.parent.mkdir(parents=True)
    snap.write_text(
        json.dumps(
            {
                "temporal_scope": {"analysis_as_of_date": "2026-06-30"},
                "market_backdrop": {"dm_inspired_market_state": "bear_low_volatility"},
                "mechanical_unwind": {"unwind_state": "QUIET"},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("MOMENTUM_ENGINE_DIR", str(tmp_path))
    monkeypatch.delenv("MOMENTUM_ENGINE_SNAPSHOT", raising=False)
    chosen = select_engine_artifact(tmp_path, as_of="2026-06-30")
    assert chosen == snap
    loaded = load_engine_state("SMH", end="2026-06-30", project_root=tmp_path)
    assert loaded is not None
    assert loaded["risk_state"] == "bear_low_volatility"
    assert loaded["dm_bear_market_indicator"] is True
    assert loaded["regime"] == "QUIET"
    assert loaded["as_of"] == "2026-06-30"


def test_stale_as_of_is_flagged(tmp_path: Path) -> None:
    path = _write_latest(tmp_path)
    payload = normalize_engine_payload(
        json.loads(path.read_text(encoding="utf-8")),
        "AAPL",
        path,
        end="2026-08-01",
    )
    assert payload["as_of_match"] is False
    assert "AAPL" in payload["note"]
    assert payload["ticker_mentions"] == []


def test_start_date_is_not_used_as_as_of(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_latest(tmp_path)
    snap = tmp_path / "outputs" / "snapshot_2026-01-01" / "structured_snapshot.json"
    snap.parent.mkdir(parents=True)
    snap.write_text(
        json.dumps(
            {
                "temporal_scope": {"analysis_as_of_date": "2026-01-01"},
                "market_backdrop": {"dm_inspired_market_state": "panic_elevated"},
                "mechanical_unwind": {"unwind_state": "UNWIND"},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("MOMENTUM_ENGINE_DIR", str(tmp_path))
    monkeypatch.delenv("MOMENTUM_ENGINE_SNAPSHOT", raising=False)
    loaded = load_engine_state(
        "SMH", start="2026-01-01", end=None, project_root=tmp_path
    )
    assert loaded is not None
    assert loaded["as_of"] == "2026-05-29"
    assert loaded["risk_state"] == "normal"
    assert loaded["start"] == "2026-01-01"
    assert loaded["as_of_match"] is True


def test_quiet_control_examples_are_ignored(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    quiet = tmp_path / "outputs" / "quiet_control_example_risk_output"
    quiet.mkdir(parents=True)
    quiet.joinpath("pm_risk_assessment_2024-01-05.json").write_text(
        json.dumps(
            {
                "config": {"as_of_date": "2024-01-05"},
                "overall_risk_state": "bear_low_volatility",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("MOMENTUM_ENGINE_DIR", str(tmp_path))
    monkeypatch.delenv("MOMENTUM_ENGINE_SNAPSHOT", raising=False)
    assert iter_engine_artifacts(tmp_path) == []
    assert select_engine_artifact(tmp_path) is None
    assert load_engine_state("NVDA", project_root=tmp_path) is None
