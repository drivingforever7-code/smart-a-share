from __future__ import annotations

import os

from contextlib import asynccontextmanager
from datetime import datetime
from typing import Literal

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .strategy_backtest_service import run_strategy_backtest
from .auto_backtest_service import (
    auto_backtest,
    capture_mode_snapshot,
    repair_repeated_cached_discoveries,
)
from .limit_break_service import (
    LimitBreakDataError,
    capture_limit_breaks,
    limit_break_research,
)
from .ai_analysis_service import (
    AiServiceError,
    ai_service_status,
    analyze_stock_with_ai,
    get_ai_run,
    list_ai_history,
)
from .ai_schemas import AiAnalysisRequest
from .ai_schemas import TradeReviewRequest
from .board_pool_service import BoardPoolDataError, board_pool_research, capture_board_pools
from .trade_review_service import review_trade
from .config import settings
from .parallel_research_service import parallel_research, start_refresh as start_parallel_refresh, start_scheduler, latest_archive
from .data_source import MarketDataError, ak, safe_float
from .data_refresh_service import refresh_all_data
from .database import init_database
from .ranking_archive_service import (
    import_packaged_ranking_archives,
    sync_ranking_archives,
)
from .ranking_optimizer_service import (
    ensure_baseline_versions,
    ranking_strategy_status,
    ranking_strategy_version_detail,
    repair_unverified_training_samples,
)
from .intraday_service import get_intraday
from .market_service import market_service, presets
from .sector_heatmap_service import sector_heatmap_service
from .reliable_data_source import data_source
from .schemas import ScreenerRequest
from .strategy_schemas import StrategyBacktestRequest, StrategyPayload
from .strategy_lab_service import StrategyLabRequest, evaluate_strategy_basket
from .strategy_service import (
    StrategyNotFoundError,
    copy_strategy,
    create_strategy,
    delete_strategy,
    get_strategy,
    initialize_strategy_catalog,
    list_strategies,
    reset_builtin_strategy,
    strategy_catalog_metadata,
    update_strategy,
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_database()
    import_packaged_ranking_archives()
    repair_repeated_cached_discoveries()
    repair_unverified_training_samples()
    ensure_baseline_versions()
    initialize_strategy_catalog()
    parallel_stop = start_scheduler()
    try:
        yield
    finally:
        parallel_stop.set()


app = FastAPI(
    title=settings.app_name,
    version=settings.version,
    description="本地 A 股实时行情、短线/波段评分、选股和策略验证接口",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5173",
        "http://localhost:5173",
        "http://127.0.0.1:4173",
        "http://localhost:4173",
    ],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(LimitBreakDataError)
async def limit_break_data_error_handler(_: Request, exc: LimitBreakDataError) -> JSONResponse:
    return JSONResponse(status_code=503, content={"detail": str(exc)})


@app.exception_handler(BoardPoolDataError)
async def board_pool_data_error_handler(_: Request, exc: BoardPoolDataError) -> JSONResponse:
    return JSONResponse(status_code=503, content={"detail": str(exc)})


@app.exception_handler(MarketDataError)
async def market_data_error_handler(_: Request, exc: MarketDataError) -> JSONResponse:
    return JSONResponse(status_code=503, content={"detail": str(exc)})


@app.get("/api/health", tags=["系统"])
async def health() -> dict[str, str]:
    return {
        "status": "ok",
        "version": settings.version,
        "git_commit": os.getenv("RENDER_GIT_COMMIT", "local"),
        "git_branch": os.getenv("RENDER_GIT_BRANCH", "local"),
        "git_repo": os.getenv("RENDER_GIT_REPO_SLUG", "local"),
    }


@app.get("/api/market/overview", tags=["行情"])
async def market_overview():
    return await run_in_threadpool(market_service.overview)

@app.get("/api/market/sectors", tags=["行情"])
async def sector_rankings(
    kind: Literal["industry", "concept"] = "industry",
    refresh: bool = False,
    ai: bool = True,
):
    try:
        return await run_in_threadpool(
            sector_heatmap_service.rankings,
            kind,
            force=refresh,
            with_ai=ai,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

@app.get("/api/market/sectors/{kind}/{name}", tags=["行情"])
async def sector_detail(
    kind: Literal["industry", "concept"],
    name: str,
    ai: bool = True,
):
    try:
        return await run_in_threadpool(
            sector_heatmap_service.detail,
            kind,
            name,
            with_ai=ai,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/api/market/opportunities", tags=["选股"])
async def opportunities(
    mode: Literal["short", "swing"] = "short",
    limit: int = Query(default=10, ge=1, le=10),
    preset: str | None = None,
):
    result = await run_in_threadpool(
        market_service.opportunities,
        mode,
        limit=limit,
        preset=preset,
    )
    if preset is None:
        await run_in_threadpool(capture_mode_snapshot, mode, result)
    return [item for item in result if item.get("score", 0) >= 60 and item.get("confidence", 0) >= 45][:10]


@app.get("/api/auto-backtest", tags=["自动回测"])
async def automatic_backtest(
    days: int = Query(default=5, ge=1, le=30),
):
    archive_sync = await run_in_threadpool(sync_ranking_archives)
    result = await run_in_threadpool(auto_backtest, days)
    return {**result, "archive_sync": archive_sync}


@app.get("/api/ranking-strategies/status", tags=["自动回测"])
async def ranking_strategy_versions():
    return await run_in_threadpool(ranking_strategy_status)


@app.get("/api/ranking-strategies/{mode}/versions/{version}", tags=["自动回测"])
async def ranking_strategy_version(
    mode: Literal["short", "swing"],
    version: str,
):
    try:
        return await run_in_threadpool(ranking_strategy_version_detail, mode, version)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

@app.get("/api/limit-breaks", tags=["炸板研究"])
async def limit_breaks(
    days: int = Query(default=5, ge=1, le=30),
    refresh: bool = True,
):
    return await run_in_threadpool(limit_break_research, days, refresh)


@app.post("/api/limit-breaks/capture", tags=["炸板研究"])
async def limit_break_capture(
    stage: Literal["auto", "midday", "afternoon", "close"] = "auto",
):
    return await run_in_threadpool(capture_limit_breaks, stage)


@app.get("/api/board-pools", tags=["连板与跌停研究"])
async def board_pools(days: int = Query(default=5, ge=1, le=30), refresh: bool = True):
    return await run_in_threadpool(board_pool_research, days, refresh)


@app.post("/api/board-pools/capture", tags=["连板与跌停研究"])
async def board_pool_capture():
    return await run_in_threadpool(capture_board_pools)


@app.get("/api/presets", tags=["选股"])
async def preset_list():
    return presets()


@app.get("/api/stocks/search", tags=["股票"])
async def search_stocks(
    q: str = Query(min_length=1, max_length=40),
    limit: int = Query(default=20, ge=1, le=100),
):
    return await run_in_threadpool(market_service.search, q, limit)


@app.get("/api/stocks/{code}/analysis", tags=["股票"])
async def stock_analysis(
    code: str,
    mode: Literal["short", "swing"] = "short",
):
    if len(code) != 6 or not code.isdigit():
        raise HTTPException(status_code=422, detail="股票代码必须是 6 位数字")
    return await run_in_threadpool(market_service.stock_analysis, code, mode)


@app.get("/api/stocks/{code}/bars", tags=["股票"])
async def stock_bars(
    code: str,
    timeframe: Literal["1m", "5m", "15m", "30m", "60m", "day", "week", "month"] = "day",
    limit: int = Query(default=250, ge=20, le=2000),
):
    if len(code) != 6 or not code.isdigit():
        raise HTTPException(status_code=422, detail="股票代码必须是 6 位数字")
    bars, meta = await run_in_threadpool(data_source.get_bars, code, timeframe, limit)
    if timeframe == "day":
        bars, meta = await run_in_threadpool(
            _merge_current_daily_quote,
            code,
            bars,
            meta,
            limit,
        )
    if bars:
        meta = {**meta, "trade_date": str(bars[-1]["time"])[:10]}
    return {"code": code, "timeframe": timeframe, "bars": bars, "meta": meta}


def _merge_current_daily_quote(
    code: str,
    bars: list[dict],
    meta: dict,
    limit: int,
) -> tuple[list[dict], dict]:
    """历史日线盘中滞后时，用已校验交易日的实时 OHLC 补齐最后一根。"""
    if not bars:
        return bars, meta
    last_date = str(bars[-1].get("time", ""))[:10]
    expected_date = data_source._resolve_trade_date(datetime.now())
    if not expected_date or last_date >= expected_date:
        return bars, meta

    # 分钟线是按股票请求，通常比全市场实时接口更快，也能完整还原当日 OHLC。
    try:
        minute_bars, minute_meta = data_source.get_bars(code, "1m", 500)
        current_minutes = [
            item for item in minute_bars if str(item.get("time", ""))[:10] == expected_date
        ]
    except MarketDataError:
        current_minutes = []
        minute_meta = {}
    if current_minutes:
        amounts = [safe_float(item.get("amount")) for item in current_minutes]
        live_bar = {
            "time": expected_date,
            "open": safe_float(current_minutes[0].get("open")),
            "high": max(safe_float(item.get("high")) or 0 for item in current_minutes),
            "low": min(
                value
                for item in current_minutes
                if (value := safe_float(item.get("low"))) is not None
            ),
            "close": safe_float(current_minutes[-1].get("close")),
            "volume": sum(safe_float(item.get("volume")) or 0 for item in current_minutes),
            "amount": sum(value for value in amounts if value is not None) or None,
        }
        if None not in {
            live_bar["open"],
            live_bar["high"],
            live_bar["low"],
            live_bar["close"],
        } and live_bar["volume"] > 0:
            merged = [*bars, live_bar][-max(1, min(limit, 2000)) :]
            return merged, {
                **meta,
                "source": f"{meta.get('source', '历史行情')}；当日 K 线由{minute_meta.get('source', '分钟行情')}聚合",
                "quote_time": str(current_minutes[-1].get("time", "")),
                "trade_date": expected_date,
                "is_cached": bool(minute_meta.get("is_cached")),
                "fetched_at": minute_meta.get("fetched_at", meta.get("fetched_at")),
                "cache_age_seconds": minute_meta.get("cache_age_seconds", 0),
            }

    individual_result = _fetch_individual_daily_bar(code, expected_date)
    if individual_result:
        live_bar, live_meta = individual_result
        merged = [*bars, live_bar][-max(1, min(limit, 2000)) :]
        return merged, {
            **meta,
            "source": f"{meta.get('source', '历史行情')}；当日 K 线使用{live_meta['source']}补齐",
            "quote_time": live_meta["quote_time"],
            "trade_date": expected_date,
            "is_cached": False,
            "fetched_at": live_meta["fetched_at"],
            "cache_age_seconds": 0,
        }

    try:
        quotes, quote_meta = data_source.get_spot_quotes(force=False)
        if quote_meta.get("trade_date") != expected_date:
            quotes, quote_meta = data_source.get_spot_quotes(force=True)
    except MarketDataError:
        return bars, meta
    if quote_meta.get("trade_date") != expected_date:
        return bars, meta

    quote = next((item for item in quotes if item.get("code") == code), None)
    if not quote:
        return bars, meta
    open_price = safe_float(quote.get("open"))
    high = safe_float(quote.get("high"))
    low = safe_float(quote.get("low"))
    close = safe_float(quote.get("price"))
    volume = safe_float(quote.get("volume"))
    if None in {open_price, high, low, close, volume}:
        return bars, meta
    if min(open_price, high, low, close, volume) <= 0:
        return bars, meta
    if high < max(open_price, close) or low > min(open_price, close):
        return bars, meta

    live_bar = {
        "time": expected_date,
        "open": open_price,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
        "amount": safe_float(quote.get("amount")),
    }
    merged = [*bars, live_bar][-max(1, min(limit, 2000)) :]
    return merged, {
        **meta,
        "source": f"{meta.get('source', '历史行情')}；当日 K 线使用{quote_meta.get('source', '实时行情')}补齐",
        "quote_time": quote.get("quote_time") or quote_meta.get("fetched_at"),
        "trade_date": expected_date,
        "is_cached": bool(quote_meta.get("is_cached")),
        "fetched_at": quote_meta.get("fetched_at", meta.get("fetched_at")),
        "cache_age_seconds": quote_meta.get("cache_age_seconds", 0),
    }


def _fetch_individual_daily_bar(
    code: str,
    trade_date: str,
) -> tuple[dict, dict] | None:
    """用轻量个股盘口接口获取当日 OHLC，避免全市场接口失败拖累日 K。"""
    if ak is None:
        return None
    for _attempt in range(4):
        try:
            frame = ak.stock_bid_ask_em(symbol=code)
            if frame is None or frame.empty:
                continue
            values = {
                str(item.get("item", "")): item.get("value")
                for item in frame.to_dict(orient="records")
            }
            open_price = safe_float(values.get("今开"))
            high = safe_float(values.get("最高"))
            low = safe_float(values.get("最低"))
            close = safe_float(values.get("最新"))
            volume = safe_float(values.get("总手"))
            amount = safe_float(values.get("金额"))
            if None in {open_price, high, low, close, volume}:
                continue
            if min(open_price, high, low, close, volume) <= 0:
                continue
            if high < max(open_price, close) or low > min(open_price, close):
                continue
            fetched_at = datetime.now().isoformat(timespec="seconds")
            return (
                {
                    "time": trade_date,
                    "open": open_price,
                    "high": high,
                    "low": low,
                    "close": close,
                    "volume": volume,
                    "amount": amount,
                },
                {
                    "source": "AKShare / 东方财富个股盘口",
                    "quote_time": fetched_at,
                    "fetched_at": fetched_at,
                },
            )
        except Exception:
            continue
    return None


@app.post("/api/screener", tags=["选股"])
async def screen(request: ScreenerRequest):
    return await run_in_threadpool(market_service.screen, request)


@app.get("/api/stocks/{code}/intraday", tags=["股票"])
async def stock_intraday(code: str):
    if len(code) != 6 or not code.isdigit():
        raise HTTPException(status_code=422, detail="股票代码必须是 6 位数字")
    return await run_in_threadpool(get_intraday, code)


@app.get("/api/strategies/catalog", tags=["策略工坊"])
async def strategy_catalog():
    return await run_in_threadpool(strategy_catalog_metadata)


@app.get("/api/strategies", tags=["策略工坊"])
async def strategies():
    return await run_in_threadpool(list_strategies)


@app.get("/api/strategies/{strategy_id}", tags=["策略工坊"])
async def strategy_detail(strategy_id: str):
    try:
        return await run_in_threadpool(get_strategy, strategy_id)
    except StrategyNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/strategies", tags=["策略工坊"])
async def strategy_create(payload: StrategyPayload):
    try:
        return await run_in_threadpool(create_strategy, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.put("/api/strategies/{strategy_id}", tags=["策略工坊"])
async def strategy_update(strategy_id: str, payload: StrategyPayload):
    try:
        return await run_in_threadpool(update_strategy, strategy_id, payload)
    except StrategyNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/strategies/{strategy_id}/copy", tags=["策略工坊"])
async def strategy_copy(strategy_id: str):
    try:
        return await run_in_threadpool(copy_strategy, strategy_id)
    except StrategyNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/strategies/{strategy_id}/reset", tags=["策略工坊"])
async def strategy_reset(strategy_id: str):
    try:
        return await run_in_threadpool(reset_builtin_strategy, strategy_id)
    except StrategyNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.delete("/api/strategies/{strategy_id}", tags=["策略工坊"])
async def strategy_delete(strategy_id: str):
    try:
        await run_in_threadpool(delete_strategy, strategy_id)
        return {"message": "策略已删除"}
    except StrategyNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/strategy-lab/evaluate", tags=["策略实验室"])
async def strategy_lab_evaluate(request: StrategyLabRequest):
    try:
        return await run_in_threadpool(evaluate_strategy_basket, request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/backtest", tags=["策略验证"])
async def backtest(request: StrategyBacktestRequest):
    try:
        return await run_in_threadpool(run_strategy_backtest, request)
    except StrategyNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/ai/status", tags=["AI联合分析"])
async def ai_status(test_connection: bool = False):
    return await run_in_threadpool(ai_service_status, test_connection)


@app.post("/api/ai/analyze", tags=["AI联合分析"])
async def ai_analyze(request: AiAnalysisRequest):
    try:
        return await run_in_threadpool(
            analyze_stock_with_ai,
            request.code,
            request.depth,
        )
    except AiServiceError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/api/ai/trade-review", tags=["交易复盘"])
async def ai_trade_review(request: TradeReviewRequest):
    try:
        return await run_in_threadpool(review_trade, request)
    except AiServiceError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/api/ai/history", tags=["AI联合分析"])
async def ai_history(
    code: str | None = None,
    limit: int = Query(default=20, ge=1, le=100),
):
    return await run_in_threadpool(list_ai_history, code, limit)


@app.get("/api/ai/runs/{run_id}", tags=["AI联合分析"])
async def ai_run(run_id: int):
    try:
        return await run_in_threadpool(get_ai_run, run_id)
    except AiServiceError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/data/status", tags=["数据"])
async def data_status():
    return await run_in_threadpool(market_service.data_status)


@app.post("/api/data/refresh/all", tags=["数据"])
async def refresh_all():
    return await run_in_threadpool(refresh_all_data)


@app.post("/api/data/warmup", tags=["数据"])
async def warmup_data():
    """使用缓存立即响应，并按数据层冷却规则更新。"""
    quotes, meta = await run_in_threadpool(data_source.get_spot_quotes)
    return {"message": "行情缓存已检查", "count": len(quotes), "meta": meta}

@app.post("/api/data/refresh/quotes", tags=["数据"])
async def refresh_quotes():
    return await run_in_threadpool(market_service.refresh_quotes)


@app.get("/api/parallel-research", tags=["并行研究"])
async def parallel_research_view(
    mode: Literal["short", "swing"] = "short",
    period: Literal["holdout", "year"] = "holdout",
):
    return await run_in_threadpool(parallel_research, mode, period)


@app.post("/api/parallel-research/refresh", tags=["并行研究"])
async def parallel_research_refresh():
    return start_parallel_refresh()


@app.get("/api/parallel-research/archive", tags=["并行研究"])
async def parallel_research_archive():
    return await run_in_threadpool(latest_archive)


# 云端部署时由 FastAPI 同时提供前端静态文件；本地开发仍可使用 Vite。
frontend_dir = settings.project_dir / "dist"
if frontend_dir.exists():
    app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")
