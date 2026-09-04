from __future__ import annotations

from pathlib import Path

from momentum_research_agent.eval.momentum_eval import (
    CASES,
    EvalResult,
    _append_failures,
    run_eval,
)
from momentum_research_agent.coordinator.gap_seed import load_rows
from momentum_research_agent.models.schemas import GapLedgerStatus, MomentumCapability


def test_frozen_cases_pass_without_ledger(tmp_path: Path) -> None:
    summary = run_eval(tmp_path, write_ledger=False)
    assert summary.failed == 0
    assert summary.passed == len(CASES)
    assert summary.written == 0
    assert load_rows(tmp_path) == []


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


def test_eval_includes_bundled_snapshot_case() -> None:
    assert any(case.id == "bundled_snapshot_2026_05_29" and case.bundled for case in CASES)
