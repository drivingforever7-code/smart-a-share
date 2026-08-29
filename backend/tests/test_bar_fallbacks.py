from __future__ import annotations

from types import SimpleNamespace

import pandas as pd

from app.background_data_source import BackgroundRefreshingDataSource
from app.full_data_source import FullMarketDataSource
from app.production_data_source import ProductionDataSource
from app.reliable_data_source import ReliableDataSource
from app import full_data_source, reliable_data_source
from app import main


def test_daily_cached_result_still_tries_tencent(monkeypatch):
    cached = [{"time": "2026-08-15", "open": 10, "high": 10, "low": 10, "close": 10, "volume": 1}]
    monkeypatch.setattr(
        BackgroundRefreshingDataSource,
        "get_bars",
        lambda *_args: (cached, {"is_cached": True, "source": "cache"}),
    )
    monkeypatch.setattr(
        full_data_source,
        "ak",
        SimpleNamespace(
            stock_zh_a_hist_tx=lambda **_kwargs: pd.DataFrame(
                [{"date": "2026-08-18", "open": 11, "high": 12, "low": 10, "close": 11.5, "volume": 100}]
            )
        ),
    )
    source = FullMarketDataSource()
    monkeypatch.setattr(source, "_persist_bars", lambda *_args: None)

    bars, meta = source.get_bars("002440", "day", 800)

    assert bars[-1]["time"] == "2026-08-18"
    assert meta["is_cached"] is False
    assert "腾讯证券" in meta["source"]


def test_intraday_cached_result_still_tries_sina(monkeypatch):
    cached = [{"time": "2026-08-15 15:00:00", "open": 10, "high": 10, "low": 10, "close": 10, "volume": 1}]
    monkeypatch.setattr(
        ProductionDataSource,
        "get_bars",
        lambda *_args: (cached, {"is_cached": True, "source": "cache"}),
    )
    monkeypatch.setattr(
        reliable_data_source,
        "ak",
        SimpleNamespace(
            stock_zh_a_minute=lambda **_kwargs: pd.DataFrame(
                [{"day": "2026-08-18 09:30:00", "open": 11, "high": 11.2, "low": 10.9, "close": 11.1, "volume": 100}]
            )
        ),
    )
    source = ReliableDataSource()
    monkeypatch.setattr(source, "_persist_bars", lambda *_args: None)

    bars, meta = source.get_bars("002440", "1m", 500)

    assert bars[-1]["time"] == "2026-08-18 09:30:00"
    assert meta["trade_date"] == "2026-08-18"
    assert meta["is_cached"] is False
    assert "新浪财经" in meta["source"]


def test_fallback_never_replaces_newer_cached_trading_date(monkeypatch):
    cached = [{"time": "2026-08-18", "open": 11, "high": 12, "low": 10, "close": 11.5, "volume": 100}]
    monkeypatch.setattr(
        BackgroundRefreshingDataSource,
        "get_bars",
        lambda *_args: (cached, {"is_cached": True, "source": "newer cache"}),
    )
    monkeypatch.setattr(
        full_data_source,
        "ak",
        SimpleNamespace(
            stock_zh_a_hist_tx=lambda **_kwargs: pd.DataFrame(
                [{"date": "2026-08-17", "open": 10, "high": 10, "low": 9, "close": 9.5, "volume": 50}]
            )
        ),
    )
    source = FullMarketDataSource()
    monkeypatch.setattr(source, "_persist_bars", lambda *_args: None)

    bars, meta = source.get_bars("002440", "day", 800)

    assert bars[-1]["time"] == "2026-08-18"
    assert meta["source"] == "newer cache"


def test_daily_chart_appends_verified_live_quote_when_history_lags(monkeypatch):
    history = [{"time": "2026-08-17", "open": 6.0, "high": 6.2, "low": 5.9, "close": 6.1, "volume": 100}]
    live_quote = {
        "code": "000725",
        "open": 6.09,
        "high": 6.48,
        "low": 6.09,
        "price": 6.40,
        "volume": 3200,
        "amount": 20_000,
        "quote_time": "2026-08-18 14:50:00",
    }
    monkeypatch.setattr(main.data_source, "_resolve_trade_date", lambda *_args: "2026-08-18")
    monkeypatch.setattr(main, "ak", None)
    monkeypatch.setattr(
        main.data_source,
        "get_bars",
        lambda *_args: ([], {"is_cached": False}),
    )
    monkeypatch.setattr(
        main.data_source,
        "get_spot_quotes",
        lambda **_kwargs: (
            [live_quote],
            {
                "trade_date": "2026-08-18",
                "source": "test realtime",
                "is_cached": False,
                "fetched_at": "2026-08-18T14:50:00",
            },
        ),
    )

    bars, meta = main._merge_current_daily_quote(
        "000725", history, {"source": "test history"}, 20
    )

    assert bars[-1] == {
        "time": "2026-08-18",
        "open": 6.09,
        "high": 6.48,
        "low": 6.09,
        "close": 6.40,
        "volume": 3200.0,
        "amount": 20_000.0,
    }
    assert meta["trade_date"] == "2026-08-18"
    assert "test realtime" in meta["source"]


