from __future__ import annotations

from datetime import timedelta

from momentum_research_agent.agents.audit import merge_verification, static_audit
from momentum_research_agent.models.schemas import (
    Evidence,
    EvidenceCategory,
    EvidenceStance,
    EvidenceVerdict,
    ResearchReport,
    VerificationReport,
    VerificationStatus,
    utcnow,
)


def _report(*items: Evidence, status: str = "complete") -> ResearchReport:
    return ResearchReport(
        task_id="task01",
        title="Momentum",
        agent_role="momentum_analyst",
        findings=list(items),
        summary="view",
        status=status,  # type: ignore[arg-type]
    )


def test_missing_source_is_unchecked() -> None:
    report = _report(
        Evidence(
            id="e1",
            claim="Crowding is extreme.",
            category=EvidenceCategory.CROWDED_POSITIONING,
            stance=EvidenceStance.SUPPORTING,
        )
    )
    audit = static_audit("q", [report])
    assert audit.verdicts[0].status is VerificationStatus.UNCHECKED
    assert audit.overall_status == "pass_with_caveats"
    assert "Crowding is extreme." in audit.unsupported_claims


def test_future_published_at_is_rejected() -> None:
    report = _report(
        Evidence(
            id="e2",
            claim="A print from the future.",
            category=EvidenceCategory.OTHER,
            stance=EvidenceStance.NEUTRAL,
            source_url="https://example.com/x",
            published_at=utcnow() + timedelta(days=3),
        )
    )
    audit = static_audit("q", [report])
    assert audit.verdicts[0].status is VerificationStatus.REJECTED
    assert audit.overall_status == "fail"


def test_empty_complete_report_is_missing_evidence() -> None:
    report = _report(status="complete")
    audit = static_audit("q", [report])
    assert audit.overall_status == "fail"
    assert any("empty findings" in item for item in audit.missing_evidence)


def test_cross_report_stance_conflict_downgrades() -> None:
    supporting = Evidence(
        id="e3",
        claim="Regime is crash-like.",
        category=EvidenceCategory.MARKET_REGIME,
        stance=EvidenceStance.SUPPORTING,
        source_url="https://example.com/a",
        confidence="high",
    )
    contradicting = Evidence(
        id="e4",
        claim="Regime is a healthy rotation.",
        category=EvidenceCategory.MARKET_REGIME,
        stance=EvidenceStance.CONTRADICTING,
        source_url="https://example.com/b",
        confidence="high",
    )
    left = _report(supporting)
    right = ResearchReport(
        task_id="task02",
        title="Credit",
        agent_role="credit_analyst",
        findings=[contradicting],
        summary="other view",
        status="complete",
    )
    audit = static_audit("q", [left, right])
    assert all(item.status is VerificationStatus.WEAK for item in audit.verdicts)
    assert audit.overall_status == "pass_with_caveats"


def test_merge_is_conservative_and_drops_unknown_ids() -> None:
    static = static_audit(
        "q",
        [
            _report(
                Evidence(
                    id="keep",
                    claim="Sourced claim.",
                    category=EvidenceCategory.OTHER,
                    stance=EvidenceStance.NEUTRAL,
                    source_url="https://example.com/ok",
                    confidence="high",
                )
            )
        ],
    )
    llm = VerificationReport(
        question="q",
        overall_status="pass",
        summary="LLM says all good.",
        verdicts=[
            EvidenceVerdict(
                evidence_id="keep",
                claim="Sourced claim.",
                status=VerificationStatus.VERIFIED,
                notes="rechecked",
                rechecked_source="https://example.com/ok",
            ),
            EvidenceVerdict(
                evidence_id="invented",
                claim="Hallucinated",
                status=VerificationStatus.VERIFIED,
                notes="ignore me",
            ),
        ],
    )
    merged = merge_verification(static, llm, "q")
    assert [item.evidence_id for item in merged.verdicts] == ["keep"]
    assert merged.verdicts[0].status is VerificationStatus.VERIFIED
    assert merged.verdicts[0].rechecked_source == "https://example.com/ok"


def test_json_round_trip_verification() -> None:
    audit = static_audit(
        "q",
        [
            _report(
                Evidence(
                    id="e5",
                    claim="Has a name only.",
                    category=EvidenceCategory.OTHER,
                    stance=EvidenceStance.NEUTRAL,
                    source_name="engine_query",
                )
            )
        ],
    )
    restored = VerificationReport.model_validate_json(audit.model_dump_json())
    assert restored.verdicts[0].status is VerificationStatus.WEAK
    assert restored.model_dump() == audit.model_dump()
