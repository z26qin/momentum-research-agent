from __future__ import annotations

from momentum_research_agent.tools.engine_contract import (
    delivery_hash,
    verify_live_delivery,
)


def _assessment(**overrides: object) -> dict:
    payload = {
        "as_of_date": "2026-05-29",
        "overall_risk_state": "normal",
        "mechanical_unwind_state": "QUIET",
        "full_run_fingerprint": "abcd1234efgh5678",
        "mechanism_scores": {"crowded_unwind": 10},
    }
    payload.update(overrides)
    return payload


def test_verify_live_delivery_passes_consistent_artifact() -> None:
    assessment = _assessment()
    contract = verify_live_delivery(assessment, "2026-05-29")
    assert contract.verdict == "pass"
    assert contract.pipeline_run is True
    assert contract.fingerprint == "abcd1234efgh5678"
    assert contract.delivery_hash == delivery_hash(assessment)
    assert contract.as_of == "2026-05-29"


def test_verify_live_delivery_fails_bad_risk_state() -> None:
    contract = verify_live_delivery(_assessment(overall_risk_state="panic"), "2026-05-29")
    assert contract.verdict == "fail"
    assert contract.pipeline_run is True
    assert any("risk_state" in note for note in contract.notes)


def test_verify_live_delivery_fails_as_of_mismatch() -> None:
    contract = verify_live_delivery(_assessment(), "2026-06-30")
    assert contract.verdict == "fail"
    assert any("requested" in note for note in contract.notes)


def test_verify_live_delivery_fails_missing_fingerprint() -> None:
    contract = verify_live_delivery(_assessment(full_run_fingerprint=""), "2026-05-29")
    assert contract.verdict == "fail"
    assert any("fingerprint" in note for note in contract.notes)


def test_delivery_hash_changes_when_risk_state_changes() -> None:
    base = delivery_hash(_assessment())
    other = delivery_hash(_assessment(overall_risk_state="panic_elevated"))
    assert base != other
