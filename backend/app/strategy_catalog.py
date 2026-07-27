from __future__ import annotations

from typing import Any


INDICATORS = [
    {"id": "close", "name": "收盘价", "group": "价格", "unit": "元"},
    {"id": "change_pct", "name": "当日涨跌幅", "group": "价格", "unit": "%"},
    {"id": "ma5", "name": "MA5", "group": "均线", "unit": "元"},
    {"id": "ma10", "name": "MA10", "group": "均线", "unit": "元"},
    {"id": "ma20", "name": "MA20", "group": "均线", "unit": "元"},
    {"id": "ma60", "name": "MA60", "group": "均线", "unit": "元"},
    {"id": "macd_diff", "name": "MACD DIF", "group": "技术指标", "unit": ""},
    {"id": "macd_signal", "name": "MACD DEA", "group": "技术指标", "unit": ""},
    {"id": "macd_hist", "name": "MACD 柱", "group": "技术指标", "unit": ""},
    {"id": "rsi14", "name": "RSI14", "group": "技术指标", "unit": ""},
    {"id": "kdj_k", "name": "KDJ K", "group": "技术指标", "unit": ""},
    {"id": "kdj_d", "name": "KDJ D", "group": "技术指标", "unit": ""},
    {"id": "boll_upper", "name": "布林上轨", "group": "技术指标", "unit": "元"},
    {"id": "boll_mid", "name": "布林中轨", "group": "技术指标", "unit": "元"},
    {"id": "boll_lower", "name": "布林下轨", "group": "技术指标", "unit": "元"},
    {"id": "volume_ratio_20", "name": "20日量比", "group": "量价", "unit": ""},
    {"id": "turnover_rate", "name": "换手率", "group": "量价", "unit": "%"},
    {"id": "high_breakout_20", "name": "突破20日新高", "group": "形态", "unit": ""},
    {"id": "close_to_ma10_pct", "name": "偏离MA10", "group": "形态", "unit": "%"},
    {"id": "close_to_ma20_pct", "name": "偏离MA20", "group": "形态", "unit": "%"},
    {"id": "pe", "name": "历史估算PE", "group": "基本面", "unit": "倍"},
    {"id": "pb", "name": "历史估算PB", "group": "基本面", "unit": "倍"},
    {"id": "roe", "name": "ROE", "group": "基本面", "unit": "%"},
    {"id": "revenue_growth", "name": "营收增长", "group": "基本面", "unit": "%"},
    {"id": "profit_growth", "name": "利润增长", "group": "基本面", "unit": "%"},
]

OPERATORS = [
    {"id": "gt", "name": "大于", "supports_indicator": True},
    {"id": "gte", "name": "大于等于", "supports_indicator": True},
    {"id": "lt", "name": "小于", "supports_indicator": True},
    {"id": "lte", "name": "小于等于", "supports_indicator": True},
    {"id": "between", "name": "在区间内", "supports_indicator": False},
    {"id": "cross_above", "name": "上穿", "supports_indicator": True},
    {"id": "cross_below", "name": "下穿", "supports_indicator": True},
    {"id": "is_true", "name": "成立", "supports_indicator": False},
]


def condition(
    left: str,
    operator: str,
    right: float | list[float] | str | None,
    *,
    right_type: str = "value",
) -> dict[str, Any]:
    return {
        "left": left,
        "operator": operator,
        "right_type": right_type,
        "right": right,
    }


DEFAULT_RISK = {
    "stop_loss_pct": 7,
    "take_profit_pct": 15,
    "max_holding_days": 10,
    "commission_pct": 0.1,
}


def rule_config(
    entry: list[dict[str, Any]],
    exit_conditions: list[dict[str, Any]],
    *,
    entry_logic: str = "all",
    exit_logic: str = "any",
    risk: dict[str, float] | None = None,
) -> dict[str, Any]:
    return {
        "entry_logic": entry_logic,
        "entry_conditions": entry,
        "exit_logic": exit_logic,
        "exit_conditions": exit_conditions,
        "risk": {**DEFAULT_RISK, **(risk or {})},
    }