def test_daily_chart_uses_individual_quote_after_minute_source_lags(monkeypatch):
    history = [{"time": "2026-08-17", "open": 11.0, "high": 11.1, "low": 10.9, "close": 11.0, "volume": 100}]
    quote_frame = pd.DataFrame(
        [
            {"item": "今开", "value": 11.10},
            {"item": "最高", "value": 11.20},
            {"item": "最低", "value": 11.03},
            {"item": "最新", "value": 11.05},
            {"item": "总手", "value": 808_930},
            {"item": "金额", "value": 896_330_000},
        ]
    )
    monkeypatch.setattr(main.data_source, "_resolve_trade_date", lambda *_args: "2026-08-18")
    monkeypatch.setattr(
        main.data_source,
        "get_bars",
        lambda *_args: (history, {"source": "stale minute", "is_cached": False}),
    )
    monkeypatch.setattr(
        main,
        "ak",
        SimpleNamespace(stock_bid_ask_em=lambda **_kwargs: quote_frame),
    )

    bars, meta = main._merge_current_daily_quote(
        "000001", history, {"source": "test history"}, 20
    )

    assert bars[-1]["time"] == "2026-08-18"
    assert bars[-1]["close"] == 11.05
    assert bars[-1]["volume"] == 808_930.0
    assert meta["trade_date"] == "2026-08-18"
    assert "个股盘口" in meta["source"]


def test_daily_chart_prefers_current_intraday_aggregation(monkeypatch):
    history = [{"time": "2026-08-17", "open": 6.0, "high": 6.2, "low": 5.9, "close": 6.1, "volume": 100}]
    minutes = [
        {"time": "2026-08-18 09:30:00", "open": 6.09, "high": 6.2, "low": 6.05, "close": 6.18, "volume": 100, "amount": 61_800},
        {"time": "2026-08-18 09:31:00", "open": 6.18, "high": 6.48, "low": 6.16, "close": 6.40, "volume": 200, "amount": 128_000},
    ]
    monkeypatch.setattr(main.data_source, "_resolve_trade_date", lambda *_args: "2026-08-18")
    monkeypatch.setattr(
        main.data_source,
        "get_bars",
        lambda *_args: (minutes, {"source": "test minute", "is_cached": False}),
    )
    monkeypatch.setattr(
        main.data_source,
        "get_spot_quotes",
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("spot should not run")),
    )

    bars, meta = main._merge_current_daily_quote(
        "000725", history, {"source": "test history"}, 20
    )

    assert bars[-1]["time"] == "2026-08-18"
    assert bars[-1]["open"] == 6.09
    assert bars[-1]["high"] == 6.48
    assert bars[-1]["low"] == 6.05
    assert bars[-1]["close"] == 6.40
    assert bars[-1]["volume"] == 300.0
    assert meta["trade_date"] == "2026-08-18"
    assert "test minute" in meta["source"]


def test_daily_chart_rejects_unverified_quote_date(monkeypatch):
    history = [{"time": "2026-08-17", "open": 6.0, "high": 6.2, "low": 5.9, "close": 6.1, "volume": 100}]
    monkeypatch.setattr(main.data_source, "_resolve_trade_date", lambda *_args: "2026-08-18")
    monkeypatch.setattr(main, "ak", None)
    monkeypatch.setattr(
        main.data_source,
        "get_bars",
        lambda *_args: ([], {"is_cached": False}),
    )
    monkeypatch.setattr(
        main.data_source,
        "get_spot_quotes",
        lambda **_kwargs: ([], {"trade_date": None}),
    )

    bars, meta = main._merge_current_daily_quote(
        "000725", history, {"source": "test history"}, 20
    )

    assert bars == history
    assert meta == {"source": "test history"}
