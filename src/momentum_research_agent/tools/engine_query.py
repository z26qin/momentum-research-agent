"""Query the deterministic momentum tail-risk engine via a file adapter."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from momentum_research_agent.tools.engine_adapter import (
    DM_BEAR_STATES,
    DM_PRIMARY_STATES,
    MECHANICAL_UNWIND_REGIMES,
    load_engine_state,
)
from momentum_research_agent.tools.engine_contract import attach_delivery_contract
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
        "unwind regime, and crowding overlays. Reads momentum-tail-risk-monitor "
        "JSON snapshots when available (MOMENTUM_ENGINE_DIR or a sibling checkout). "
        "The engine is market/book-level, not a single-name API. Each payload "
        "includes delivery_contract V_D (pass | pass_with_caveats | fail). "
        "Falls back to labeled mock data that uses the same DM vocabulary if "
        "no snapshot is found."
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
    live = load_engine_state(ticker, start, end, project_root=_project_root())
    payload = live if live is not None else _mock_state(
        ticker,
        start,
        end,
        reason=(
            "MOCK DATA — no momentum-tail-risk-monitor snapshot found. "
            "Labels use the same Daniel–Moskowitz vocabulary as live snapshots, "
            "but values are synthetic. Set MOMENTUM_ENGINE_DIR or place the "
            "engine repo beside this project."
        ),
    )
    return json.dumps(attach_delivery_contract(payload, requested_end=end), indent=2)
