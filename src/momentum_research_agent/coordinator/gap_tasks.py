"""Turn open ledger gaps into a bounded set of next-run research tasks.

Capped. Not an in-session follow-up loop. GAP tasks are distinct from
FOLLOWUP so already_followed_up() is unaffected.
"""

from __future__ import annotations

from dataclasses import dataclass

from momentum_research_agent.models.schemas import (
    GapCapability,
    GapRecord,
    TaskKind,
)
from momentum_research_agent.tools import RESEARCH_PROFILES

MAX_GAP_SEED_TASKS = 2
DEFAULT_GAP_PROFILE = "momentum_analyst"
GAP_TITLE_PREFIX = "Gap:"

_PROFILE_FOR_CAPABILITY = {
    GapCapability.CROWDING: "flow_analyst",
    GapCapability.UNWIND_CRASH: "momentum_analyst",
    GapCapability.ENGINE_FRESHNESS: "momentum_analyst",
    GapCapability.SOURCE_QUALITY: "momentum_analyst",
    GapCapability.OTHER: "momentum_analyst",
}


@dataclass(frozen=True)
class GapTaskSpec:
    title: str
    assignment: str
    profile: str
    evidence_ids: tuple[str, ...]
    kind: TaskKind = TaskKind.GAP


def _profile(capability: GapCapability) -> str:
    name = _PROFILE_FOR_CAPABILITY.get(capability, DEFAULT_GAP_PROFILE)
    return name if name in RESEARCH_PROFILES else DEFAULT_GAP_PROFILE


def gap_task_specs(
    question: str,
    gaps: list[GapRecord],
    *,
    max_tasks: int = MAX_GAP_SEED_TASKS,
) -> list[GapTaskSpec]:
    if max_tasks <= 0 or not gaps:
        return []
    grouped: dict[GapCapability, list[GapRecord]] = {}
    for gap in gaps:
        grouped.setdefault(gap.capability, []).append(gap)
    ranked = sorted(
        grouped.items(),
        key=lambda item: (
            0 if item[0] is GapCapability.UNWIND_CRASH else 1,
            -len(item[1]),
        ),
    )
    specs: list[GapTaskSpec] = []
    for capability, records in ranked[:max_tasks]:
        lines = [
            f"- [{item.status.value}] {item.evidence_id}: {item.claim}"
            + (f" ({item.notes})" if item.notes else "")
            for item in records
        ]
        assignment = (
            "Prior sessions left these momentum-factor claims rejected or "
            "unchecked. Re-investigate with retrieved sources. Do not restate "
            "the original claim without new evidence.\n\n"
            f"Current research question:\n{question}\n\n"
            f"Capability: {capability.value}\n\n"
            "Open gaps:\n"
            + "\n".join(lines)
        )
        short = records[0].claim.strip().replace("\n", " ")
        title_claim = short if len(short) <= 48 else short[:45] + "..."
        specs.append(
            GapTaskSpec(
                title=f"{GAP_TITLE_PREFIX} {capability.value} / {title_claim}",
                assignment=assignment,
                profile=_profile(capability),
                evidence_ids=tuple(item.evidence_id for item in records),
            )
        )
    return specs
