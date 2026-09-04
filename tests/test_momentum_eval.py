from __future__ import annotations

from pathlib import Path

import pytest

from momentum_research_agent.eval.momentum_eval import (
    CASES,
    EvalCase,
    EvalResult,
    _append_failures,
    run_eval,
)
from momentum_research_agent.coordinator.gap_seed import load_rows
from momentum_research_agent.models.schemas import GapLedgerStatus, MomentumCapability


def test_eval_failures_append_to_ledger(tmp_path: Path) -> None:
    written = _append_failures(
        tmp_path,
        [
            EvalResult(
                "broken_payload_fails_vd",
                False,
                ["V_D 'fail' != 'pass'"],
                {},
            )
        ],
    )
    assert written == 1
    rows = load_rows(tmp_path)
    assert len(rows) == 1
    assert rows[0].evidence_id == "eval:broken_payload_fails_vd"
    assert "V_D" in rows[0].claim
    assert rows[0].capability is MomentumCapability.ENGINE_FRESHNESS
    assert rows[0].status is GapLedgerStatus.OPEN
    assert _append_failures(
        tmp_path,
        [EvalResult("broken_payload_fails_vd", False, ["again"], {})],
    ) == 0


def test_eval_writeback_refreshes_learned_hints(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from momentum_research_agent.eval import momentum_eval as mod
    from momentum_research_agent.state.prompt_memory import load_profile_hints
    from momentum_research_agent.state.persistence import load_json
    from momentum_research_agent.state.prompt_memory import evolution_path

    monkeypatch.setattr(
        mod,
        "CASES",
        (
            EvalCase(
                id="broken_payload_fails_vd",
                payload={"ticker": "NVDA", "source": "mock"},
                expect_contract="pass",
            ),
        ),
    )
    summary = run_eval(tmp_path, write_ledger=True)
    assert summary.failed == 1
    assert summary.written == 1
    hints = load_profile_hints(tmp_path)
    assert "Open engine_freshness gap eval:broken_payload_fails_vd" in hints
    learned = load_json(evolution_path(tmp_path))["learned"]
    assert any(item["key"] == "gap:eval:broken_payload_fails_vd" for item in learned)


def test_eval_includes_bundled_snapshot_case() -> None:
    assert any(case.id == "bundled_snapshot_2026_05_29" and case.bundled for case in CASES)
    assert any(
        case.id == "bundled_pipeline_replay" and case.via_query for case in CASES
    )
    assert any(
        case.id == "bundled_pipeline_replay_2026_06_30" and case.via_query
        for case in CASES
    )


def test_frozen_cases_pass_without_ledger(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("MOMENTUM_ENGINE_DIR", raising=False)
    monkeypatch.delenv("MOMENTUM_ENGINE_SNAPSHOT", raising=False)
    monkeypatch.delenv("MOMENTUM_DISABLE_PIPELINE", raising=False)
    summary = run_eval(tmp_path, write_ledger=False)
    assert summary.failed == 0
    assert summary.passed == len(CASES)
    assert summary.written == 0
    assert load_rows(tmp_path) == []
