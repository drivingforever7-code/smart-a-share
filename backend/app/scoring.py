from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd


SHORT_WEIGHTS = {
    "trend": ("短期趋势", 25),
    "momentum": ("动量强度", 20),
    "volume": ("量价配合", 20),
    "intraday": ("盘中表现", 15),
    "pattern": ("形态位置", 10),
    "risk": ("风险控制", 10),
}

SWING_WEIGHTS = {
    "trend": ("中期趋势", 25),
    "quality": ("盈利质量", 20),
    "growth": ("成长能力", 15),
    "valuation": ("估值水平", 15),
    "volume": ("量价资金", 10),
    "timing": ("买入时机", 10),
    "risk": ("风险控制", 5),
}


def number(value: Any, default: float = 0.0) -> float:
    try:
        result = float(value)
        return result if math.isfinite(result) else default
    except (TypeError, ValueError):
        return default


def clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def bars_frame(bars: list[dict[str, Any]] | None) -> pd.DataFrame:
    if not bars:
        return pd.DataFrame()
    frame = pd.DataFrame(bars).copy()
    for column in ["open", "high", "low", "close", "volume", "amount"]:
        if column in frame:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
    return frame.dropna(subset=["open", "high", "low", "close", "volume"])


def calculate_indicators(frame: pd.DataFrame) -> dict[str, float | None]:
    if frame.empty:
        return {}
    close = frame["close"]
    high = frame["high"]
    low = frame["low"]
    volume = frame["volume"]
    result: dict[str, float | None] = {}

    for period in (5, 10, 20, 60):
        series = close.rolling(period).mean()
        result[f"MA{period}"] = _last(series)

    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    dif = ema12 - ema26
    dea = dif.ewm(span=9, adjust=False).mean()
    result["DIF"] = _last(dif)
    result["DEA"] = _last(dea)
    result["MACD"] = _last((dif - dea) * 2)

    delta = close.diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = -delta.clip(upper=0).rolling(14).mean()
    relative_strength = gain / loss.replace(0, np.nan)
    result["RSI14"] = _last(100 - 100 / (1 + relative_strength))

    low9 = low.rolling(9).min()
    high9 = high.rolling(9).max()
    rsv = (close - low9) / (high9 - low9).replace(0, np.nan) * 100
    k = rsv.ewm(com=2, adjust=False).mean()
    d = k.ewm(com=2, adjust=False).mean()
    result["KDJ_K"] = _last(k)
    result["KDJ_D"] = _last(d)
    result["KDJ_J"] = _last(3 * k - 2 * d)

    ma20 = close.rolling(20).mean()
    std20 = close.rolling(20).std()
    result["BOLL_UP"] = _last(ma20 + 2 * std20)
    result["BOLL_MID"] = _last(ma20)
    result["BOLL_LOW"] = _last(ma20 - 2 * std20)
    result["20日新高距离"] = (
        number(close.iloc[-1] / high.rolling(20).max().iloc[-1] - 1) * 100
        if len(frame) >= 20
        else None
    )
    result["20日量比"] = (
        number(volume.iloc[-1] / volume.rolling(20).mean().iloc[-1])
        if len(frame) >= 20
        else None
    )
    returns = close.pct_change()
    result["20日波动率"] = (
        number(returns.tail(20).std() * math.sqrt(252) * 100)
        if len(frame) >= 20
        else None
    )
    return result


def _last(series: pd.Series) -> float | None:
    if series.empty:
        return None
    value = series.iloc[-1]
    return number(value) if pd.notna(value) else None


def _dimension(
    key: str,
    weights: dict[str, tuple[str, int]],
    score: float,
    summary: str,
) -> dict[str, Any]:
    name, maximum = weights[key]
    return {
        "key": key,
        "name": name,
        "score": round(clamp(score, 0, maximum), 1),
        "max_score": maximum,
        "summary": summary,
    }


