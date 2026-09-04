from __future__ import annotations

from momentum_research_agent.coordinator.followup import (
    FOLLOWUP_TITLE_PREFIX,
    already_followed_up,
    followup_specs,
)
from momentum_research_agent.models.schemas import (
    Evidence,
    EvidenceCategory,
    EvidenceStance,
    EvidenceVerdict,
    ResearchReport,
    Task,
    VerificationReport,
    VerificationStatus,
)


def _report(task_id: str, profile: str, claim: str) -> ResearchReport:
    return ResearchReport(
        task_id=task_id,
        title=f"{profile} view",
        agent_role=profile,
        findings=[
            Evidence(
                id="abcd1234",
                claim=claim,
                category=EvidenceCategory.MARKET_REGIME,
                stance=EvidenceStance.SUPPORTING,
                source_name="test",
                agent_id=task_id,
            )
        ],
        summary="n/a",
    )


def test_followup_specs_only_rejected_and_unchecked() -> None:
    report = _report("t1", "momentum_analyst", "Crowding is critical")
    verification = VerificationReport(
        question="q",
        overall_status="pass_with_caveats",
        summary="gaps",
        verdicts=[
            EvidenceVerdict(
                evidence_id="abcd1234",
                task_id="t1",
                claim="Crowding is critical",
                status=VerificationStatus.UNCHECKED,
                issues=["no source"],
            ),
            EvidenceVerdict(
                evidence_id="ok000001",
                task_id="t1",
                claim="Tape is quiet",
                status=VerificationStatus.VERIFIED,
            ),
            EvidenceVerdict(
                evidence_id="weak0001",
                task_id="t1",
                claim="Name-only source",
                status=VerificationStatus.WEAK,
            ),
        ],
    )
    specs = followup_specs("q", verification, {"t1": report})
    assert len(specs) == 1
    assert specs[0].profile == "momentum_analyst"
    assert specs[0].title.startswith(FOLLOWUP_TITLE_PREFIX)
    assert "abcd1234" in specs[0].assignment
    assert "ok000001" not in specs[0].assignment
    assert "weak0001" not in specs[0].assignment


def test_followup_caps_at_two_original_tasks() -> None:
    reports = {
        "a": _report("a", "momentum_analyst", "A"),
        "b": _report("b", "credit_analyst", "B"),
        "c": _report("c", "macro_analyst", "C"),
    }
    verification = VerificationReport(
        question="q",
        overall_status="fail",
        summary="many gaps",
        verdicts=[
            EvidenceVerdict(
                evidence_id="1",
                task_id="a",
                claim="A",
                status=VerificationStatus.REJECTED,
            ),
            EvidenceVerdict(
                evidence_id="2",
                task_id="b",
                claim="B",
                status=VerificationStatus.UNCHECKED,
            ),
            EvidenceVerdict(
                evidence_id="3",
                task_id="c",
                claim="C",
                status=VerificationStatus.REJECTED,
            ),
        ],
    )
    specs = followup_specs("q", verification, reports, max_tasks=2)
    assert len(specs) == 2
    assert {spec.original_task_id for spec in specs} == {"a", "b"}


def test_already_followed_up_detects_prefix() -> None:
    assert already_followed_up([]) is False
    assert already_followed_up([Task(title="Momentum state", assignment="x", profile="momentum_analyst")]) is False
    assert (
        already_followed_up(
            [Task(title="Follow-up: Crowding is critical", assignment="x", profile="momentum_analyst")]
        )
        is True
    )
