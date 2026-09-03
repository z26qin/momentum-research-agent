"""Fetch price/volume history via yfinance."""

from __future__ import annotations

import asyncio

from momentum_research_agent.tools.registry import register_tool


def _download(ticker: str, period: str, interval: str):
    import yfinance as yf

    return yf.download(
        ticker,
        period=period,
        interval=interval,
        progress=False,
        auto_adjust=True,
    )


def _to_markdown(frame) -> str:
    if frame is None or frame.empty:
        return "No price data returned."

    if getattr(frame.columns, "nlevels", 1) > 1:
        frame = frame.copy()
        frame.columns = [
            col[0] if isinstance(col, tuple) else col for col in frame.columns
        ]

    close_col = "Close" if "Close" in frame.columns else frame.columns[0]
    work = frame[[close_col]].copy()
    if "Volume" in frame.columns:
        work["Volume"] = frame["Volume"]
    work["Return"] = work[close_col].pct_change()
    tail = work.tail(20).reset_index()
    date_col = tail.columns[0]
    tail[date_col] = tail[date_col].astype(str)
    tail[close_col] = tail[close_col].map(lambda value: f"{float(value):.2f}")
    tail["Return"] = tail["Return"].map(
        lambda value: "" if value != value else f"{float(value):.2%}"
    )
    if "Volume" in tail.columns:
        tail["Volume"] = tail["Volume"].map(
            lambda value: "" if value != value else f"{int(value):,}"
        )
    return tail.to_markdown(index=False)


@register_tool(
    name="market_data",
    description=(
        "Fetch OHLCV history for a US ticker via yfinance and return a markdown "
        "table of recent close, return, and volume."
    ),
    parameters={
        "type": "object",
        "properties": {
            "ticker": {"type": "string", "description": "Ticker symbol, e.g. NVDA."},
            "period": {
                "type": "string",
                "description": "yfinance period string. Default: 3mo.",
            },
            "interval": {
                "type": "string",
                "description": "yfinance interval string. Default: 1d.",
            },
        },
        "required": ["ticker"],
    },
)
async def market_data(ticker: str, period: str = "3mo", interval: str = "1d") -> str:
    try:
        frame = await asyncio.to_thread(_download, ticker, period, interval)
    except Exception as exc:
        return f"market_data failed for {ticker}: {exc}"
    header = f"# {ticker.upper()}  period={period} interval={interval}\n\n"
    return header + _to_markdown(frame)
