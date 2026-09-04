from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from momentum_research_agent.models.schemas import (
    Evidence,
    EvidenceCategory,
    EvidenceStance,
    ResearchReport,
)


def test_valid_evidence_parses() -> None:
    item = Evidence(
        claim="NVDA 20d return is negative while SMH breadth is mixed.",
        category=EvidenceCategory.MARKET_REGIME,
        stance=EvidenceStance.SUPPORTING,
        source_url="https://example.com/nvda",
        source_name="example",
        confidence="high",
        agent_id="abcd1234",
    )
    assert item.category is EvidenceCategory.MARKET_REGIME
    assert item.stance is EvidenceStance.SUPPORTING
    assert item.id


def test_invalid_stance_and_category_rejected() -> None:
    with pytest.raises(ValidationError):
        Evidence(claim="x", category="market_regime", stance="bullish")
    with pytest.raises(ValidationError):
        Evidence(claim="x", category="vibes", stance="supporting")


def test_empty_evidence_insufficient_status_allowed() -> None:
    report = ResearchReport(
        task_id="abcd1234",
        title="Credit overlay",
        agent_role="credit_analyst",
        findings=[],
        summary="No usable CDS print.",
        unanswered_questions=["Where is the 5y CDS time series?"],
        contradictions=[],
        status="insufficient_evidence",
    )
    assert report.findings == []
    assert report.status == "insufficient_evidence"


def test_json_round_trip_preserves_fields() -> None:
    report = ResearchReport(
        task_id="abcd1234",
        title="Momentum state",
        agent_role="momentum_analyst",
        findings=[
            Evidence(
                id="ev01ev01",
                claim="Crowding score is elevated.",
                category=EvidenceCategory.CROWDED_POSITIONING,
                stance=EvidenceStance.SUPPORTING,
                source_name="engine_query",
                confidence="medium",
                agent_id="abcd1234",
            ),
            Evidence(
                id="ev02ev02",
                claim="No crash-frequency spike.",
                category=EvidenceCategory.CONTRADICTING_EVIDENCE,
                stance=EvidenceStance.CONTRADICTING,
                source_name="engine_query",
                confidence="low",
                agent_id="abcd1234",
            ),
        ],
        summary="Crowded but not a crash.",
        unanswered_questions=["Is FINRA SI stale?"],
        contradictions=["Crowding elevated vs crash frequency quiet."],
        status="partial",
    )
    restored = ResearchReport.model_validate_json(report.model_dump_json())
    assert restored.model_dump() == report.model_dump()
    as_dict = json.loads(report.model_dump_json())
    assert as_dict["findings"][0]["category"] == "crowded_positioning"
    assert as_dict["contradictions"][0].startswith("Crowding")
