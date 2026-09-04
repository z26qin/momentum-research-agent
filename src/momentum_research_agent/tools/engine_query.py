"""Query the deterministic momentum tail-risk engine via a file adapter."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import asyncio

from momentum_research_agent.tools.engine_adapter import (
    DM_BEAR_STATES,
    DM_PRIMARY_STATES,
    MECHANICAL_UNWIND_REGIMES,
    load_engine_state,
)
from momentum_research_agent.tools.engine_contract import attach_delivery_contract
from momentum_research_agent.tools.engine_pipeline import (
    peek_cached_assessment,
    run_monitor_assessment,
)
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


def _project_root() -> Path | None:
    try:
        return get_tool_context().project_root
    except RuntimeError:
        return None


@register_tool(
    name="engine_query",
    description=(
        "Query the deterministic momentum tail-risk engine for Daniel–Moskowitz "
        "risk state (normal | bear_low_volatility | panic_elevated), mechanical "
        "unwind regime, and crowding overlays. Prefers a warmed live PIT run of "
        "momentum-tail-risk-monitor (`scripts/run_monitor.py` via MOMENTUM_ENGINE_DIR "
        "or a sibling checkout) when Coordinator.warm_engine cached it. Matching "
        "JSON snapshots (including fixtures/engine frozen 2026-05-29 / 2026-06-30) "
        "are the fast path. If neither exists, runs a local Daniel–Moskowitz "
        "scorer on SPY + ticker closes (24m bear market + 6m vol → risk_state; "
        "1m drawdown → unwind). Each payload includes delivery_contract V_D "
        "(pass | pass_with_caveats | fail). Labeled mock only if snapshot, "
        "pipeline, and local scorer are all unavailable."
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
    root = _project_root()
    payload = peek_cached_assessment(ticker, start, end, project_root=root)
    live = None
    if payload is None:
        live = load_engine_state(ticker, start, end, project_root=root)
        payload = live if live is not None and live.get("as_of_match", True) else None
    if payload is None:
        payload = await asyncio.to_thread(
            run_monitor_assessment,
            ticker,
            start,
            end,
            project_root=root,
        )
    if payload is None and live is not None:
        payload = live
    if payload is None:
        payload = await asyncio.to_thread(score_local_dm, ticker, start, end)
    if payload is None:
        payload = _mock_state(
            ticker,
            start,
            end,
            reason=(
                "MOCK DATA — no momentum-tail-risk-monitor snapshot, pipeline run, "
                "or local DM prices. Labels use the same Daniel–Moskowitz "
                "vocabulary, but values are synthetic. Set MOMENTUM_ENGINE_DIR "
                "to a monitor checkout (scripts/run_monitor.py) or allow yfinance."
            ),
        )
    return json.dumps(attach_delivery_contract(payload, requested_end=end), indent=2)
