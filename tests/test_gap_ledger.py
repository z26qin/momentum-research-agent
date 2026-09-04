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
