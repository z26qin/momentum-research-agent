"""Delivery contract V_D attached to every engine_query payload.

Only a live run_mvp subprocess (pipeline_run=True) may verdict=pass.
File snapshots and local_dm cannot pass.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

Verdict = Literal["pass", "pass_with_caveats", "fail"]


class DeliveryContract(BaseModel):
    verdict: Verdict
    pipeline_run: bool
    source: str
    as_of: str | None = None
    requested_as_of: str | None = None
    fingerprint: str | None = None
    notes: list[str] = Field(default_factory=list)


def attach_contract(payload: dict[str, Any], contract: DeliveryContract) -> dict[str, Any]:
    out = dict(payload)
    out["pipeline_run"] = contract.pipeline_run
    out["delivery_contract"] = contract.model_dump()
    return out


def pipeline_pass(
    *,
    as_of: str | None,
    requested_as_of: str | None,
    fingerprint: str | None,
    notes: list[str] | None = None,
) -> DeliveryContract:
    return DeliveryContract(
        verdict="pass",
        pipeline_run=True,
        source="run_mvp",
        as_of=as_of,
        requested_as_of=requested_as_of,
        fingerprint=fingerprint,
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
) -> DeliveryContract:
    return DeliveryContract(
        verdict=verdict,
        pipeline_run=pipeline_run,
        source=source,
        as_of=as_of,
        requested_as_of=requested_as_of,
        notes=notes or [],
    )
