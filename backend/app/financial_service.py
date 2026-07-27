from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

import pandas as pd
from sqlalchemy import func, select
from sqlalchemy.dialects.sqlite import insert

from .data_source import MarketDataError, ak, safe_float
from .database import SessionLocal
from .strategy_models import FinancialPeriod


FINANCIAL_SOURCE = "AKShare / 新浪财经历史财务指标"


def get_financial_history(
    code: str,
    *,
    start_year: int,
    force: bool = False,
) -> list[dict[str, Any]]:
    cached, last_fetch = _load_cached(code, start_year)
    fresh = last_fetch and datetime.now() - last_fetch < timedelta(days=7)
    if cached and fresh and not force:
        return cached

    try:
        if ak is None:
            raise MarketDataError("AKShare 尚未安装，无法获取历史财务数据")
        frame = ak.stock_financial_analysis_indicator(
            symbol=code,
            start_year=str(max(1990, start_year - 1)),
        )
        records = _normalize_financial_frame(code, frame)
        if not records:
            raise MarketDataError("历史财务接口没有返回可用报告")
        _persist(records)
        result, _ = _load_cached(code, start_year)
        return result
    except Exception as exc:
        if cached:
            return cached
        if isinstance(exc, MarketDataError):
            raise
        raise MarketDataError(f"历史财务数据获取失败：{exc}") from exc


def enrich_price_frame(
    frame: pd.DataFrame,
    periods: list[dict[str, Any]],
) -> pd.DataFrame:
    result = frame.copy()
    result["date"] = pd.to_datetime(result["date"])
    if not periods:
        for column in ["roe", "revenue_growth", "profit_growth", "pe", "pb"]:
            result[column] = float("nan")
        return result

    finance = pd.DataFrame(periods)
    finance["available_date"] = pd.to_datetime(finance["available_date"])
    finance = finance.sort_values("available_date")
    result = pd.merge_asof(
        result.sort_values("date"),
        finance[
            [
                "available_date",
                "roe",
                "revenue_growth",
                "profit_growth",
                "eps_annualized",
                "book_value_per_share",
            ]
        ],
        left_on="date",
        right_on="available_date",
        direction="backward",
    )
    result["pe"] = result["close"] / result["eps_annualized"].where(
        result["eps_annualized"] > 0
    )
    result["pb"] = result["close"] / result["book_value_per_share"].where(
        result["book_value_per_share"] > 0
    )
    return result


def financial_cache_status() -> dict[str, Any]:
    with SessionLocal() as session:
        count = session.scalar(select(func.count()).select_from(FinancialPeriod)) or 0
        latest = session.scalar(select(func.max(FinancialPeriod.fetched_at)))
    return {
        "records": count,
        "updated_at": latest.isoformat(timespec="seconds") if latest else None,
    }


def _normalize_financial_frame(
    code: str,
    frame: pd.DataFrame | None,
) -> list[dict[str, Any]]:
    if frame is None or frame.empty or "日期" not in frame.columns:
        return []
    fetched_at = datetime.now()
    records: list[dict[str, Any]] = []
    for raw in frame.to_dict(orient="records"):
        raw_date = raw.get("日期")
        if pd.isna(raw_date):
            continue
        report = pd.Timestamp(raw_date).date()
        eps = _first_number(
            raw,
            ["每股收益_调整后(元)", "加权每股收益(元)", "摊薄每股收益(元)"],
        )
        book_value = _first_number(
            raw,
            ["每股净资产_调整后(元)", "每股净资产_调整前(元)", "调整后的每股净资产(元)"],
        )
        records.append(
            {
                "code": code,
                "report_date": report.isoformat(),
                "available_date": _conservative_available_date(report).isoformat(),
                "roe": _first_number(
                    raw,
                    ["加权净资产收益率(%)", "净资产收益率(%)", "净资产报酬率(%)"],
                ),
                "revenue_growth": _first_number(
                    raw,
                    ["主营业务收入增长率(%)"],
                ),
                "profit_growth": _first_number(raw, ["净利润增长率(%)"]),
                "eps": eps,
                "eps_annualized": _annualize_eps(eps, report),
                "book_value_per_share": book_value,
                "source": FINANCIAL_SOURCE,
                "fetched_at": fetched_at,
            }
        )
    return records


def _conservative_available_date(report: date) -> date:
    month_day = (report.month, report.day)
    if month_day <= (3, 31):
        return date(report.year, 4, 30)
    if month_day <= (6, 30):
        return date(report.year, 8, 31)
    if month_day <= (9, 30):
        return date(report.year, 10, 31)
    return date(report.year + 1, 4, 30)


def _annualize_eps(eps: float | None, report: date) -> float | None:
    if eps is None:
        return None
    if report.month <= 3:
        return eps * 4
    if report.month <= 6:
        return eps * 2
    if report.month <= 9:
        return eps * 4 / 3
    return eps


def _first_number(raw: dict[str, Any], columns: list[str]) -> float | None:
    for column in columns:
        value = safe_float(raw.get(column))
        if value is not None:
            return value
    return None


def _persist(records: list[dict[str, Any]]) -> None:
    with SessionLocal.begin() as session:
        for start in range(0, len(records), 200):
            values = records[start : start + 200]
            stmt = insert(FinancialPeriod).values(values)
            stmt = stmt.on_conflict_do_update(
                index_elements=[FinancialPeriod.code, FinancialPeriod.report_date],
                set_={
                    key: getattr(stmt.excluded, key)
                    for key in values[0]
                    if key not in {"code", "report_date"}
                },
            )
            session.execute(stmt)


def _load_cached(
    code: str,
    start_year: int,
) -> tuple[list[dict[str, Any]], datetime | None]:
    with SessionLocal() as session:
        rows = session.scalars(
            select(FinancialPeriod)
            .where(
                FinancialPeriod.code == code,
                FinancialPeriod.report_date >= f"{start_year - 1}-01-01",
            )
            .order_by(FinancialPeriod.available_date.asc())
        ).all()
        last_fetch = max((row.fetched_at for row in rows), default=None)
        records = [
            {
                "code": row.code,
                "report_date": row.report_date,
                "available_date": row.available_date,
                "roe": row.roe,
                "revenue_growth": row.revenue_growth,
                "profit_growth": row.profit_growth,
                "eps": row.eps,
                "eps_annualized": row.eps_annualized,
                "book_value_per_share": row.book_value_per_share,
                "source": row.source,
            }
            for row in rows
        ]
    return records, last_fetch
