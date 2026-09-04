from __future__ import annotations

from pathlib import Path

from momentum_research_agent.eval.momentum_eval import (
    CASES,
    EvalResult,
    _append_failures,
    run_eval,
)
from momentum_research_agent.state.gap_ledger import ledger_path, open_gaps


def test_frozen_cases_pass_without_ledger(tmp_path: Path) -> None:
    summary = run_eval(tmp_path, write_ledger=False)
    assert summary.failed == 0
    assert summary.passed == len(CASES)
    assert summary.written == 0
    assert open_gaps(ledger_path(tmp_path)) == []


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
    gaps = open_gaps(ledger_path(tmp_path))
    assert len(gaps) == 1
    assert gaps[0].evidence_id == "eval:broken_payload_fails_vd"
    assert "V_D" in gaps[0].claim
    from momentum_research_agent.models.schemas import GapCapability
    from momentum_research_agent.coordinator.gap_tasks import gap_task_specs

    assert gaps[0].capability is GapCapability.ENGINE_FRESHNESS
    specs = gap_task_specs("Is this a crash?", gaps, max_tasks=2)
    assert specs and specs[0].kind.value == "gap"
    assert "eval:broken_payload_fails_vd" in specs[0].evidence_ids
    # open rows are not duplicated
    assert _append_failures(
        tmp_path,
        [EvalResult("broken_payload_fails_vd", False, ["again"], {})],
    ) == 0
