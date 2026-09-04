from __future__ import annotations

from momentum_research_agent.tools.local_dm import geometric_closes, score_from_closes


def test_bull_quiet_is_normal() -> None:
    path = geometric_closes(
        n=520,
        start=100.0,
        daily_mu=0.0005,
        shocks=(0.003, -0.003),
        end="2026-05-29",
    )
    payload = score_from_closes("NVDA", path, path, end="2026-05-29")
    assert payload is not None
    assert payload["source"] == "local_dm"
    assert payload["risk_state"] == "normal"
    assert payload["regime"] == "QUIET"
    assert payload["dm_bear_market_indicator"] is False


def test_bear_low_vol_maps_to_dm_bear() -> None:
    path = geometric_closes(
        n=520,
        start=100.0,
        daily_mu=-0.0007,
        shocks=(0.003, -0.003),
        end="2026-05-29",
    )
    payload = score_from_closes("SMH", path, path, end="2026-05-29")
    assert payload is not None
    assert payload["risk_state"] == "bear_low_volatility"
    assert payload["regime"] == "FRAGILITY_BUILDING"
    assert payload["dm_bear_market_indicator"] is True


def test_high_vol_crash_is_panic_unwind() -> None:
    path = geometric_closes(
        n=520,
        start=100.0,
        daily_mu=-0.001,
        shocks=(0.02, -0.02),
        end="2026-05-29",
        crash_days=21,
        crash_mu=-0.025,
    )
    payload = score_from_closes("NVDA", path, path, end="2026-05-29")
    assert payload is not None
    assert payload["risk_state"] == "panic_elevated"
    assert payload["regime"] == "UNWIND"
    assert payload["ticker_1m_return"] < -0.10
    assert 0.0 <= payload["crowding_score"] <= 1.0


def test_fetch_closes_caches(monkeypatch) -> None:
    import sys
    from types import SimpleNamespace

    from momentum_research_agent.tools import local_dm

    class _Cols(list):
        nlevels = 1

    class FakeFrame:
        empty = False
        columns = _Cols(["Close"])

        def __init__(self) -> None:
            self._rows = [(f"2024-01-{i:02d}", 100.0 + i) for i in range(2, 28)]

        def __getitem__(self, _name: str):
            return self

        def items(self):
            return iter(self._rows)

    local_dm._CLOSE_CACHE.clear()
    calls = {"n": 0}

    def fake_download(ticker, **kwargs):
        calls["n"] += 1
        return FakeFrame()

    monkeypatch.setitem(sys.modules, "yfinance", SimpleNamespace(download=fake_download))
    first = local_dm.fetch_closes("NVDA", end="2024-04-22")
    second = local_dm.fetch_closes("NVDA", end="2024-04-22")
    assert first is not None and len(first) == 26
    assert second == first
    assert calls["n"] == 1