def short_score(
    quote: dict[str, Any],
    frame: pd.DataFrame,
    indicators: dict[str, float | None],
) -> list[dict[str, Any]]:
    change = number(quote.get("change_pct"))
    speed = number(quote.get("speed"))
    change_5m = number(quote.get("change_5m"))
    change_60d = number(quote.get("change_60d"))
    volume_ratio = number(quote.get("volume_ratio"))
    turnover = number(quote.get("turnover_rate"))
    amount = number(quote.get("amount"))
    amplitude = number(quote.get("amplitude"))
    price = number(quote.get("price"))
    open_price = number(quote.get("open"))
    high = number(quote.get("high"))
    low = number(quote.get("low"))

    ma5 = number(indicators.get("MA5"))
    ma10 = number(indicators.get("MA10"))
    ma20 = number(indicators.get("MA20"))
    rsi = number(indicators.get("RSI14"), 50)
    macd = number(indicators.get("MACD"))

    trend = 9.0
    trend_notes: list[str] = []
    if ma5 and ma10 and ma20 and price:
        trend = 4
        if price > ma5:
            trend += 5
        if ma5 > ma10:
            trend += 6
        if ma10 > ma20:
            trend += 6
        if len(frame) >= 8 and frame["close"].rolling(5).mean().iloc[-1] > frame["close"].rolling(5).mean().iloc[-4]:
            trend += 4
        trend_notes.append("均线多头" if ma5 > ma10 > ma20 else "均线尚未形成完整多头")
    else:
        trend += clamp(change_60d / 5, -4, 7)
        trend_notes.append("依据盘中和阶段涨幅估算，打开详情后补充均线")

    momentum = 7.0
    if 0.5 <= change <= 5:
        momentum += 5
    elif change > 7:
        momentum += 1
    elif change < -3:
        momentum -= 3
    momentum += clamp(speed * 2.2, -3, 4)
    momentum += clamp(change_5m * 1.8, -3, 3)
    if indicators:
        momentum += 3 if macd > 0 else -1
        momentum += 3 if 45 <= rsi <= 70 else (-2 if rsi > 80 else 0)
    momentum_summary = (
        "上涨动能较强且未明显过热"
        if momentum >= 14
        else "短期动能一般，需要等待进一步确认"
    )

    volume_score = 5.0
    volume_score += clamp((volume_ratio - 0.8) * 5, -2, 7)
    if 2 <= turnover <= 12:
        volume_score += 5
    elif turnover > 20:
        volume_score += 1
    if amount >= 5e8:
        volume_score += 3
    elif amount >= 1e8:
        volume_score += 2
    elif amount and amount < 3e7:
        volume_score -= 3
    volume_summary = (
        f"量比 {volume_ratio:.2f}，成交活跃"
        if volume_ratio >= 1.2
        else f"量比 {volume_ratio:.2f}，放量确认不足"
    )

    intraday = 6.0
    if price and open_price:
        intraday += 3 if price >= open_price else -2
    if high > low and price:
        position = (price - low) / (high - low)
        intraday += clamp((position - 0.4) * 7, -2, 4)
    intraday += clamp(speed * 1.6, -2, 3)
    intraday_summary = (
        "价格运行在日内相对强势区域"
        if intraday >= 10
        else "盘中强度普通，尚未形成明显优势"
    )

    pattern = 4.0
    high_distance = indicators.get("20日新高距离")
    if high_distance is not None:
        if -3 <= high_distance <= 0:
            pattern += 5
        elif high_distance < -12:
            pattern -= 1
    elif change >= 2 and volume_ratio >= 1.2:
        pattern += 3
    pattern_summary = (
        "接近阶段新高，存在突破特征"
        if pattern >= 7
        else "形态位置一般，需等待突破或企稳"
    )

    risk = 10.0
    if amplitude > 8:
        risk -= 3
    if abs(change) > 7:
        risk -= 3
    if turnover > 25:
        risk -= 2
    if amount and amount < 3e7:
        risk -= 4
    if quote.get("is_st"):
        risk = 0
    if quote.get("status") != "正常":
        risk = 0
    risk_summary = "当前规则风险可控" if risk >= 7 else "波动、追高或流动性风险偏高"

    return [
        _dimension("trend", SHORT_WEIGHTS, trend, "；".join(trend_notes)),
        _dimension("momentum", SHORT_WEIGHTS, momentum, momentum_summary),
        _dimension("volume", SHORT_WEIGHTS, volume_score, volume_summary),
        _dimension("intraday", SHORT_WEIGHTS, intraday, intraday_summary),
        _dimension("pattern", SHORT_WEIGHTS, pattern, pattern_summary),
        _dimension("risk", SHORT_WEIGHTS, risk, risk_summary),
    ]


