"""Delivery contract V_D attached to every engine_query payload.

Only a live run_mvp assessment that independently re-checks as_of,
risk_state, and fingerprint may verdict=pass. File snapshots and
local_dm cannot pass. Crowding / unwind assertions stay on the verifier.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Literal

from pydantic import BaseModel, Field

from momentum_research_agent.tools.engine_adapter import DM_PRIMARY_STATES

Verdict = Literal["pass", "pass_with_caveats", "fail"]
AS_OF_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class DeliveryContract(BaseModel):
    verdict: Verdict
    pipeline_run: bool
    source: str
    as_of: str | None = None
    requested_as_of: str | None = None
    fingerprint: str | None = None
    delivery_hash: str | None = None
    notes: list[str] = Field(default_factory=list)


def attach_contract(payload: dict[str, Any], contract: DeliveryContract) -> dict[str, Any]:
    out = dict(payload)
    out["pipeline_run"] = contract.pipeline_run
    out["delivery_hash"] = contract.delivery_hash
    out["delivery_contract"] = contract.model_dump()
    return out


def delivery_hash(assessment: dict[str, Any]) -> str:
    """Re-derive a hash from published assessment fields. Does not import src.mvp."""
    seed = {
        "as_of": str(assessment.get("as_of_date") or "")[:10],
        "risk_state": assessment.get("overall_risk_state"),
        "unwind": assessment.get("mechanical_unwind_state"),
        "fingerprint": assessment.get("full_run_fingerprint"),
        "mechanism_scores": assessment.get("mechanism_scores"),
    }
    payload = json.dumps(seed, sort_keys=True, default=str, allow_nan=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def pipeline_pass(
    *,
    as_of: str | None,
    requested_as_of: str | None,
    fingerprint: str | None,
    notes: list[str] | None = None,
    delivery_hash_value: str | None = None,
) -> DeliveryContract:
    return DeliveryContract(
        verdict="pass",
        pipeline_run=True,
        source="run_mvp",
        as_of=as_of,
        requested_as_of=requested_as_of,
        fingerprint=fingerprint,
        delivery_hash=delivery_hash_value,
        notes=notes or ["State produced by live run_mvp via scripts/run_monitor.py."],
    )


def not_pass(
    *,
    verdict: Verdict,
    source: str,
    as_of: str | None = None,
    requested_as_of: str | None = None,
    notes: list[str] | None = None,
    pipeline_run: bool = False,
    fingerprint: str | None = None,
    delivery_hash_value: str | None = None,
) -> DeliveryContract:
    return DeliveryContract(
        verdict=verdict,
        pipeline_run=pipeline_run,
        source=source,
        as_of=as_of,
        requested_as_of=requested_as_of,
        fingerprint=fingerprint,
        delivery_hash=delivery_hash_value,
        notes=notes or [],
    )


def verify_live_delivery(
    assessment: dict[str, Any],
    requested_as_of: str | None,
    *,
    extra_notes: list[str] | None = None,
) -> DeliveryContract:
    """Judge a live run_mvp artifact independently of subprocess exit.

    Checks as_of format + match, risk_state ∈ DM primary states, and a
    present fingerprint. Recomputes delivery_hash from those published
    fields. Does not attack crowding/unwind claims.
    """
    as_of = str(assessment.get("as_of_date") or "")[:10]
    risk = assessment.get("overall_risk_state")
    fingerprint = str(assessment.get("full_run_fingerprint") or "").strip() or None
    derived = delivery_hash(assessment)
    notes = list(extra_notes or [])
    problems: list[str] = []
    if not AS_OF_RE.match(as_of):
        problems.append(f"as_of {as_of!r} is not YYYY-MM-DD")
    if requested_as_of and as_of != requested_as_of[:10]:
        problems.append(f"as_of {as_of!r} != requested {requested_as_of[:10]!r}")
    if risk not in DM_PRIMARY_STATES:
        problems.append(f"risk_state {risk!r} not in {DM_PRIMARY_STATES}")
    if fingerprint is None or len(fingerprint) < 8:
        problems.append("full_run_fingerprint missing or too short")
    if problems:
        return not_pass(
            verdict="fail",
            source="run_mvp",
            as_of=as_of or None,
            requested_as_of=requested_as_of,
            fingerprint=fingerprint,
            delivery_hash_value=derived,
            pipeline_run=True,
            notes=[
                "V_D rejected a live run_mvp artifact.",
                *notes,
                *problems,
            ],
        )
    return pipeline_pass(
        as_of=as_of,
        requested_as_of=requested_as_of,
        fingerprint=fingerprint,
        delivery_hash_value=derived,
        notes=[
            "V_D re-checked as_of, risk_state, and fingerprint on the run_mvp artifact.",
            *notes,
        ],
    )
