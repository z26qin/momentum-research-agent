from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from momentum_research_agent.coordinator.coordinator import Coordinator
from momentum_research_agent.coordinator.gap_seed import load_rows
from momentum_research_agent.models.schemas import (
    EvidenceVerdict,
    GapEntry,
    GapKind,
    GapLedgerStatus,
    Task,
    TaskKind,
    VerificationReport,
    VerificationStatus,
)
from momentum_research_agent.state.reports import persist_verification_report


def _coordinator(tmp_path: Path, session: str) -> Coordinator:
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace()))
    return Coordinator(
        session_dir=tmp_path / session,
        client=client,  # type: ignore[arg-type]
        question="Is the NVDA selloff a crash?",
        project_root=tmp_path,
    )


def _engine_mock_report(*, task_id: str | None = None) -> VerificationReport:
    return VerificationReport(
        question="Is the NVDA selloff a crash?",
        overall_status="pass_with_caveats",
        summary="engine returned labeled mock",
        gaps=[
            GapEntry(
                kind=GapKind.ENGINE_MOCK,
                claim="engine_query(NVDA) returned labeled mock data.",
                notes="Replay uses the stored observation; no live snapshot was attached.",
                evidence_id="engine_mock:NVDA",
                task_id=task_id,
            )
        ],
    )


def _complete(coordinator: Coordinator, task: Task) -> None:
    coordinator.board.activate(task.id)
    coordinator.board.complete(task.id, "gap research")


def test_engine_mock_reopens_after_unresolved_verify(tmp_path: Path) -> None:
    session_a = _coordinator(tmp_path, "session-a")
    persist_verification_report(session_a.session_dir, _engine_mock_report())
    session_a.record_gaps()
    assert load_rows(tmp_path)[0].status is GapLedgerStatus.OPEN

    session_b = _coordinator(tmp_path, "session-b")
    planted = session_b.seed_from_ledger()
    assert len(planted) == 1
    assert planted[0].kind is TaskKind.GAP
    assert load_rows(tmp_path)[0].status is GapLedgerStatus.CONSUMED

    _complete(session_b, planted[0])
    session_b.verification = _engine_mock_report(task_id=planted[0].id)
    persist_verification_report(session_b.session_dir, session_b.verification)
    session_b.record_gaps()
    session_b.resolve_planted_gaps()

    row = load_rows(tmp_path)[0]
    assert row.evidence_id == "engine_mock:NVDA"
    assert row.status is GapLedgerStatus.OPEN
    assert row.consumed_session_id == session_b.board.session_id
    assert row.consumed_task_id == planted[0].id


def test_verified_gap_closes_and_is_not_replanted(tmp_path: Path) -> None:
    session_a = _coordinator(tmp_path, "session-a")
    persist_verification_report(session_a.session_dir, _engine_mock_report())
    session_a.record_gaps()

    session_b = _coordinator(tmp_path, "session-b")
    planted = session_b.seed_from_ledger()
    _complete(session_b, planted[0])
    session_b.verification = VerificationReport(
        question="Is the NVDA selloff a crash?",
        overall_status="pass",
        summary="live snapshot replaced the mock",
        verdicts=[
            EvidenceVerdict(
                evidence_id="ev-live",
                task_id=planted[0].id,
                claim="engine_query(NVDA) used a live snapshot.",
                status=VerificationStatus.VERIFIED,
            )
        ],
        gaps=[],
    )
    persist_verification_report(session_b.session_dir, session_b.verification)
    session_b.record_gaps()
    session_b.resolve_planted_gaps()

    row = load_rows(tmp_path)[0]
    assert row.status is GapLedgerStatus.CLOSED
    assert row.consumed_task_id == planted[0].id

    session_c = _coordinator(tmp_path, "session-c")
    assert session_c.seed_from_ledger() == []
    assert load_rows(tmp_path)[0].status is GapLedgerStatus.CLOSED
    assert all(task.kind is not TaskKind.GAP for task in session_c.board.tasks)


def test_rejected_gap_task_reopens(tmp_path: Path) -> None:
    session_a = _coordinator(tmp_path, "session-a")
    persist_verification_report(session_a.session_dir, _engine_mock_report())
    session_a.record_gaps()

    session_b = _coordinator(tmp_path, "session-b")
    planted = session_b.seed_from_ledger()
    _complete(session_b, planted[0])
    session_b.verification = VerificationReport(
        question="Is the NVDA selloff a crash?",
        overall_status="fail",
        summary="gap task evidence was rejected",
        verdicts=[
            EvidenceVerdict(
                evidence_id="ev-bad",
                task_id=planted[0].id,
                claim="crowding print is still unsourced.",
                status=VerificationStatus.REJECTED,
            )
        ],
        gaps=[
            GapEntry(
                kind=GapKind.REJECTED_EVIDENCE,
                claim="crowding print is still unsourced.",
                evidence_id="ev-bad",
                task_id=planted[0].id,
                status=VerificationStatus.REJECTED,
            )
        ],
    )
    session_b.resolve_planted_gaps()
    assert load_rows(tmp_path)[0].status is GapLedgerStatus.OPEN
