from __future__ import annotations

from momentum_research_agent.coordinator.gap_tasks import GAP_TITLE_PREFIX, gap_task_specs
from momentum_research_agent.models.schemas import (
    GapCapability,
    GapRecord,
    TaskKind,
    VerificationStatus,
)


def _gap(evidence_id: str, capability: GapCapability, claim: str) -> GapRecord:
    return GapRecord(
        evidence_id=evidence_id,
        claim=claim,
        status=VerificationStatus.REJECTED,
        capability=capability,
        session_id="old",
    )


def test_gap_task_specs_group_and_cap() -> None:
    gaps = [
        _gap("a", GapCapability.UNWIND_CRASH, "unwind starting"),
        _gap("b", GapCapability.UNWIND_CRASH, "crash frequency up"),
        _gap("c", GapCapability.CROWDING, "crowding still high"),
        _gap("d", GapCapability.SOURCE_QUALITY, "no url"),
    ]
    specs = gap_task_specs("Is this a crash?", gaps, max_tasks=2)
    assert len(specs) == 2
    assert specs[0].kind is TaskKind.GAP
    assert specs[0].title.startswith(GAP_TITLE_PREFIX)
    assert specs[0].profile == "momentum_analyst"
    assert set(specs[0].evidence_ids) == {"a", "b"}
    assert specs[1].profile == "flow_analyst"
    assert "Current research question" in specs[0].assignment


def test_gap_task_specs_empty() -> None:
    assert gap_task_specs("q", [], max_tasks=2) == []
    assert gap_task_specs("q", [_gap("a", GapCapability.OTHER, "x")], max_tasks=0) == []