BUILTIN_STRATEGIES: list[dict[str, Any]] = [
    {
        "id": "volume_breakout",
        "name": "放量突破",
        "category": "rule",
        "mode": "short",
        "icon": "🚀",
        "description": "突破20日高点并伴随成交量放大",
        "config": rule_config(
            [
                condition("high_breakout_20", "is_true", None),
                condition("volume_ratio_20", "gte", 1.5),
            ],
            [condition("close", "cross_below", "ma10", right_type="indicator")],
            risk={"max_holding_days": 8, "stop_loss_pct": 6, "take_profit_pct": 12},
        ),
    },
    {
        "id": "low_volume_pullback",
        "name": "缩量回调",
        "category": "rule",
        "mode": "swing",
        "icon": "🌊",
        "description": "中期上升趋势中缩量回到关键均线",
        "config": rule_config(
            [
                condition("ma20", "gt", "ma60", right_type="indicator"),
                condition("close_to_ma10_pct", "between", [-2, 2]),
                condition("volume_ratio_20", "lte", 0.9),
            ],
            [condition("close", "cross_below", "ma20", right_type="indicator")],
            risk={"max_holding_days": 20, "stop_loss_pct": 8, "take_profit_pct": 18},
        ),
    },
    {
        "id": "ma_bull",
        "name": "均线多头",
        "category": "rule",
        "mode": "swing",
        "icon": "📈",
        "description": "价格与短中期均线形成多头排列",
        "config": rule_config(
            [
                condition("close", "gt", "ma5", right_type="indicator"),
                condition("ma5", "gt", "ma10", right_type="indicator"),
                condition("ma10", "gt", "ma20", right_type="indicator"),
            ],
            [condition("ma5", "cross_below", "ma10", right_type="indicator")],
            risk={"max_holding_days": 20},
        ),
    },
    {
        "id": "oversold_rebound",
        "name": "超跌反弹",
        "category": "rule",
        "mode": "short",
        "icon": "↗️",
        "description": "RSI从超卖区域恢复并出现正收益",
        "config": rule_config(
            [
                condition("rsi14", "cross_above", 30),
                condition("change_pct", "gt", 0),
            ],
            [condition("rsi14", "gte", 72)],
            risk={"max_holding_days": 6, "stop_loss_pct": 5, "take_profit_pct": 10},
        ),
    },
    {
        "id": "macd_cross",
        "name": "MACD 金叉",
        "category": "rule",
        "mode": "short",
        "icon": "✳️",
        "description": "MACD金叉并由中期均线过滤弱势信号",
        "config": rule_config(
            [
                condition("macd_diff", "cross_above", "macd_signal", right_type="indicator"),
                condition("close", "gt", "ma20", right_type="indicator"),
            ],
            [condition("macd_diff", "cross_below", "macd_signal", right_type="indicator")],
        ),
    },
    {
        "id": "strong_pullback",
        "name": "强势股回踩",
        "category": "rule",
        "mode": "short",
        "icon": "🪂",
        "description": "强趋势中回踩MA10附近后企稳",
        "config": rule_config(
            [
                condition("ma20", "gt", "ma60", right_type="indicator"),
                condition("close_to_ma10_pct", "between", [0, 2.5]),
                condition("change_pct", "gt", 0),
            ],
            [condition("close", "cross_below", "ma20", right_type="indicator")],
        ),
    },
    {
        "id": "value_trend",
        "name": "低估值趋势",
        "category": "rule",
        "mode": "swing",
        "icon": "💎",
        "description": "历史估值合理且中期趋势向上",
        "config": rule_config(
            [
                condition("pe", "between", [0, 35]),
                condition("pb", "between", [0, 4]),
                condition("ma20", "gt", "ma60", right_type="indicator"),
            ],
            [condition("close", "cross_below", "ma20", right_type="indicator")],
            risk={"max_holding_days": 30, "stop_loss_pct": 9, "take_profit_pct": 22},
        ),
    },
    {
        "id": "earnings_growth",
        "name": "业绩成长",
        "category": "rule",
        "mode": "swing",
        "icon": "🌱",
        "description": "历史营收利润增长、ROE与趋势共同确认",
        "config": rule_config(
            [
                condition("revenue_growth", "gte", 10),
                condition("profit_growth", "gte", 10),
                condition("roe", "gte", 8),
                condition("ma20", "gt", "ma60", right_type="indicator"),
            ],
            [condition("close", "cross_below", "ma20", right_type="indicator")],
            risk={"max_holding_days": 40, "stop_loss_pct": 10, "take_profit_pct": 25},
        ),
    },
    {
        "id": "short_composite",
        "name": "短线综合",
        "category": "composite",
        "mode": "short",
        "icon": "🧭",
        "description": "多种短线信号按权重综合，降低单一指标误判",
        "config": {
            "components": [
                {"strategy_id": "volume_breakout", "weight": 30},
                {"strategy_id": "macd_cross", "weight": 25},
                {"strategy_id": "strong_pullback", "weight": 25},
                {"strategy_id": "oversold_rebound", "weight": 20},
            ],
            "trigger_score": 50,
            "exit_score": 50,
            "risk": {**DEFAULT_RISK, "max_holding_days": 10},
        },
    },
    {
        "id": "swing_composite",
        "name": "波段综合",
        "category": "composite",
        "mode": "swing",
        "icon": "⚖️",
        "description": "趋势、回调、估值和成长策略按权重综合",
        "config": {
            "components": [
                {"strategy_id": "ma_bull", "weight": 30},
                {"strategy_id": "low_volume_pullback", "weight": 25},
                {"strategy_id": "value_trend", "weight": 25},
                {"strategy_id": "earnings_growth", "weight": 20},
            ],
            "trigger_score": 50,
            "exit_score": 50,
            "risk": {**DEFAULT_RISK, "max_holding_days": 30, "stop_loss_pct": 9, "take_profit_pct": 22},
        },
    },
]
