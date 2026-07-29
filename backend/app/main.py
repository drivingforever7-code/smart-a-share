from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .strategy_backtest_service import run_strategy_backtest
from .auto_backtest_service import auto_backtest, capture_mode_snapshot
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
from .config import settings
from .data_source import MarketDataError
from .database import init_database
from .ranking_optimizer_service import (
    ensure_baseline_versions,
    ranking_strategy_status,
)
from .intraday_service import get_intraday
from .market_service import market_service, presets
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
    ensure_baseline_versions()
    initialize_strategy_catalog()
    yield


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


@app.exception_handler(MarketDataError)
async def market_data_error_handler(_: Request, exc: MarketDataError) -> JSONResponse:
    return JSONResponse(status_code=503, content={"detail": str(exc)})


@app.get("/api/health", tags=["系统"])
async def health() -> dict[str, str]:
    return {"status": "ok", "version": settings.version}


@app.get("/api/market/overview", tags=["行情"])
async def market_overview():
    return await run_in_threadpool(market_service.overview)


@app.get("/api/market/opportunities", tags=["选股"])
async def opportunities(
    mode: Literal["short", "swing"] = "short",
    limit: int = Query(default=20, ge=1, le=500),
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
    return result


@app.get("/api/auto-backtest", tags=["自动回测"])
async def automatic_backtest(
    days: int = Query(default=5, ge=1, le=30),
):
    return await run_in_threadpool(auto_backtest, days)


@app.get("/api/ranking-strategies/status", tags=["自动回测"])
async def ranking_strategy_versions():
    return await run_in_threadpool(ranking_strategy_status)


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
    return {"code": code, "timeframe": timeframe, "bars": bars, "meta": meta}


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


@app.post("/api/data/refresh/quotes", tags=["数据"])
async def refresh_quotes():
    return await run_in_threadpool(market_service.refresh_quotes)


# 云端部署时由 FastAPI 同时提供前端静态文件；本地开发仍可使用 Vite。
frontend_dir = settings.project_dir / "dist"
if frontend_dir.exists():
    app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")
