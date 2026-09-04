"""Query the deterministic momentum tail-risk engine via a file adapter."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from momentum_research_agent.tools.engine_adapter import load_engine_state
from momentum_research_agent.tools.registry import get_tool_context, register_tool

_REGIMES = ("EXPANSION", "CROWDED", "UNWIND", "BEAR_REBOUND", "CRASH_RISK")
_STATES = ("QUIET", "WATCH", "ELEVATED", "CRITICAL")


def _mock_state(
    ticker: str,
    start: str | None,
    end: str | None,
    *,
    reason: str,
) -> dict[str, object]:
    seed = hashlib.sha256(f"{ticker}|{start}|{end}".encode()).digest()
    regime = _REGIMES[seed[0] % len(_REGIMES)]
    state = _STATES[seed[1] % len(_STATES)]
    freq = round(0.04 + (seed[2] / 255.0) * 0.28, 3)
    return {
        "ticker": ticker.upper(),
        "start": start,
        "end": end,
        "as_of": datetime.now(timezone.utc).date().isoformat(),
        "source": "mock",
        "scope": "mock",
        "risk_state": state,
        "regime": regime,
        "conditional_crash_frequency": freq,
        "dm_bear_market_indicator": regime in {"BEAR_REBOUND", "CRASH_RISK"},
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
        "risk state, mechanical-unwind regime, and crowding overlays. Reads "
        "momentum-tail-risk-monitor JSON snapshots when available "
        "(MOMENTUM_ENGINE_DIR or a sibling checkout). The engine is "
        "market/book-level, not a single-name API. Falls back to labeled mock "
        "data if no snapshot is found."
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
                "description": "Optional start date YYYY-MM-DD.",
            },
            "end": {
                "type": "string",
                "description": "Optional as-of / end date YYYY-MM-DD.",
            },
        },
        "required": ["ticker"],
    },
)
async def engine_query(ticker: str, start: str | None = None, end: str | None = None) -> str:
    live = load_engine_state(ticker, start, end, project_root=_project_root())
    if live is not None:
        return json.dumps(live, indent=2)
    return json.dumps(
        _mock_state(
            ticker,
            start,
            end,
            reason=(
                "MOCK DATA — no momentum-tail-risk-monitor snapshot found. "
                "Set MOMENTUM_ENGINE_DIR or place the engine repo beside this project."
            ),
        ),
        indent=2,
    )
