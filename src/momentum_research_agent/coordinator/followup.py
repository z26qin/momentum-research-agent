"""Bounded follow-up research for rejected / unchecked evidence.

One round only. Coordinator creates ordinary TaskBoard tasks; there is no
AgentBus. Verified and weak-as-ok items are left alone.
"""

from __future__ import annotations

from dataclasses import dataclass

from momentum_research_agent.models.schemas import (
    ResearchReport,
    Task,
    VerificationReport,
    VerificationStatus,
)
from momentum_research_agent.tools import RESEARCH_PROFILES

FOLLOWUP_TITLE_PREFIX = "Follow-up:"
FOLLOWUP_STATUSES = frozenset(
    {VerificationStatus.REJECTED, VerificationStatus.UNCHECKED}
)
DEFAULT_FOLLOWUP_PROFILE = "momentum_analyst"
MAX_FOLLOWUP_TASKS = 2


@dataclass(frozen=True)
class FollowUpSpec:
    title: str
    assignment: str
    profile: str
    original_task_id: str | None
    evidence_ids: tuple[str, ...]


def already_followed_up(tasks: list[Task]) -> bool:
    return any(task.title.startswith(FOLLOWUP_TITLE_PREFIX) for task in tasks)


def followup_specs(
    question: str,
    verification: VerificationReport,
    reports: dict[str, ResearchReport],
    *,
    max_tasks: int = MAX_FOLLOWUP_TASKS,
) -> list[FollowUpSpec]:
    grouped: dict[str, list] = {}
    for verdict in verification.verdicts:
        if verdict.status not in FOLLOWUP_STATUSES:
            continue
        key = verdict.task_id or "_ungrouped"
        grouped.setdefault(key, []).append(verdict)
    if not grouped or max_tasks <= 0:
        return []

    specs: list[FollowUpSpec] = []
    for original_id, verdicts in list(grouped.items())[:max_tasks]:
        report = reports.get(original_id)
        profile = (
            report.agent_role.removesuffix(".md")
            if report is not None
            else DEFAULT_FOLLOWUP_PROFILE
        )
        if profile not in RESEARCH_PROFILES:
            profile = DEFAULT_FOLLOWUP_PROFILE
        original_title = report.title if report is not None else "ungrouped evidence"
        lines = []
        for verdict in verdicts:
            issues = "; ".join(verdict.issues) if verdict.issues else verdict.notes
            lines.append(
                f"- [{verdict.status.value}] {verdict.evidence_id}: {verdict.claim}"
                + (f"\n  issues: {issues}" if issues else "")
            )
        assignment = (
            "The independent verifier marked the following evidence as "
            "rejected or unchecked. Re-investigate with retrieved sources "
            "(URLs and published dates when they exist). Do not restate the "
            "original claim without new retrieval.\n\n"
            f"Research question:\n{question}\n\n"
            f"Original task: {original_title} ({profile})\n\n"
            "Evidence to repair:\n"
            + "\n".join(lines)
            + "\n\nProduce a ResearchReport. Prefer new findings that replace "
            "or qualify these claims. Leave verified evidence alone."
        )
        claim = verdicts[0].claim.strip().replace("\n", " ")
        short = claim if len(claim) <= 48 else claim[:45] + "..."
        specs.append(
            FollowUpSpec(
                title=f"{FOLLOWUP_TITLE_PREFIX} {short}",
                assignment=assignment,
                profile=profile,
                original_task_id=None if original_id == "_ungrouped" else original_id,
                evidence_ids=tuple(item.evidence_id for item in verdicts),
            )
        )
    return specs
