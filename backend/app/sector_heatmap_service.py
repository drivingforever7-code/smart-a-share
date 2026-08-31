from __future__ import annotations

import json
import math
import threading
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from datetime import datetime
from typing import Any

try:
    import akshare as ak
except ImportError:  # pragma: no cover
    ak = None

from .ai_analysis_service import AiServiceError, _chat_json
from .config import settings
from .reliable_data_source import data_source


_KIND_CONFIG = {
    "industry": {
        "label": "行业板块",
        "rank_func": "stock_board_industry_name_em",
        "members_func": "stock_board_industry_cons_em",
        "fund_type": "行业资金流",
    },
    "concept": {
        "label": "概念板块",
        "rank_func": "stock_board_concept_name_em",
        "members_func": "stock_board_concept_cons_em",
        "fund_type": "概念资金流",
    },
}
_CACHE_SECONDS = 30
_AI_CACHE_SECONDS = 1800
_MEMBER_CACHE_SECONDS = 60


def _number(value: Any) -> float | None:
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def _pick(row: dict[str, Any], *names: str) -> Any:
    for name in names:
        if name in row and row[name] not in (None, "", "-"):
            return row[name]
    return None


def _clamp(value: float, low: float = 0, high: float = 100) -> float:
    return max(low, min(high, value))


def _call_with_timeout(function, *args, timeout: int = 18, **kwargs):
    executor = ThreadPoolExecutor(max_workers=1)
    future = executor.submit(function, *args, **kwargs)
    try:
        return future.result(timeout=timeout)
    except FutureTimeoutError as exc:
        future.cancel()
        raise RuntimeError("板块数据源响应超时") from exc
    finally:
        executor.shutdown(wait=False, cancel_futures=True)


