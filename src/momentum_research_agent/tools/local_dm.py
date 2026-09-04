"""Local Daniel–Moskowitz-inspired scorer when no monitor snapshot exists.

Uses trailing market (SPY) return and realized vol to map onto the same
risk_state / unwind-regime vocabulary as momentum-tail-risk-monitor.
This is not a hash mock and not a PIT parquet pipeline run.
"""

from __future__ import annotations

import math
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from typing import Any, Sequence

from momentum_research_agent.tools.engine_adapter import (
    DM_BEAR_STATES,
    DM_PRIMARY_STATES,
    MECHANICAL_UNWIND_REGIMES,
)

MARKET_TICKER = "SPY"
MIN_POINTS = 60
BEAR_RETURN = 0.0
PANIC_VOL = 0.20
UNWIND_1M = -0.10
UNWIND_VOL = 0.18
FRAGILITY_MOM = 0.40
FRAGILITY_VOL = 0.16
TRADING_YEAR = 252
TRADING_MONTH = 21
TRADING_6M = 126
TRADING_12M = 252
TRADING_24M = 504

_CLOSE_CACHE: dict[tuple[str, str | None], list[tuple[str, float]]] = {}


def local_dm_disabled() -> bool:
    return os.environ.get("MOMENTUM_DISABLE_LOCAL_DM", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }


def score_from_closes(
    ticker: str,
    ticker_closes: Sequence[tuple[str, float]],
    market_closes: Sequence[tuple[str, float]] | None = None,
    *,
    start: str | None = None,
    end: str | None = None,
) -> dict[str, Any] | None:
    ticker_px = _values(ticker_closes, end)
    market_px = _values(market_closes or ticker_closes, end)
    if len(ticker_px) < MIN_POINTS or len(market_px) < MIN_POINTS:
        return None
    as_of = _last_date(ticker_closes, end)
    mkt_24m = _trailing_return(market_px, TRADING_24M)
    mkt_vol = _ann_vol(market_px, TRADING_6M)
    r_1m = _trailing_return(ticker_px, TRADING_MONTH)
    mom_12_1 = _skip_month_momentum(ticker_px)
    mkt_mom_12_1 = _skip_month_momentum(market_px)
    if mkt_24m < BEAR_RETURN:
        risk_state = (
            DM_PRIMARY_STATES[2]
            if mkt_vol >= PANIC_VOL
            else DM_PRIMARY_STATES[1]
        )
    else:
        risk_state = DM_PRIMARY_STATES[0]
    if r_1m <= UNWIND_1M and mkt_vol >= UNWIND_VOL:
        regime = MECHANICAL_UNWIND_REGIMES[2]
    elif mkt_24m < BEAR_RETURN or (
        mom_12_1 >= FRAGILITY_MOM and mkt_vol >= FRAGILITY_VOL
    ):
        regime = MECHANICAL_UNWIND_REGIMES[1]
    else:
        regime = MECHANICAL_UNWIND_REGIMES[0]
    relative = mom_12_1 - mkt_mom_12_1
    crowding = round(min(1.0, max(0.0, 0.5 + relative)), 3)
    crash_freq = round(min(0.45, max(0.02, 0.04 + max(0.0, -r_1m) + max(0.0, mkt_vol - 0.15))), 3)
    return {
        "ticker": ticker.upper(),
        "start": start,
        "end": end,
        "as_of": as_of,
        "source": "local_dm",
        "scope": "ticker_with_spy_market",
        "as_of_match": True,
        "risk_state": risk_state,
        "regime": regime,
        "conditional_crash_frequency": crash_freq,
        "dm_bear_market_indicator": risk_state in DM_BEAR_STATES,
        "crowding_score": crowding,
        "market_24m_return": round(mkt_24m, 4),
        "market_6m_vol": round(mkt_vol, 4),
        "ticker_1m_return": round(r_1m, 4),
        "momentum_12_1": round(mom_12_1, 4),
        "note": (
            "Local Daniel–Moskowitz-inspired scorer over yfinance closes "
            "(SPY 24m return + 6m vol → risk_state; 1m drawdown → unwind regime). "
            "Not a momentum-tail-risk-monitor PIT pipeline run."
        ),
    }


