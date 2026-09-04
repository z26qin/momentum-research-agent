"""Local Daniel–Moskowitz-style scorer when the live pipeline cannot run.

Cannot issue V_D pass. Unknown dates may use this as pass_with_caveats / fail.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from momentum_research_agent.tools.engine_adapter import DM_BEAR_STATES, MECHANICAL_UNWIND_REGIMES


def score_local_dm(
    ticker: str,
    start: str | None,
    end: str | None,
) -> dict[str, Any] | None:
    try:
        import pandas as pd
        import yfinance as yf
    except ImportError:
        return None
    as_of = end or datetime.now(timezone.utc).date().isoformat()
    try:
        hist = yf.Ticker("SPY").history(period="2y", auto_adjust=True)
    except Exception:
        return None
    if hist is None or hist.empty or "Close" not in hist.columns:
        return None
    closes = hist["Close"].dropna()
    if len(closes) < 40:
        return None
    ret_24m = float(closes.iloc[-1] / closes.iloc[0] - 1.0)
    vol_6m = float(closes.iloc[-126:].pct_change().std() * (252**0.5)) if len(closes) > 126 else float(
        closes.pct_change().std() * (252**0.5)
    )
    if ret_24m < -0.2 and vol_6m > 0.25:
        risk_state = "panic_elevated"
        regime = "UNWIND"
    elif ret_24m < 0:
        risk_state = "bear_low_volatility"
        regime = "FRAGILITY_BUILDING"
    else:
        risk_state = "normal"
        regime = MECHANICAL_UNWIND_REGIMES[0]
    return {
        "ticker": ticker.upper(),
        "start": start,
        "end": end,
        "as_of": as_of,
        "source": "local_dm",
        "scope": "spy_proxy",
        "risk_state": risk_state,
        "regime": regime,
        "conditional_crash_frequency": None,
        "dm_bear_market_indicator": risk_state in DM_BEAR_STATES,
        "crowding_score": None,
        "spy_24m_return": round(ret_24m, 4),
        "spy_6m_vol": round(vol_6m, 4),
        "note": (
            "LOCAL DM — yfinance SPY proxy, not run_mvp. "
            "Cannot satisfy delivery_contract.verdict=pass."
        ),
    }
