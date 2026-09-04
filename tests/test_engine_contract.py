from __future__ import annotations

from momentum_research_agent.tools.engine_contract import (
    attach_delivery_contract,
    grade_engine_payload,
)


def test_complete_snapshot_passes() -> None:
    payload = {
        "ticker": "NVDA",
        "as_of": "2026-05-29",
        "source": "momentum-tail-risk-monitor",
        "risk_state": "normal",
        "regime": "FRAGILITY_BUILDING",
        "crowding_score": 0.96,
        "as_of_match": True,
    }
    contract = grade_engine_payload(payload, requested_end="2026-05-29")
    assert contract.verdict == "pass"
    assert contract.missing == []
    assert contract.invalid == []


def test_mock_is_caveat_not_fail() -> None:
    payload = {
        "ticker": "NVDA",
        "as_of": "2026-05-29",
        "source": "mock",
        "risk_state": "panic_elevated",
        "regime": "UNWIND",
        "crowding_score": 0.4,
    }
    contract = grade_engine_payload(payload)
    assert contract.verdict == "pass_with_caveats"
    assert any("mock" in item for item in contract.caveats)


def test_missing_fields_fail() -> None:
    contract = grade_engine_payload({"ticker": "NVDA", "source": "mock"})
    assert contract.verdict == "fail"
    assert "as_of" in contract.missing
    assert "risk_state" in contract.missing
    assert "regime" in contract.missing
    assert "crowding_score" in contract.missing


def test_invalid_dm_vocabulary_fails() -> None:
    contract = grade_engine_payload(
        {
            "ticker": "SMH",
            "as_of": "2026-05-29",
            "source": "momentum-tail-risk-monitor",
            "risk_state": "hot",
            "regime": "MELTDOWN",
            "crowding_score": 0.2,
        }
    )
    assert contract.verdict == "fail"
    assert any("risk_state=hot" in item for item in contract.invalid)
    assert any("regime=MELTDOWN" in item for item in contract.invalid)


def test_null_crowding_and_stale_as_of_are_caveats() -> None:
    contract = grade_engine_payload(
        {
            "ticker": "AAPL",
            "as_of": "2026-05-29",
            "end": "2026-08-01",
            "source": "momentum-tail-risk-monitor",
            "risk_state": "unknown",
            "regime": "QUIET",
            "crowding_score": None,
            "as_of_match": False,
        },
        requested_end="2026-08-01",
    )
    assert contract.verdict == "pass_with_caveats"
    joined = " ".join(contract.caveats)
    assert "crowding_score is null" in joined
    assert "as_of_match=false" in joined


def test_attach_nests_contract() -> None:
    graded = attach_delivery_contract(
        {
            "ticker": "NVDA",
            "as_of": "2026-05-29",
            "source": "mock",
            "risk_state": "normal",
            "regime": "QUIET",
            "crowding_score": 0.1,
        }
    )
    assert graded["delivery_contract"]["contract"] == "V_D"
    assert graded["delivery_contract"]["verdict"] == "pass_with_caveats"