def swing_score(
    quote: dict[str, Any],
    frame: pd.DataFrame,
    indicators: dict[str, float | None],
    fundamentals: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    fundamentals = fundamentals or {}
    change = number(quote.get("change_pct"))
    change_60d = number(quote.get("change_60d"))
    change_ytd = number(quote.get("change_ytd"))
    price = number(quote.get("price"))
    pe = number(quote.get("pe"))
    pb = number(quote.get("pb"))
    amount = number(quote.get("amount"))
    turnover = number(quote.get("turnover_rate"))
    volume_ratio = number(quote.get("volume_ratio"))
    ma20 = number(indicators.get("MA20"))
    ma60 = number(indicators.get("MA60"))

    trend = 9.0
    if ma20 and ma60 and price:
        trend = 5
        trend += 7 if price > ma20 else 0
        trend += 8 if ma20 > ma60 else 0
        if len(frame) >= 25 and frame["close"].rolling(20).mean().iloc[-1] > frame["close"].rolling(20).mean().iloc[-6]:
            trend += 5
        trend_summary = "中期均线保持上升趋势" if trend >= 18 else "中期趋势尚未完全转强"
    else:
        trend += clamp(change_60d / 3, -5, 9)
        trend += clamp(change_ytd / 10, -2, 5)
        trend_summary = "阶段涨幅偏强，详情页可补充中期均线" if trend >= 16 else "阶段趋势表现一般"

    roe = fundamentals.get("roe")
    quality = 8.0 if roe is None else clamp(number(roe) / 1.2, 0, 20)
    quality_summary = (
        "财务 ROE 数据暂缺，盈利质量按中性计分"
        if roe is None
        else f"ROE 为 {number(roe):.2f}%"
    )

    revenue_growth = fundamentals.get("revenue_growth")
    profit_growth = fundamentals.get("profit_growth")
    if revenue_growth is None and profit_growth is None:
        growth = 6.0
        growth_summary = "最新成长数据暂缺，成长能力按中性偏谨慎计分"
    else:
        growth = 4
        growth += clamp(number(revenue_growth) / 6, -3, 5)
        growth += clamp(number(profit_growth) / 5, -4, 6)
        growth_summary = "营收和利润增速支持波段逻辑" if growth >= 10 else "成长性未形成明显优势"

    valuation = 5.0
    if 0 < pe <= 20:
        valuation += 6
    elif 20 < pe <= 40:
        valuation += 4
    elif pe > 80 or pe < 0:
        valuation -= 2
    if 0 < pb <= 3:
        valuation += 4
    elif 3 < pb <= 6:
        valuation += 2
    elif pb > 10:
        valuation -= 2
    valuation_summary = (
        f"PE {pe:.2f}、PB {pb:.2f}，估值相对温和"
        if valuation >= 11
        else f"PE {pe:.2f}、PB {pb:.2f}，估值吸引力一般"
    )

    volume = 3.0
    if amount >= 5e8:
        volume += 3
    elif amount >= 1e8:
        volume += 2
    if 1 <= volume_ratio <= 2.5:
        volume += 2
    if 1 <= turnover <= 10:
        volume += 2
    volume_summary = "成交活跃且量价结构较健康" if volume >= 7 else "成交活跃度对波段支撑有限"

    timing = 5.0
    if -2 <= change <= 3:
        timing += 2
    if ma20 and price:
        distance = (price / ma20 - 1) * 100
        if -2 <= distance <= 5:
            timing += 3
        elif distance > 12:
            timing -= 3
    elif 0 < change_60d < 35:
        timing += 2
    timing_summary = "价格位置适合继续观察买点" if timing >= 7 else "当前位置追高或趋势确认不足"

    risk = 5.0
    if abs(change_60d) > 60:
        risk -= 2
    if number(quote.get("amplitude")) > 10:
        risk -= 1
    if amount and amount < 3e7:
        risk -= 2
    if quote.get("is_st") or quote.get("status") != "正常":
        risk = 0
    risk_summary = "中期风险未见明显异常" if risk >= 4 else "中期波动或交易风险偏高"

    return [
        _dimension("trend", SWING_WEIGHTS, trend, trend_summary),
        _dimension("quality", SWING_WEIGHTS, quality, quality_summary),
        _dimension("growth", SWING_WEIGHTS, growth, growth_summary),
        _dimension("valuation", SWING_WEIGHTS, valuation, valuation_summary),
        _dimension("volume", SWING_WEIGHTS, volume, volume_summary),
        _dimension("timing", SWING_WEIGHTS, timing, timing_summary),
        _dimension("risk", SWING_WEIGHTS, risk, risk_summary),
    ]


def hard_risks(quote: dict[str, Any]) -> list[str]:
    risks: list[str] = []
    price = number(quote.get("price"))
    amount = number(quote.get("amount"))
    change = number(quote.get("change_pct"))
    if not price:
        risks.append("最新价格缺失，可能停牌或数据异常")
    if quote.get("status") != "正常":
        risks.append(f"当前状态为{quote.get('status', '异常')}")
    if quote.get("is_st"):
        risks.append("ST 或退市风险股票")
    if amount and amount < 1e7:
        risks.append("成交额过低，可能难以正常买卖")
    if change >= 9.7:
        risks.append("接近涨停，无法按当前价格合理成交")
    return risks


def calculate_confidence(
    quote: dict[str, Any],
    mode: str,
    has_bars: bool,
    fundamentals: dict[str, Any] | None,
) -> float:
    quote_fields = [
        "price",
        "change_pct",
        "amount",
        "turnover_rate",
        "volume_ratio",
        "amplitude",
        "speed",
        "change_60d",
        "pe",
        "pb",
    ]
    available = sum(quote.get(key) is not None for key in quote_fields)
    confidence = 35 + available / len(quote_fields) * 35
    if has_bars:
        confidence += 22
    if mode == "swing":
        financial_fields = ["roe", "revenue_growth", "profit_growth"]
        values = fundamentals or {}
        confidence -= 10
        confidence += sum(values.get(key) is not None for key in financial_fields) / 3 * 18
    return round(clamp(confidence, 0, 100), 1)


def recommendation(score: float, confidence: float, blocking_risks: list[str]) -> str:
    if blocking_risks:
        return "建议回避"
    if score >= 80 and confidence >= 70:
        return "建议买入"
    if score >= 70 and confidence >= 55:
        return "建议小仓位试买"
    if score >= 60:
        return "建议观察"
    return "暂不建议"


def analyze(
    quote: dict[str, Any],
    mode: str,
    *,
    meta: dict[str, Any],
    bars: list[dict[str, Any]] | None = None,
    fundamentals: dict[str, Any] | None = None,
) -> dict[str, Any]:
    frame = bars_frame(bars)
    indicators = calculate_indicators(frame)
    short_dimensions = short_score(quote, frame, indicators)
    swing_dimensions = swing_score(quote, frame, indicators, fundamentals)
    short_total = round(sum(item["score"] for item in short_dimensions), 1)
    swing_total = round(sum(item["score"] for item in swing_dimensions), 1)
    dimensions = short_dimensions if mode == "short" else swing_dimensions
    total = short_total if mode == "short" else swing_total
    confidence = calculate_confidence(quote, mode, not frame.empty, fundamentals)
    blocking = hard_risks(quote)

    ranked = sorted(dimensions, key=lambda item: item["score"] / item["max_score"], reverse=True)
    reasons = [item["summary"] for item in ranked[:3] if item["score"] >= item["max_score"] * 0.55]
    if not reasons:
        reasons = ["当前指标组合尚未形成明确优势"]

    risks = list(blocking)
    change = number(quote.get("change_pct"))
    amplitude = number(quote.get("amplitude"))
    turnover = number(quote.get("turnover_rate"))
    if change > 7:
        risks.append("当日涨幅较大，存在追高回落风险")
    if amplitude > 8:
        risks.append("日内振幅较大，止损空间需要放宽")
    if turnover > 20:
        risks.append("换手率偏高，筹码可能不稳定")
    if mode == "swing" and not fundamentals:
        risks.append("财务成长数据尚未补齐，波段评分置信度受限")
    risks = list(dict.fromkeys(risks))[:3]

    price = number(quote.get("price"))
    ma10 = number(indicators.get("MA10"))
    ma20 = number(indicators.get("MA20"))
    support = ma10 if mode == "short" and ma10 else ma20 if ma20 else price * (0.96 if mode == "short" else 0.92)
    entry_low = min(price, support * 1.01) if price else None
    entry_high = price * (1.01 if mode == "short" else 1.015) if price else None
    stop_loss = min(support * 0.98, price * (0.95 if mode == "short" else 0.92)) if price else None
    invalidation = (
        f"收盘有效跌破参考支撑 {support:.2f}，或量价信号转弱"
        if support
        else "关键价格或趋势数据缺失时，当前信号自动失效"
    )

    return {
        "code": quote["code"],
        "name": quote["name"],
        "market": quote.get("market", ""),
        "board": quote.get("board", ""),
        "industry": quote.get("industry"),
        "price": quote.get("price"),
        "change_pct": quote.get("change_pct"),
        "amount": quote.get("amount"),
        "turnover_rate": quote.get("turnover_rate"),
        "volume_ratio": quote.get("volume_ratio"),
        "pe": quote.get("pe"),
        "pb": quote.get("pb"),
        "total_market_cap": quote.get("total_market_cap"),
        "score": total,
        "short_score": short_total,
        "swing_score": swing_total,
        "score_change": None,
        "recommendation": recommendation(total, confidence, blocking),
        "confidence": confidence,
        "reasons": reasons,
        "risks": risks,
        "entry_low": round(entry_low, 2) if entry_low else None,
        "entry_high": round(entry_high, 2) if entry_high else None,
        "stop_loss": round(stop_loss, 2) if stop_loss else None,
        "invalidation": invalidation,
        "meta": meta,
        "mode": mode,
        "dimensions": dimensions,
        "indicators": {key: round(value, 3) if value is not None else None for key, value in indicators.items()},
        "data_completeness": confidence,
    }


PRESETS = [
    {"id": "volume_breakout", "name": "放量突破", "mode": "short", "description": "突破压力位并伴随成交量放大", "icon": "🚀"},
    {"id": "low_volume_pullback", "name": "缩量回调", "mode": "both", "description": "上升趋势中回调，成交量逐步缩小", "icon": "🌊"},
    {"id": "ma_bull", "name": "均线多头", "mode": "both", "description": "短中期均线保持强势排列", "icon": "📈"},
    {"id": "oversold_rebound", "name": "超跌反弹", "mode": "short", "description": "短期超跌后的动能修复", "icon": "↗️"},
    {"id": "macd_cross", "name": "MACD 金叉", "mode": "both", "description": "动能金叉并通过趋势过滤", "icon": "✳️"},
    {"id": "strong_pullback", "name": "强势股回踩", "mode": "short", "description": "强势上涨后回踩关键位置企稳", "icon": "🪂"},
    {"id": "value_trend", "name": "低估值趋势", "mode": "swing", "description": "估值相对合理且中期趋势向上", "icon": "💎"},
    {"id": "earnings_growth", "name": "业绩成长", "mode": "swing", "description": "成长、估值和趋势共同确认", "icon": "🌱"},
]


def matches_preset(item: dict[str, Any], preset: str | None) -> bool:
    if not preset:
        return True
    quote = item
    change = number(quote.get("change_pct"))
    volume_ratio = number(quote.get("volume_ratio"))
    turnover = number(quote.get("turnover_rate"))
    change_60d = number(quote.get("change_60d"))
    pe = number(quote.get("pe"))
    pb = number(quote.get("pb"))
    if preset == "volume_breakout":
        return 1.5 <= change <= 8 and volume_ratio >= 1.3 and turnover >= 2
    if preset == "low_volume_pullback":
        return -3 <= change <= 1.5 and 5 <= change_60d <= 45 and 0 < volume_ratio <= 1
    if preset == "ma_bull":
        return change > 0 and change_60d > 5 and item.get("short_score", 0) >= 68
    if preset == "oversold_rebound":
        return change >= 1 and change_60d <= -8 and volume_ratio >= 1
    if preset == "macd_cross":
        return 0 < change <= 6 and change_60d > -5 and volume_ratio >= 1
    if preset == "strong_pullback":
        return -2.5 <= change <= 2 and change_60d >= 20 and turnover >= 2
    if preset == "value_trend":
        return 0 < pe <= 35 and 0 < pb <= 4 and change_60d > 3
    if preset == "earnings_growth":
        return 0 < pe <= 60 and change_60d > 5 and item.get("swing_score", 0) >= 65
    return True