def score_local_dm(
    ticker: str,
    start: str | None = None,
    end: str | None = None,
) -> dict[str, Any] | None:
    if local_dm_disabled():
        return None
    symbol = ticker.upper()
    if symbol == MARKET_TICKER:
        ticker_px = fetch_closes(symbol, end=end)
        market_px = ticker_px
    else:
        with ThreadPoolExecutor(max_workers=2) as pool:
            ticker_fut = pool.submit(fetch_closes, symbol, end=end)
            market_fut = pool.submit(fetch_closes, MARKET_TICKER, end=end)
            ticker_px = ticker_fut.result()
            market_px = market_fut.result()
    if ticker_px is None:
        return None
    return score_from_closes(
        symbol, ticker_px, market_px or ticker_px, start=start, end=end
    )


def fetch_closes(ticker: str, *, end: str | None = None) -> list[tuple[str, float]] | None:
    key = (ticker.upper(), end)
    cached = _CLOSE_CACHE.get(key)
    if cached is not None:
        return cached
    try:
        import yfinance as yf
    except ImportError:
        return None
    kwargs: dict[str, Any] = {"progress": False, "auto_adjust": True}
    if end:
        kwargs["end"] = end
        kwargs["start"] = _minus_years(end, 3)
    else:
        kwargs["period"] = "3y"
    try:
        frame = yf.download(ticker, **kwargs)
    except Exception:
        return None
    if frame is None or getattr(frame, "empty", True):
        return None
    if getattr(frame.columns, "nlevels", 1) > 1:
        frame = frame.copy()
        frame.columns = [
            col[0] if isinstance(col, tuple) else col for col in frame.columns
        ]
    close_col = "Close" if "Close" in frame.columns else frame.columns[0]
    rows: list[tuple[str, float]] = []
    for index, value in frame[close_col].items():
        try:
            price = float(value)
        except (TypeError, ValueError):
            continue
        if price != price or price <= 0:
            continue
        day = str(index)[:10]
        rows.append((day, price))
    if not rows:
        return None
    _CLOSE_CACHE[key] = rows
    return rows


def _minus_years(end: str, years: int) -> str:
    try:
        day = date.fromisoformat(end[:10])
    except ValueError:
        return f"{int(end[:4]) - years}-01-01"
    try:
        return day.replace(year=day.year - years).isoformat()
    except ValueError:
        return day.replace(month=2, day=28, year=day.year - years).isoformat()


def _values(points: Sequence[tuple[str, float]], end: str | None) -> list[float]:
    cutoff = end[:10] if end else None
    values: list[float] = []
    for day, price in points:
        if cutoff and day[:10] > cutoff:
            continue
        values.append(float(price))
    return values


def _last_date(points: Sequence[tuple[str, float]], end: str | None) -> str:
    cutoff = end[:10] if end else None
    last = cutoff
    for day, _price in points:
        if cutoff and day[:10] > cutoff:
            continue
        last = day[:10]
    return last or datetime.now(timezone.utc).date().isoformat()


def _trailing_return(values: list[float], window: int) -> float:
    if len(values) < 2:
        return 0.0
    base = values[-window] if len(values) >= window else values[0]
    if base <= 0:
        return 0.0
    return values[-1] / base - 1.0


def _skip_month_momentum(values: list[float]) -> float:
    if len(values) < TRADING_MONTH + 2:
        return _trailing_return(values, min(len(values) - 1, TRADING_12M))
    held = values[:-TRADING_MONTH]
    return _trailing_return(held, TRADING_12M)


def _ann_vol(values: list[float], window: int) -> float:
    sample = values[-(window + 1) :] if len(values) > window + 1 else values
    rets = [
        sample[i] / sample[i - 1] - 1.0
        for i in range(1, len(sample))
        if sample[i - 1] > 0
    ]
    if len(rets) < 5:
        return 0.0
    mean = sum(rets) / len(rets)
    var = sum((item - mean) ** 2 for item in rets) / (len(rets) - 1)
    return math.sqrt(var) * math.sqrt(TRADING_YEAR)


def geometric_closes(
    *,
    n: int,
    start: float,
    daily_mu: float,
    shocks: Sequence[float],
    end: str,
    crash_days: int = 0,
    crash_mu: float = -0.02,
) -> list[tuple[str, float]]:
    """Deterministic dated close path for tests and frozen eval."""
    end_day = date.fromisoformat(end)
    values = [float(start)]
    for i in range(n - 1):
        remaining = n - 1 - i
        mu = crash_mu if remaining <= crash_days else daily_mu
        shock = shocks[i % len(shocks)] if shocks else 0.0
        values.append(max(0.01, values[-1] * (1.0 + mu + shock)))
    days: list[date] = []
    cursor = end_day
    while len(days) < n:
        if cursor.weekday() < 5:
            days.append(cursor)
        cursor -= timedelta(days=1)
    days.reverse()
    return [(day.isoformat(), price) for day, price in zip(days, values, strict=False)]
