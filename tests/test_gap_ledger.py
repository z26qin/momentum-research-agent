from __future__ import annotations

from pathlib import Path

from momentum_research_agent.models.schemas import (
    EvidenceCategory,
    GapCapability,
    GapState,
    VerificationReport,
    VerificationStatus,
    EvidenceVerdict,
)
from momentum_research_agent.state.gap_ledger import (
    append_from_verification,
    classify_gap,
    failure_brief,
    mark_consumed,
    open_gaps,
)


def _verification(*verdicts: EvidenceVerdict) -> VerificationReport:
    return VerificationReport(
        question="Is SMH crowding a crash?",
        overall_status="fail",
        summary="audit",
        verdicts=list(verdicts),
    )


def test_classify_momentum_capabilities() -> None:
    assert classify_gap("factor crowding in SMH") is GapCapability.CROWDING
    assert classify_gap("Daniel-Moskowitz unwind / crash") is GapCapability.UNWIND_CRASH
    assert classify_gap("engine snapshot is stale as_of") is GapCapability.ENGINE_FRESHNESS
    assert (
        classify_gap("claim", notes="No source_url or source_name")
        is GapCapability.SOURCE_QUALITY
    )
    assert (
        classify_gap("misc", category=EvidenceCategory.CROWDED_POSITIONING)
        is GapCapability.CROWDING
    )


def test_append_skips_verified_and_dedupes_open(tmp_path: Path) -> None:
    path = tmp_path / "gap_ledger.jsonl"
    rejected = EvidenceVerdict(
        evidence_id="e1",
        claim="crowding is elevated",
        status=VerificationStatus.REJECTED,
        notes="no url",
    )
    verified = EvidenceVerdict(
        evidence_id="e2",
        claim="ok",
        status=VerificationStatus.VERIFIED,
    )
    first = append_from_verification(path, _verification(rejected, verified), "sess-a")
    assert len(first) == 1
    assert first[0].capability is GapCapability.CROWDING
    assert first[0].state is GapState.OPEN
    assert append_from_verification(path, _verification(rejected), "sess-a") == []
    assert len(open_gaps(path)) == 1


def test_mark_consumed_closes_row(tmp_path: Path) -> None:
    path = tmp_path / "gap_ledger.jsonl"
    verdict = EvidenceVerdict(
        evidence_id="e1",
        claim="unchecked unwind",
        status=VerificationStatus.UNCHECKED,
    )
    append_from_verification(path, _verification(verdict), "sess-a")
    closed = mark_consumed(path, ["e1"], "sess-b")
    assert closed[0].state is GapState.CONSUMED
    assert closed[0].consumed_by == "sess-b"
    assert open_gaps(path) == []


def test_failure_brief_lists_open_then_consumed(tmp_path: Path) -> None:
    path = tmp_path / "gap_ledger.jsonl"
    append_from_verification(
        path,
        _verification(
            EvidenceVerdict(
                evidence_id="e1",
                claim="crowding is elevated",
                status=VerificationStatus.REJECTED,
                notes="no url",
            )
        ),
        "sess-a",
    )
    mark_consumed(path, ["e1"], "sess-b")
    append_from_verification(
        path,
        _verification(
            EvidenceVerdict(
                evidence_id="e2",
                claim="Daniel-Moskowitz unwind",
                status=VerificationStatus.UNCHECKED,
            )
        ),
        "sess-c",
    )
    brief = failure_brief(path)
    assert "OPEN unwind_crash" in brief
    assert "CONSUMED crowding" in brief
    assert "e2" in brief
    assert "e1" in brief


def test_session_engine_mock_and_unanswered_feed_cross_session_ledger(
    tmp_path: Path,
) -> None:
    from momentum_research_agent.models.schemas import GapEntry, GapKind

    path = tmp_path / "gap_ledger.jsonl"
    report = VerificationReport(
        question="Is this a crash?",
        overall_status="fail",
        summary="session ledger",
        verdicts=[
            EvidenceVerdict(
                evidence_id="e1",
                claim="crowding is elevated",
                status=VerificationStatus.REJECTED,
            )
        ],
        gaps=[
            GapEntry(
                kind=GapKind.REJECTED_EVIDENCE,
                claim="crowding is elevated",
                evidence_id="e1",
            ),
            GapEntry(
                kind=GapKind.ENGINE_MOCK,
                claim="engine_query(NVDA) returned labeled mock data.",
                notes="no snapshot",
            ),
            GapEntry(
                kind=GapKind.UNANSWERED_QUESTION,
                claim="Does FINRA SI confirm the crowding print?",
            ),
        ],
    )
    written = append_from_verification(path, report, "sess-a")
    ids = {item.evidence_id for item in written}
    assert "e1" in ids
    assert any(item.startswith("engine_mock:") for item in ids)
    assert any(item.startswith("unanswered:") for item in ids)
    caps = {item.capability for item in written}
    assert GapCapability.CROWDING in caps
    assert GapCapability.ENGINE_FRESHNESS in caps
    # rejected gap row is not duplicated from verdicts
    assert sum(1 for item in written if item.evidence_id == "e1") == 1