class SectorHeatmapService:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._ranking_cache: dict[str, tuple[float, dict[str, Any]]] = {}
        self._member_cache: dict[tuple[str, str], tuple[float, list[dict[str, Any]]]] = {}
        self._ai_cache: dict[str, tuple[float, dict[str, dict[str, Any]]]] = {}

    def rankings(
        self,
        kind: str = "industry",
        *,
        force: bool = False,
        with_ai: bool = True,
    ) -> dict[str, Any]:
        config = self._config(kind)
        now = time.monotonic()
        cached = self._ranking_cache.get(kind)
        if cached and not force and now - cached[0] < _CACHE_SECONDS:
            result = json.loads(json.dumps(cached[1], ensure_ascii=False))
            result["meta"]["is_cached"] = True
        else:
            try:
                result = self._load_rankings(kind, config)
                with self._lock:
                    self._ranking_cache[kind] = (now, result)
            except Exception as exc:
                if not cached:
                    raise RuntimeError(f"板块热力数据获取失败：{exc}") from exc
                result = json.loads(json.dumps(cached[1], ensure_ascii=False))
                result["meta"].update(
                    {
                        "is_cached": True,
                        "status": "stale",
                        "error": str(exc),
                    }
                )

        if with_ai:
            self._apply_ai(kind, result)
        else:
            result["ai"] = {
                "status": "not_requested",
                "configured": bool(settings.deepseek_api_key),
            }
        result["ifind"] = {
            "configured": bool(settings.ifind_access_token),
            "status": "configured_unverified" if settings.ifind_access_token else "waiting_credentials",
            "message": (
                "已配置 iFinD 授权，但尚需在线连通性验证后才能切换"
                if settings.ifind_access_token
                else "未配置 iFinD access token，当前使用东方财富/AKShare"
            ),
        }
        return result

    def detail(self, kind: str, name: str, *, with_ai: bool = True) -> dict[str, Any]:
        ranking = self.rankings(kind, with_ai=with_ai)
        sector = next((item for item in ranking["items"] if item["name"] == name), None)
        if sector is None:
            raise LookupError("未找到该板块")
        members = self._members(kind, name)
        if not members and sector.get("leader"):
            try:
                from .market_service import market_service
                matches = market_service.search(str(sector["leader"]), 5)
                exact = next(
                    (item for item in matches if item.get("name") == sector["leader"]),
                    matches[0] if matches else None,
                )
                if exact:
                    members = [{
                        "code": str(exact.get("code") or "").zfill(6),
                        "name": str(exact.get("name") or sector["leader"]),
                        "price": _number(exact.get("price")),
                        "change_pct": _number(exact.get("change_pct")),
                        "amount": _number(exact.get("amount")),
                        "turnover_rate": _number(exact.get("turnover_rate")),
                        "amplitude": _number(exact.get("amplitude")),
                        "pe": _number(exact.get("pe")),
                        "pb": _number(exact.get("pb")),
                        "market_cap": _number(exact.get("market_cap")),
                    }]
            except Exception:
                members = []
        by_amount = sorted(
            members,
            key=lambda item: item.get("amount") or 0,
            reverse=True,
        )
        by_change = sorted(
            members,
            key=lambda item: item.get("change_pct") if item.get("change_pct") is not None else -999,
            reverse=True,
        )
        positive = sum((item.get("change_pct") or 0) > 0 for item in members)
        negative = sum((item.get("change_pct") or 0) < 0 for item in members)
        return {
            "sector": sector,
            "description": self._description(sector, len(members), positive, negative),
            "core_stocks": by_amount[:8],
            "sentiment_stocks": by_change[:8],
            "members": by_change,
            "breadth": {
                "total": len(members),
                "up": positive,
                "down": negative,
                "flat": max(0, len(members) - positive - negative),
            },
            "meta": ranking["meta"],
            "ai": ranking["ai"],
            "ifind": ranking["ifind"],
        }

    def _load_rankings(self, kind: str, config: dict[str, str]) -> dict[str, Any]:
        if ak is None:
            raise RuntimeError("AKShare 尚未安装")
        rank_function = getattr(ak, config["rank_func"], None)
        if rank_function is None:
            raise RuntimeError("当前 AKShare 版本不支持板块排行")
        try:
            frame = _call_with_timeout(rank_function)
        except Exception:
            if kind == "industry":
                return self._load_industry_from_spot()
            return self._load_ths_summary(kind)
        if frame is None or frame.empty:
            raise RuntimeError("板块排行返回空数据")

        fund_rows: list[dict[str, Any]] = []
        fund_function = getattr(ak, "stock_sector_fund_flow_rank", None)
        if fund_function is not None:
            try:
                fund_frame = _call_with_timeout(
                    fund_function,
                    indicator="今日",
                    sector_type=config["fund_type"],
                )
                if fund_frame is not None and not fund_frame.empty:
                    fund_rows = fund_frame.to_dict(orient="records")
            except Exception:
                fund_rows = []
        fund_map = {
            str(_pick(row, "名称", "板块名称", "行业")).strip(): row
            for row in fund_rows
            if _pick(row, "名称", "板块名称", "行业")
        }

        items: list[dict[str, Any]] = []
        for row in frame.to_dict(orient="records"):
            name = str(_pick(row, "板块名称", "名称") or "").strip()
            if not name:
                continue
            fund = fund_map.get(name, {})
            change_pct = _number(_pick(row, "涨跌幅", "今日涨跌幅"))
            up_count = int(_number(_pick(row, "上涨家数")) or 0)
            down_count = int(_number(_pick(row, "下跌家数")) or 0)
            total = up_count + down_count
            breadth = up_count / total if total else 0.5
            net_inflow = _number(
                _pick(
                    fund,
                    "今日主力净流入-净额",
                    "主力净流入-净额",
                    "净流入",
                )
            )
            net_ratio = _number(
                _pick(
                    fund,
                    "今日主力净流入-净占比",
                    "主力净流入-净占比",
                    "净占比",
                )
            )
            strength = _clamp(
                50
                + (change_pct or 0) * 7
                + (breadth - 0.5) * 34
                + (net_ratio or 0) * 0.8
            )
            heat = _clamp(
                strength * 0.72
                + _clamp(50 + (net_ratio or 0) * 2.2) * 0.28
            )
            recommendation, reasons, risks = self._advice(
                strength,
                change_pct,
                breadth,
                net_inflow,
                net_ratio,
            )
            items.append(
                {
                    "kind": kind,
                    "name": name,
                    "code": str(_pick(row, "板块代码", "代码") or ""),
                    "change_pct": change_pct,
                    "price": _number(_pick(row, "最新价")),
                    "turnover_rate": _number(_pick(row, "换手率")),
                    "market_cap": _number(_pick(row, "总市值")),
                    "amount": _number(_pick(row, "成交额")),
                    "up_count": up_count,
                    "down_count": down_count,
                    "breadth": round(breadth * 100, 2),
                    "leader": str(_pick(row, "领涨股票", "领涨股") or ""),
                    "leader_change_pct": _number(
                        _pick(row, "领涨股票-涨跌幅", "领涨股-涨跌幅")
                    ),
                    "main_net_inflow": net_inflow,
                    "main_net_inflow_ratio": net_ratio,
                    "fund_flow_available": bool(fund),
                    "strength": round(strength, 2),
                    "heat": round(heat, 2),
                    "recommendation": recommendation,
                    "reasons": reasons,
                    "risks": risks,
                    "ai_score": None,
                    "ai_view": None,
                }
            )
        items.sort(
            key=lambda item: (
                item["heat"],
                item.get("main_net_inflow") or 0,
                item.get("change_pct") or -999,
            ),
            reverse=True,
        )
        for rank, item in enumerate(items, start=1):
            item["rank"] = rank

        fetched_at = datetime.now().isoformat(timespec="seconds")
        return {
            "kind": kind,
            "label": config["label"],
            "items": items,
            "overview": self._overview(items),
            "meta": {
                "fetched_at": fetched_at,
                "quote_time": None,
                "source": "AKShare / 东方财富板块排行与资金流",
                "is_cached": False,
                "status": "fresh",
                "refresh_seconds": _CACHE_SECONDS,
            },
        }

    def _load_ths_summary(self, kind: str) -> dict[str, Any]:
        if ak is None:
            raise RuntimeError("AKShare 尚未安装")
        function_name = (
            "stock_board_industry_summary_ths"
            if kind == "industry"
            else "stock_board_concept_summary_ths"
        )
        function = getattr(ak, function_name, None)
        if function is None:
            raise RuntimeError("当前 AKShare 版本不支持同花顺板块排行")
        frame = _call_with_timeout(function)
        if frame is None or frame.empty:
            raise RuntimeError("同花顺板块排行返回空数据")
        items: list[dict[str, Any]] = []
        for row in frame.to_dict(orient="records"):
            name = str(_pick(row, "板块", "名称", "概念名称") or "").strip()
            if not name:
                continue
            change_pct = _number(_pick(row, "涨跌幅"))
            up_count = int(_number(_pick(row, "上涨家数")) or 0)
            down_count = int(_number(_pick(row, "下跌家数")) or 0)
            total = up_count + down_count
            breadth = up_count / total if total else 0.5
            amount_yi = _number(_pick(row, "总成交额"))
            flow_yi = _number(_pick(row, "净流入"))
            net_ratio = (
                flow_yi / amount_yi * 100
                if flow_yi is not None and amount_yi not in (None, 0)
                else None
            )
            strength = _clamp(
                50 + (change_pct or 0) * 7 + (breadth - 0.5) * 34
                + (net_ratio or 0) * 0.8
            )
            heat = _clamp(
                strength * 0.72 + _clamp(50 + (net_ratio or 0) * 2.2) * 0.28
            )
            recommendation, reasons, risks = self._advice(
                strength,
                change_pct,
                breadth,
                None if flow_yi is None else flow_yi * 100_000_000,
                net_ratio,
            )
            if kind == "concept" and change_pct is None:
                event = str(_pick(row, "驱动事件") or "").strip()
                recommendation = "观望"
                reasons = [f"近期驱动：{event}" if event else "同花顺近期概念事件入选"]
                risks = ["备用源缺少实时涨跌和资金字段，不能据此给出买入建议"]
            items.append(
                {
                    "kind": kind,
                    "name": name,
                    "code": "",
                    "change_pct": change_pct,
                    "price": _number(_pick(row, "均价")),
                    "turnover_rate": None,
                    "market_cap": None,
                    "amount": None if amount_yi is None else amount_yi * 100_000_000,
                    "up_count": up_count,
                    "down_count": down_count,
                    "breadth": round(breadth * 100, 2),
                    "leader": str(_pick(row, "领涨股", "龙头股") or ""),
                    "leader_change_pct": _number(_pick(row, "领涨股-涨跌幅")),
                    "main_net_inflow": None if flow_yi is None else flow_yi * 100_000_000,
                    "main_net_inflow_ratio": None if net_ratio is None else round(net_ratio, 3),
                    "fund_flow_available": flow_yi is not None,
                    "strength": round(strength, 2),
                    "heat": round(heat, 2),
                    "recommendation": recommendation,
                    "reasons": reasons,
                    "risks": risks,
                    "ai_score": None,
                    "ai_view": None,
                }
            )
        if not items:
            raise RuntimeError("同花顺板块排行缺少可用记录")
        items.sort(
            key=lambda item: (
                item["heat"],
                item.get("main_net_inflow") or 0,
                item.get("change_pct") or -999,
            ),
            reverse=True,
        )
        for rank, item in enumerate(items, start=1):
            item["rank"] = rank
        return {
            "kind": kind,
            "label": _KIND_CONFIG[kind]["label"],
            "items": items,
            "overview": self._overview(items),
            "meta": {
                "fetched_at": datetime.now().isoformat(timespec="seconds"),
                "quote_time": None,
                "source": "AKShare / 同花顺行业排行或概念事件备用源",
                "is_cached": False,
                "status": "fallback",
                "refresh_seconds": _CACHE_SECONDS,
            },
        }
    def _load_industry_from_spot(self) -> dict[str, Any]:
        try:
            return self._load_ths_summary("industry")
        except Exception:
            pass
        quotes, meta = data_source.get_spot_quotes()
        groups: dict[str, list[dict[str, Any]]] = {}
        for quote in quotes:
            industry = str(quote.get("industry") or "").strip()
            if industry:
                groups.setdefault(industry, []).append(quote)
        items: list[dict[str, Any]] = []
        for name, rows in groups.items():
            changes = [
                value for value in (_number(row.get("change_pct")) for row in rows)
                if value is not None
            ]
            if not changes:
                continue
            up_count = sum(value > 0 for value in changes)
            down_count = sum(value < 0 for value in changes)
            breadth = up_count / len(changes)
            mean_change = sum(changes) / len(changes)
            strength = _clamp(50 + mean_change * 7 + (breadth - 0.5) * 34)
            heat = _clamp(strength * 0.82 + min(len(rows), 30) / 30 * 18)
            leader = max(
                rows,
                key=lambda row: _number(row.get("change_pct")) or -999,
            )
            recommendation, reasons, risks = self._advice(
                strength, mean_change, breadth, None, None
            )
            items.append(
                {
                    "kind": "industry",
                    "name": name,
                    "code": "",
                    "change_pct": round(mean_change, 3),
                    "price": None,
                    "turnover_rate": None,
                    "market_cap": sum(_number(row.get("market_cap")) or 0 for row in rows),
                    "amount": sum(_number(row.get("amount")) or 0 for row in rows),
                    "up_count": up_count,
                    "down_count": down_count,
                    "breadth": round(breadth * 100, 2),
                    "leader": str(leader.get("name") or ""),
                    "leader_change_pct": _number(leader.get("change_pct")),
                    "main_net_inflow": None,
                    "main_net_inflow_ratio": None,
                    "fund_flow_available": False,
                    "strength": round(strength, 2),
                    "heat": round(heat, 2),
                    "recommendation": recommendation,
                    "reasons": reasons,
                    "risks": risks,
                    "ai_score": None,
                    "ai_view": None,
                }
            )
        if not items:
            raise RuntimeError("全市场实时行情缺少可用行业字段")
        items.sort(key=lambda item: (item["heat"], item["change_pct"]), reverse=True)
        for rank, item in enumerate(items, start=1):
            item["rank"] = rank
        return {
            "kind": "industry",
            "label": "行业板块",
            "items": items,
            "overview": self._overview(items),
            "meta": {
                "fetched_at": datetime.now().isoformat(timespec="seconds"),
                "quote_time": meta.get("quote_time"),
                "source": f"{meta.get('source') or '全市场行情'} / 行业聚合回退",
                "is_cached": bool(meta.get("is_cached")),
                "status": "fallback",
                "refresh_seconds": _CACHE_SECONDS,
            },
        }
    def _members(self, kind: str, name: str) -> list[dict[str, Any]]:
        key = (kind, name)
        now = time.monotonic()
        cached = self._member_cache.get(key)
        if cached and now - cached[0] < _MEMBER_CACHE_SECONDS:
            return cached[1]
        config = self._config(kind)
        if ak is None:
            raise RuntimeError("AKShare 尚未安装")
        function = getattr(ak, config["members_func"], None)
        if function is None:
            raise RuntimeError("当前 AKShare 版本不支持板块成分")
        try:
            frame = _call_with_timeout(function, symbol=name)
            if frame is None or frame.empty:
                raise RuntimeError("板块成分返回空数据")
            members = []
            for row in frame.to_dict(orient="records"):
                code = str(_pick(row, "代码") or "").strip().zfill(6)
                stock_name = str(_pick(row, "名称") or "").strip()
                if len(code) != 6 or not code.isdigit() or not stock_name:
                    continue
                members.append(
                    {
                        "code": code,
                        "name": stock_name,
                        "price": _number(_pick(row, "最新价")),
                        "change_pct": _number(_pick(row, "涨跌幅")),
                        "amount": _number(_pick(row, "成交额")),
                        "turnover_rate": _number(_pick(row, "换手率")),
                        "amplitude": _number(_pick(row, "振幅")),
                        "pe": _number(_pick(row, "市盈率-动态", "市盈率")),
                        "pb": _number(_pick(row, "市净率")),
                        "market_cap": _number(_pick(row, "总市值", "流通市值")),
                    }
                )
            if not members:
                raise RuntimeError("板块成分没有可用股票")
            with self._lock:
                self._member_cache[key] = (now, members)
            return members
        except Exception as primary_error:
            if cached:
                return cached[1]
            try:
                quotes, _ = data_source.get_spot_quotes()
                members = []
                for row in quotes:
                    if str(row.get("industry") or "").strip() != name:
                        continue
                    code = str(row.get("code") or "").strip().zfill(6)
                    stock_name = str(row.get("name") or "").strip()
                    if len(code) != 6 or not code.isdigit() or not stock_name:
                        continue
                    members.append(
                        {
                            "code": code,
                            "name": stock_name,
                            "price": _number(row.get("price")),
                            "change_pct": _number(row.get("change_pct")),
                            "amount": _number(row.get("amount")),
                            "turnover_rate": _number(row.get("turnover_rate")),
                            "amplitude": _number(row.get("amplitude")),
                            "pe": _number(row.get("pe")),
                            "pb": _number(row.get("pb")),
                            "market_cap": _number(row.get("market_cap")),
                        }
                    )
                if members:
                    with self._lock:
                        self._member_cache[key] = (now, members)
                    return members
            except Exception:
                pass
            return []

    def _apply_ai(self, kind: str, result: dict[str, Any]) -> None:
        if not settings.deepseek_api_key:
            result["ai"] = {
                "status": "unavailable",
                "configured": False,
                "message": "未配置 DeepSeek，当前仅显示量化建议",
            }
            return
        cached = self._ai_cache.get(kind)
        now = time.monotonic()
        if cached and now - cached[0] < _AI_CACHE_SECONDS:
            ai_map = cached[1]
            status = "cached"
        else:
            compact = [
                {
                    "name": item["name"],
                    "change_pct": item["change_pct"],
                    "breadth": item["breadth"],
                    "strength": item["strength"],
                    "main_net_inflow": item["main_net_inflow"],
                    "main_net_inflow_ratio": item["main_net_inflow_ratio"],
                    "quant_recommendation": item["recommendation"],
                }
                for item in result["items"][:20]
            ]
            try:
                payload = _chat_json(
                    "你是A股板块轮动复核员。只基于输入数据，结合趋势、涨跌广度、资金流和追高风险，为每个板块给0到100的ai_score，并给action（买入关注、观望、卖出/回避之一）、一句理由和一句风险。返回JSON对象{sectors:[{name,ai_score,action,reason,risk}]}，不得承诺收益。",
                    json.dumps(
                        {
                            "kind": kind,
                            "as_of": result["meta"]["fetched_at"],
                            "sectors": compact,
                        },
                        ensure_ascii=False,
                    ),
                )
                ai_map = {
                    str(row.get("name")): {
                        "score": _clamp(_number(row.get("ai_score")) or 50),
                        "action": str(row.get("action") or "观望"),
                        "reason": str(row.get("reason") or ""),
                        "risk": str(row.get("risk") or ""),
                    }
                    for row in payload.get("sectors", [])
                }
                with self._lock:
                    self._ai_cache[kind] = (now, ai_map)
                status = "updated"
            except AiServiceError as exc:
                result["ai"] = {
                    "status": "fallback",
                    "configured": True,
                    "message": str(exc),
                }
                return
        for item in result["items"]:
            ai = ai_map.get(item["name"])
            if not ai:
                continue
            item["ai_score"] = round(ai["score"], 2)
            item["ai_view"] = ai
            item["combined_score"] = round(item["strength"] * 0.7 + ai["score"] * 0.3, 2)
        result["items"].sort(
            key=lambda item: item.get("combined_score", item["strength"]),
            reverse=True,
        )
        for rank, item in enumerate(result["items"], start=1):
            item["rank"] = rank
        result["ai"] = {
            "status": status,
            "configured": True,
            "model": settings.deepseek_model,
            "weight": 0.3,
        }

    @staticmethod
    def _overview(items: list[dict[str, Any]]) -> dict[str, Any]:
        if not items:
            return {
                "total": 0,
                "rising": 0,
                "falling": 0,
                "net_inflow": None,
                "strongest": None,
                "weakest": None,
            }
        flows = [
            item["main_net_inflow"]
            for item in items
            if item.get("main_net_inflow") is not None
        ]
        return {
            "total": len(items),
            "rising": sum((item.get("change_pct") or 0) > 0 for item in items),
            "falling": sum((item.get("change_pct") or 0) < 0 for item in items),
            "net_inflow": round(sum(flows), 2) if flows else None,
            "strongest": items[0]["name"],
            "weakest": min(items, key=lambda item: item["strength"])["name"],
        }

    @staticmethod
    def _advice(
        strength: float,
        change_pct: float | None,
        breadth: float,
        net_inflow: float | None,
        net_ratio: float | None,
    ) -> tuple[str, list[str], list[str]]:
        reasons = [
            f"量化强度 {strength:.1f}/100",
            f"上涨广度 {breadth * 100:.1f}%",
        ]
        if net_inflow is not None:
            reasons.append(
                f"主力资金{'净流入' if net_inflow >= 0 else '净流出'}"
            )
        risks = []
        if change_pct is not None and change_pct >= 4:
            risks.append("板块短时涨幅偏高，存在追高回落风险")
        if net_ratio is not None and net_ratio < 0:
            risks.append("主力净流入占比为负")
        if breadth < 0.4:
            risks.append("上涨股票占比偏低，板块内部一致性不足")
        if strength >= 72 and not risks:
            action = "买入关注"
        elif strength >= 52:
            action = "观望"
        else:
            action = "卖出/回避"
        return action, reasons, risks or ["板块轮动较快，需设置失效条件"]

    @staticmethod
    def _description(
        sector: dict[str, Any],
        total: int,
        positive: int,
        negative: int,
    ) -> str:
        flow = sector.get("main_net_inflow")
        flow_text = (
            "资金流数据暂缺"
            if flow is None
            else f"主力资金当前{'净流入' if flow >= 0 else '净流出'}"
        )
        return (
            f"{sector['name']}当前包含 {total} 只可用成分股，"
            f"上涨 {positive} 只、下跌 {negative} 只；{flow_text}。"
            "板块结论同时考虑价格强弱、上涨广度、资金方向与追高风险。"
        )

    @staticmethod
    def _config(kind: str) -> dict[str, str]:
        if kind not in _KIND_CONFIG:
            raise LookupError("未知板块类型")
        return _KIND_CONFIG[kind]


sector_heatmap_service = SectorHeatmapService()
