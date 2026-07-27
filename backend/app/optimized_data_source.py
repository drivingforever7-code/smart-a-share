from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import delete
from sqlalchemy.dialects.sqlite import insert

from .data_source import AkshareDataSource
from .database import Bar, Quote, SessionLocal, Stock


class OptimizedAkshareDataSource(AkshareDataSource):
    """在基础适配器之上使用 SQLite 批量更新，缩短全市场刷新时间。"""

    @staticmethod
    def _persist_quotes(records: list[dict[str, Any]], fetched_at: datetime) -> None:
        quote_columns = {
            column.name
            for column in Quote.__table__.columns
            if column.name != "code"
        }
        with SessionLocal.begin() as session:
            for start in range(0, len(records), 300):
                batch = records[start : start + 300]
                stock_values = [
                    {
                        "code": record["code"],
                        "name": record["name"],
                        "market": record["market"],
                        "board": record["board"],
                        "industry": record["industry"],
                        "is_st": record["is_st"],
                        "status": record["status"],
                        "updated_at": fetched_at,
                    }
                    for record in batch
                ]
                stock_stmt = insert(Stock).values(stock_values)
                stock_stmt = stock_stmt.on_conflict_do_update(
                    index_elements=[Stock.code],
                    set_={
                        key: getattr(stock_stmt.excluded, key)
                        for key in stock_values[0]
                        if key != "code"
                    },
                )
                session.execute(stock_stmt)

                quote_values = [
                    {
                        key: value
                        for key, value in record.items()
                        if key == "code" or key in quote_columns
                    }
                    for record in batch
                ]
                quote_stmt = insert(Quote).values(quote_values)
                quote_stmt = quote_stmt.on_conflict_do_update(
                    index_elements=[Quote.code],
                    set_={
                        key: getattr(quote_stmt.excluded, key)
                        for key in quote_values[0]
                        if key != "code"
                    },
                )
                session.execute(quote_stmt)

    @staticmethod
    def _persist_bars(
        code: str,
        timeframe: str,
        bars: list[dict[str, Any]],
        fetched_at: datetime,
    ) -> None:
        with SessionLocal.begin() as session:
            if timeframe.endswith("m"):
                session.execute(
                    delete(Bar).where(Bar.code == code, Bar.timeframe == timeframe)
                )
            values = [
                {
                    "code": code,
                    "timeframe": timeframe,
                    **item,
                    "fetched_at": fetched_at,
                    "source": "AKShare / 东方财富",
                }
                for item in bars
            ]
            if not values:
                return
            stmt = insert(Bar).values(values)
            stmt = stmt.on_conflict_do_update(
                index_elements=[Bar.code, Bar.timeframe, Bar.time],
                set_={
                    key: getattr(stmt.excluded, key)
                    for key in values[0]
                    if key not in {"code", "timeframe", "time"}
                },
            )
            session.execute(stmt)


data_source = OptimizedAkshareDataSource()
