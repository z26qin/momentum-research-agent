"""Cross-session ledger of rejected/unchecked momentum evidence.

This is the first half of the closed loop: observe verification failures,
classify them into momentum-factor capabilities, and persist them outside
a single session. The next run may consume open rows as GAP tasks.
It is not an in-session unbounded follow-up loop.
"""

from __future__ import annotations

from pathlib import Path

from momentum_research_agent.config import reports_root
from momentum_research_agent.models.schemas import (
    EvidenceCategory,
    GapCapability,
    GapRecord,
    GapState,
    ResearchReport,
    VerificationReport,
    VerificationStatus,
)
from momentum_research_agent.state.persistence import append_jsonl, read_jsonl

LEDGER_NAME = "gap_ledger.jsonl"
GAP_STATUSES = frozenset({VerificationStatus.REJECTED, VerificationStatus.UNCHECKED})

_CROWD = ("crowd", "positioning", "short interest", "etf flow")
_UNWIND = ("unwind", "crash", "daniel", "moskowitz", "panic", "bear market")
_ENGINE = ("engine", "snapshot", "as_of", "mock data")
_SOURCE = ("source", "url", "no retrievable", "unpublished")


def ledger_path(project_root: Path | None = None) -> Path:
    return reports_root(project_root) / LEDGER_NAME


def classify_gap(
    claim: str,
    notes: str = "",
    issues: list[str] | None = None,
    category: EvidenceCategory | None = None,
) -> GapCapability:
    blob = " ".join([claim, notes, *(issues or [])]).lower()
    if category is EvidenceCategory.CROWDED_POSITIONING or any(token in blob for token in _CROWD):
        return GapCapability.CROWDING
    if any(token in blob for token in _UNWIND):
        return GapCapability.UNWIND_CRASH
    if any(token in blob for token in _ENGINE):
        return GapCapability.ENGINE_FRESHNESS
    if any(token in blob for token in _SOURCE):
        return GapCapability.SOURCE_QUALITY
    if category is EvidenceCategory.MARKET_REGIME:
        return GapCapability.UNWIND_CRASH
    return GapCapability.OTHER


def load_ledger(path: Path) -> dict[str, GapRecord]:
    """Last write for an evidence_id wins."""
    by_id: dict[str, GapRecord] = {}
    for raw in read_jsonl(path):
        record = GapRecord.model_validate(raw)
        by_id[record.evidence_id] = record
    return by_id


def open_gaps(path: Path) -> list[GapRecord]:
    return [item for item in load_ledger(path).values() if item.state is GapState.OPEN]


def failure_brief(
    path: Path,
    *,
    max_open: int = 4,
    max_consumed: int = 2,
) -> str:
    """Compact ledger digest for the next decompose call.

    Open rows first (the next run still sees them before seed_from_ledger
    consumes a subset). Recently consumed rows are a short memory of what
    was already retried.
    """
    by_id = load_ledger(path)
    if not by_id:
        return ""
    open_rows = [item for item in by_id.values() if item.state is GapState.OPEN]
    consumed = [item for item in by_id.values() if item.state is GapState.CONSUMED]
    open_rows = open_rows[-max_open:]
    consumed = consumed[-max_consumed:]
    lines: list[str] = []
    for item in open_rows:
        lines.append(_brief_line("OPEN", item))
    for item in consumed:
        lines.append(_brief_line("CONSUMED", item))
    return "\n".join(lines)


def _brief_line(label: str, item: GapRecord) -> str:
    claim = item.claim.strip().replace("\n", " ")
    if len(claim) > 80:
        claim = claim[:77] + "..."
    extra = f" ({item.notes})" if item.notes else ""
    return (
        f"{label} {item.capability.value} [{item.status.value}] "
        f"{item.evidence_id}: {claim}{extra}"
    )


def append_from_verification(
    path: Path,
    verification: VerificationReport,
    session_id: str,
    reports: dict[str, ResearchReport] | None = None,
) -> list[GapRecord]:
    reports = reports or {}
    existing = load_ledger(path)
    written: list[GapRecord] = []
    for verdict in verification.verdicts:
        if verdict.status not in GAP_STATUSES:
            continue
        prior = existing.get(verdict.evidence_id)
        if prior is not None and prior.state is GapState.OPEN:
            continue
        category = None
        profile = None
        if verdict.task_id and verdict.task_id in reports:
            report = reports[verdict.task_id]
            profile = report.agent_role
            for item in report.findings:
                if item.id == verdict.evidence_id:
                    category = item.category
                    break
        record = GapRecord(
            evidence_id=verdict.evidence_id,
            claim=verdict.claim,
            status=verdict.status,
            capability=classify_gap(
                verdict.claim, verdict.notes, verdict.issues, category
            ),
            session_id=session_id,
            task_id=verdict.task_id,
            profile=profile,
            notes=verdict.notes,
            issues=list(verdict.issues),
        )
        append_jsonl(path, record.model_dump(mode="json"))
        existing[record.evidence_id] = record
        written.append(record)
    return written


def mark_consumed(path: Path, evidence_ids: list[str], session_id: str) -> list[GapRecord]:
    existing = load_ledger(path)
    updated: list[GapRecord] = []
    for evidence_id in evidence_ids:
        record = existing.get(evidence_id)
        if record is None or record.state is GapState.CONSUMED:
            continue
        consumed = record.model_copy(
            update={"state": GapState.CONSUMED, "consumed_by": session_id}
        )
        append_jsonl(path, consumed.model_dump(mode="json"))
        existing[evidence_id] = consumed
        updated.append(consumed)
    return updated
