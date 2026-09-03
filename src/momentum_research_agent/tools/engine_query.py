"""Placeholder query against the deterministic momentum tail-risk engine."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from momentum_research_agent.tools.registry import register_tool

# TODO: wire to actual engine (momentum-tail-risk-monitor Daniel–Moskowitz
# risk state, FINRA/GDELT overlays, triggered evidence layer).

_REGIMES = ("EXPANSION", "CROWDED", "UNWIND", "BEAR_REBOUND", "CRASH_RISK")
_STATES = ("QUIET", "WATCH", "ELEVATED", "CRITICAL")


def _mock_state(ticker: str, start: str | None, end: str | None) -> dict[str, object]:
    seed = hashlib.sha256(f"{ticker}|{start}|{end}".encode()).digest()
    regime = _REGIMES[seed[0] % len(_REGIMES)]
    state = _STATES[seed[1] % len(_STATES)]
    freq = round(0.04 + (seed[2] / 255.0) * 0.28, 3)
    return {
        "ticker": ticker.upper(),
        "start": start,
        "end": end,
        "as_of": datetime.now(timezone.utc).date().isoformat(),
        "risk_state": state,
        "regime": regime,
        "conditional_crash_frequency": freq,
        "dm_bear_market_indicator": regime in {"BEAR_REBOUND", "CRASH_RISK"},
        "crowding_score": round(0.2 + (seed[3] / 255.0) * 0.7, 3),
        "note": "MOCK DATA — TODO: wire to actual engine",
    }


@register_tool(
    name="engine_query",
    description=(
        "Query the deterministic momentum tail-risk engine for risk state, "
        "conditional crash frequency, and regime classification. "
        "Currently returns deterministic mock data."
    ),
    parameters={
        "type": "object",
        "properties": {
            "ticker": {
                "type": "string",
                "description": "US equity ticker, e.g. NVDA or SMH.",
            },
            "start": {
                "type": "string",
                "description": "Optional start date YYYY-MM-DD.",
            },
            "end": {
                "type": "string",
                "description": "Optional end date YYYY-MM-DD.",
            },
        },
        "required": ["ticker"],
    },
)
async def engine_query(ticker: str, start: str | None = None, end: str | None = None) -> str:
    return json.dumps(_mock_state(ticker, start, end), indent=2)
