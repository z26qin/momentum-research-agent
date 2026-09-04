"""Query the deterministic momentum tail-risk engine.

Live path: subprocess scripts/run_monitor.py → run_mvp. JSON snapshots and
local_dm are fail-closed fallbacks and cannot V_D pass.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from momentum_research_agent.tools.engine_adapter import (
    DM_BEAR_STATES,
    DM_PRIMARY_STATES,
    MECHANICAL_UNWIND_REGIMES,
    load_engine_state,
    normalize_engine_payload,
)
from momentum_research_agent.tools.engine_contract import (
    attach_contract,
    not_pass,
    pipeline_pass,
)
from momentum_research_agent.tools.engine_pipeline import QUERY_TIMEOUT_S, run_pipeline
from momentum_research_agent.tools.local_dm import score_local_dm
from momentum_research_agent.tools.registry import get_tool_context, register_tool


def _mock_state(
    ticker: str,
    start: str | None,
    end: str | None,
    *,
    reason: str,
) -> dict[str, object]:
    seed = hashlib.sha256(f"{ticker}|{start}|{end}".encode()).digest()
    risk_state = DM_PRIMARY_STATES[seed[1] % len(DM_PRIMARY_STATES)]
    regime = MECHANICAL_UNWIND_REGIMES[seed[0] % len(MECHANICAL_UNWIND_REGIMES)]
    freq = round(0.04 + (seed[2] / 255.0) * 0.28, 3)
    return {
        "ticker": ticker.upper(),
        "start": start,
        "end": end,
        "as_of": end or datetime.now(timezone.utc).date().isoformat(),
        "source": "mock",
        "scope": "mock",
        "risk_state": risk_state,
        "regime": regime,
        "conditional_crash_frequency": freq,
        "dm_bear_market_indicator": risk_state in DM_BEAR_STATES,
        "crowding_score": round(0.2 + (seed[3] / 255.0) * 0.7, 3),
        "note": reason,
    }


def _engine_dir_forced_missing() -> bool:
    raw = os.environ.get("MOMENTUM_ENGINE_DIR", "").strip()
    return bool(raw) and not Path(raw).expanduser().is_dir()


def _project_root() -> Path | None:
    try:
        return get_tool_context().project_root
    except RuntimeError:
        return None


def _from_assessment(
    assessment: dict,
    ticker: str,
    start: str | None,
    end: str | None,
    root: Path | None,
) -> dict:
    path = (root / "outputs" / "pipeline_runs" / f"{assessment.get('as_of_date')}.json") if root else Path(
        f"run_mvp:{assessment.get('as_of_date')}"
    )
    payload = normalize_engine_payload(assessment, ticker, path, start=start, end=end)
    payload["source"] = "run_mvp"
    payload["note"] = (
        "Live run_mvp via scripts/run_monitor.py. Market/book-level, not a ticker API. "
        "This path does not read structured_snapshot.json."
    )
    payload["full_run_fingerprint"] = assessment.get("full_run_fingerprint")
    return payload


@register_tool(
    name="engine_query",
    description=(
        "Query the deterministic momentum tail-risk engine for Daniel–Moskowitz "
        "risk state (normal | bear_low_volatility | panic_elevated), mechanical "
        "unwind regime, and crowding overlays. Prefers a live run_mvp subprocess "
        "(scripts/run_monitor.py). File snapshots and local DM cannot V_D pass. "
        "The engine is market/book-level, not a single-name API."
    ),
    parameters={
        "type": "object",
        "properties": {
            "ticker": {
                "type": "string",
                "description": "US equity ticker for context, e.g. NVDA or SMH.",
            },
            "start": {
                "type": "string",
                "description": "Optional start date YYYY-MM-DD (query context only).",
            },
            "end": {
                "type": "string",
                "description": "Optional as-of date YYYY-MM-DD used to select a snapshot.",
            },
        },
        "required": ["ticker"],
    },
)
async def engine_query(ticker: str, start: str | None = None, end: str | None = None) -> str:
    project_root = _project_root()
    requested = end
    forced_missing = _engine_dir_forced_missing()
    if requested and not forced_missing:
        run = await asyncio.to_thread(
            run_pipeline,
            requested,
            project_root=project_root,
            timeout_s=QUERY_TIMEOUT_S,
        )
        if run.ok and run.assessment is not None:
            payload = _from_assessment(run.assessment, ticker, start, end, run.root)
            as_of = str(run.assessment.get("as_of_date") or "")[:10]
            stale = bool(requested and as_of and requested != as_of)
            if stale:
                contract = not_pass(
                    verdict="pass_with_caveats",
                    source="run_mvp",
                    as_of=as_of,
                    requested_as_of=requested,
                    pipeline_run=True,
                    notes=["run_mvp as_of did not match the requested date."],
                )
            else:
                contract = pipeline_pass(
                    as_of=as_of,
                    requested_as_of=requested,
                    fingerprint=str(run.assessment.get("full_run_fingerprint") or "") or None,
                )
            return json.dumps(attach_contract(payload, contract), indent=2)

    if forced_missing:
        live = None
    else:
        live = load_engine_state(ticker, start, end, project_root=project_root)
    if live is not None:
        stale = live.get("as_of_match") is False
        contract = not_pass(
            verdict="pass_with_caveats",
            source="file_snapshot",
            as_of=str(live.get("as_of") or None),
            requested_as_of=requested,
            notes=[
                "File snapshot fallback; not a live run_mvp. Cannot V_D pass.",
                *(
                    ["Requested as_of did not match snapshot as_of."]
                    if stale
                    else []
                ),
            ],
        )
        return json.dumps(attach_contract(live, contract), indent=2)

    if not forced_missing:
        local = score_local_dm(ticker, start, end)
    else:
        local = None
    if local is not None:
        contract = not_pass(
            verdict="pass_with_caveats",
            source="local_dm",
            as_of=str(local.get("as_of") or None),
            requested_as_of=requested,
            notes=["Local DM SPY proxy; cannot V_D pass."],
        )
        return json.dumps(attach_contract(local, contract), indent=2)

    mock = _mock_state(
        ticker,
        start,
        end,
        reason=(
            "MOCK DATA — no live run_mvp and no momentum-tail-risk-monitor snapshot. "
            "Labels use the same Daniel–Moskowitz vocabulary as live runs, "
            "but values are synthetic. Set MOMENTUM_ENGINE_DIR or vendor the PIT pack."
        ),
    )
    contract = not_pass(
        verdict="fail",
        source="mock",
        as_of=str(mock.get("as_of") or None),
        requested_as_of=requested,
        notes=["Labeled mock; cannot V_D pass."],
    )
    return json.dumps(attach_contract(mock, contract), indent=2)
