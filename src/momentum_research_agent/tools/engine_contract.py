"""Delivery contract V_D for momentum engine_query payloads.

A live `run_monitor.py` assessment (pipeline_run=True) can pass. File
snapshots — including the frozen cases under fixtures/engine — local_dm,
and mock cannot pass without caveats.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field

from momentum_research_agent.tools.engine_adapter import (
    DM_PRIMARY_STATES,
    MECHANICAL_UNWIND_REGIMES,
)

REQUIRED_FIELDS = ("ticker", "as_of", "source", "risk_state", "regime", "crowding_score")
_DM = frozenset(DM_PRIMARY_STATES)
_REGIMES = frozenset(MECHANICAL_UNWIND_REGIMES)


class DeliveryContract(BaseModel):
    verdict: Literal["pass", "pass_with_caveats", "fail"]
    domain: str = "momentum_tail_risk"
    contract: str = "V_D"
    missing: list[str] = Field(default_factory=list)
    invalid: list[str] = Field(default_factory=list)
    caveats: list[str] = Field(default_factory=list)


def grade_engine_payload(
    payload: dict[str, Any],
    *,
    requested_end: str | None = None,
) -> DeliveryContract:
    missing: list[str] = []
    invalid: list[str] = []
    caveats: list[str] = []

    for field in REQUIRED_FIELDS:
        if field not in payload:
            missing.append(field)

    ticker = payload.get("ticker")
    if "ticker" in payload and not (isinstance(ticker, str) and ticker.strip()):
        invalid.append("ticker")

    as_of = payload.get("as_of")
    if "as_of" in payload and not (isinstance(as_of, str) and as_of.strip()):
        invalid.append("as_of")

    source = payload.get("source")
    if "source" in payload:
        if not (isinstance(source, str) and source.strip()):
            invalid.append("source")
        elif source == "mock":
            caveats.append("source=mock; values are synthetic, not a live engine run")
        elif source == "local_dm":
            caveats.append("source=local_dm; not a PIT parquet pipeline run")
        elif source == "momentum-tail-risk-monitor" and not payload.get("pipeline_run"):
            caveats.append(
                "file snapshot adapter; not a live run_monitor.py PIT run"
            )

    risk_state = payload.get("risk_state")
    if "risk_state" in payload:
        if not isinstance(risk_state, str) or not risk_state.strip():
            invalid.append("risk_state")
        elif risk_state == "unknown":
            caveats.append("risk_state=unknown")
        elif risk_state not in _DM:
            invalid.append(f"risk_state={risk_state}")

    regime = payload.get("regime")
    if "regime" in payload:
        if not isinstance(regime, str) or not regime.strip():
            invalid.append("regime")
        elif regime == "unknown":
            caveats.append("regime=unknown")
        elif regime in _DM:
            caveats.append("regime reused a DM risk_state instead of an unwind regime")
        elif regime not in _REGIMES:
            invalid.append(f"regime={regime}")

    crowding = payload.get("crowding_score")
    if "crowding_score" in payload:
        if crowding is None:
            caveats.append("crowding_score is null")
        elif isinstance(crowding, bool) or not isinstance(crowding, (int, float)):
            invalid.append("crowding_score")
        elif crowding > 1.5:
            caveats.append("crowding_score looks like a 0-100 scale, expected 0-1")

    if payload.get("as_of_match") is False:
        caveats.append("as_of_match=false; snapshot date does not match the requested end")

    requested = requested_end or (str(payload.get("end")) if payload.get("end") else None)
    as_of_day = _parse_day(as_of)
    requested_day = _parse_day(requested)
    if as_of_day is not None and requested_day is not None and as_of_day != requested_day:
        if "as_of_match=false" not in " ".join(caveats):
            caveats.append(f"as_of={as_of_day.isoformat()} != requested end={requested_day.isoformat()}")

    if missing or invalid:
        verdict: Literal["pass", "pass_with_caveats", "fail"] = "fail"
    elif caveats:
        verdict = "pass_with_caveats"
    else:
        verdict = "pass"
    return DeliveryContract(
        verdict=verdict,
        missing=missing,
        invalid=invalid,
        caveats=caveats,
    )


def attach_delivery_contract(
    payload: dict[str, Any],
    *,
    requested_end: str | None = None,
) -> dict[str, Any]:
    graded = dict(payload)
    graded["delivery_contract"] = grade_engine_payload(
        graded, requested_end=requested_end
    ).model_dump()
    return graded


def _parse_day(value: object) -> date | None:
    if not isinstance(value, str) or len(value) < 10:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None
