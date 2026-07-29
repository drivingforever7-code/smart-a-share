from __future__ import annotations

from typing import Any


INDICATORS = [
    {"id": "close", "name": "收盘价", "group": "价格", "unit": "元"},
    {"id": "change_pct", "name": "当日涨跌幅", "group": "价格", "unit": "%"},
    *[
        {"id": f"ma{days}", "name": f"MA{days}", "group": "均线", "unit": "元"}
        for days in [5, 10, 20, 60]
    ],
    {"id": "ma20_slope", "name": "MA20斜率", "group": "趋势质量", "unit": "%"},
    {"id": "ma60_slope", "name": "MA60斜率", "group": "趋势质量", "unit": "%"},
    {"id": "adx14", "name": "ADX14趋势强度", "group": "趋势质量", "unit": ""},
    {"id": "momentum20", "name": "20日动量", "group": "动量", "unit": "%"},
    {"id": "momentum60", "name": "60日动量", "group": "动量", "unit": "%"},
    {"id": "rsi14", "name": "RSI14", "group": "动量", "unit": ""},
    {"id": "macd_diff", "name": "MACD DIF", "group": "动量", "unit": ""},
    {"id": "macd_signal", "name": "MACD DEA", "group": "动量", "unit": ""},
    {"id": "macd_hist", "name": "MACD柱", "group": "动量", "unit": ""},
    {"id": "kdj_k", "name": "KDJ K", "group": "动量", "unit": ""},
    {"id": "kdj_d", "name": "KDJ D", "group": "动量", "unit": ""},
    {"id": "boll_upper", "name": "布林上轨", "group": "波动", "unit": "元"},
    {"id": "boll_mid", "name": "布林中轨", "group": "波动", "unit": "元"},
    {"id": "boll_lower", "name": "布林下轨", "group": "波动", "unit": "元"},
    {"id": "atr_pct", "name": "ATR波动率", "group": "波动", "unit": "%"},
    {"id": "volatility20", "name": "20日年化波动", "group": "波动", "unit": "%"},
    {"id": "volume_ratio_20", "name": "20日量比", "group": "量价资金", "unit": ""},
    {"id": "mfi14", "name": "MFI资金流量", "group": "量价资金", "unit": ""},
    {"id": "obv_slope20", "name": "OBV二十日强度", "group": "量价资金", "unit": "%"},
    {"id": "turnover_rate", "name": "换手率", "group": "量价资金", "unit": "%"},
    {"id": "high_breakout_20", "name": "突破20日新高", "group": "形态", "unit": ""},
    {"id": "donchian_low10", "name": "十日价格下轨", "group": "形态", "unit": "元"},
    {"id": "close_to_ma10_pct", "name": "偏离MA10", "group": "形态", "unit": "%"},
    {"id": "close_to_ma20_pct", "name": "偏离MA20", "group": "形态", "unit": "%"},
    {"id": "market_regime_up", "name": "沪深300顺风环境", "group": "市场环境", "unit": ""},
    {"id": "market_momentum20", "name": "沪深300二十日动量", "group": "市场环境", "unit": "%"},
    {"id": "factor_score", "name": "多因子共振分", "group": "多因子", "unit": "分"},
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


def c(left: str, operator: str, right: Any = None, right_type: str = "value"):
    return {
        "left": left,
        "operator": operator,
        "right_type": right_type,
        "right": right,
    }


BASE_RISK = {
    "stop_loss_pct": 7,
    "take_profit_pct": 16,
    "max_holding_days": 15,
    "commission_pct": 0.1,
    "slippage_pct": 0.05,
    "stamp_duty_pct": 0.05,
}


def rule(
    entry: list[dict[str, Any]],
    exits: list[dict[str, Any]],
    *,
    risk: dict[str, float] | None = None,
    entry_logic: str = "all",
    exit_logic: str = "any",
):
    return {
        "entry_logic": entry_logic,
        "entry_conditions": entry,
        "exit_logic": exit_logic,
        "exit_conditions": exits,
        "risk": {**BASE_RISK, **(risk or {})},
    }


BUILTIN_STRATEGIES = [
    {
        "id": "market_tailwind_trend",
        "name": "市场顺风趋势",
        "category": "rule",
        "mode": "swing",
        "icon": "🧭",
        "description": "只在沪深300顺风时寻找趋势向上、位置不过热的个股",
        "source": "Qlib + daily_stock_analysis",
        "config": rule(
            [
                c("market_regime_up", "is_true"),
                c("adx14", "gte", 18),
                c("ma20_slope", "gt", 0),
                c("close_to_ma20_pct", "between", [-2, 6]),
                c("volume_ratio_20", "between", [0.7, 2.2]),
            ],
            [
                c("close", "cross_below", "ma20", "indicator"),
                c("market_momentum20", "lt", -4),
            ],
            risk={"max_holding_days": 35, "stop_loss_pct": 8, "take_profit_pct": 24},
        ),
    },
    {
        "id": "volatility_adjusted_momentum",
        "name": "波动调整动量",
        "category": "rule",
        "mode": "short",
        "icon": "⚡",
        "description": "寻找有动量但波动和乖离尚未失控的短线机会",
        "source": "Qlib 因子思想 + TradingAgents",
        "config": rule(
            [
                c("market_regime_up", "is_true"),
                c("momentum20", "between", [3, 18]),
                c("atr_pct", "between", [1, 5.5]),
                c("rsi14", "between", [50, 72]),
                c("close", "gt", "ma20", "indicator"),
            ],
            [c("momentum20", "lt", 0), c("rsi14", "gte", 78)],
            risk={"max_holding_days": 12, "stop_loss_pct": 6, "take_profit_pct": 14},
        ),
    },
    {
        "id": "quality_breakout",
        "name": "高质量突破",
        "category": "rule",
        "mode": "short",
        "icon": "🚀",
        "description": "突破、趋势强度、成交量和波动率同时确认",
        "source": "daily_stock_analysis + QuantDinger",
        "config": rule(
            [
                c("market_regime_up", "is_true"),
                c("high_breakout_20", "is_true"),
                c("adx14", "gte", 20),
                c("volume_ratio_20", "between", [1.25, 3.5]),
                c("atr_pct", "lte", 6),
            ],
            [c("close", "cross_below", "donchian_low10", "indicator")],
            risk={"max_holding_days": 10, "stop_loss_pct": 6, "take_profit_pct": 15},
        ),
    },
    {
        "id": "trend_mean_reversion",
        "name": "趋势内均值回归",
        "category": "rule",
        "mode": "short",
        "icon": "🌊",
        "description": "只在上升结构中接回调，避免把持续下跌误判为超跌",
        "source": "daily_stock_analysis",
        "config": rule(
            [
                c("market_regime_up", "is_true"),
                c("ma20", "gt", "ma60", "indicator"),
                c("close_to_ma20_pct", "between", [-4, 1.5]),
                c("rsi14", "between", [38, 58]),
                c("volume_ratio_20", "lte", 1.15),
            ],
            [c("close", "cross_below", "ma60", "indicator"), c("rsi14", "gte", 72)],
            risk={"max_holding_days": 15, "stop_loss_pct": 6, "take_profit_pct": 13},
        ),
    },
    {
        "id": "capital_accumulation",
        "name": "资金累积确认",
        "category": "rule",
        "mode": "swing",
        "icon": "💧",
        "description": "用OBV、MFI和趋势共同识别持续资金累积",
        "source": "TradingAgents 技术分析角色",
        "config": rule(
            [
                c("market_regime_up", "is_true"),
                c("obv_slope20", "gt", 5),
                c("mfi14", "between", [50, 78]),
                c("ma20_slope", "gt", 0),
                c("volume_ratio_20", "lte", 2.5),
            ],
            [c("obv_slope20", "lt", -5), c("close", "cross_below", "ma20", "indicator")],
            risk={"max_holding_days": 30, "stop_loss_pct": 8, "take_profit_pct": 22},
        ),
    },
    {
        "id": "quality_growth_value",
        "name": "质量成长合理价",
        "category": "rule",
        "mode": "swing",
        "icon": "🌱",
        "description": "成长、ROE、估值和市场趋势共同确认，不追逐未验证故事",
        "source": "TradingAgents 基本面角色 + daily_stock_analysis",
        "config": rule(
            [
                c("market_regime_up", "is_true"),
                c("roe", "gte", 9),
                c("revenue_growth", "gte", 8),
                c("profit_growth", "gte", 8),
                c("pe", "between", [0, 45]),
                c("ma20", "gt", "ma60", "indicator"),
            ],
            [c("profit_growth", "lt", 0), c("close", "cross_below", "ma60", "indicator")],
            risk={"max_holding_days": 60, "stop_loss_pct": 10, "take_profit_pct": 30},
        ),
    },
    {
        "id": "multifactor_resonance",
        "name": "多因子共振",
        "category": "rule",
        "mode": "swing",
        "icon": "🧠",
        "description": "综合趋势、动量、低波和资金质量，降低单一指标误判",
        "source": "Microsoft Qlib Alpha 因子思想",
        "config": rule(
            [
                c("market_regime_up", "is_true"),
                c("factor_score", "gte", 66),
                c("atr_pct", "lte", 5.5),
                c("close_to_ma20_pct", "between", [-2, 8]),
            ],
            [c("factor_score", "lt", 45), c("market_momentum20", "lt", -4)],
            risk={"max_holding_days": 40, "stop_loss_pct": 8, "take_profit_pct": 24},
        ),
    },
    {
        "id": "risk_balanced_short",
        "name": "短线风险平衡",
        "category": "composite",
        "mode": "short",
        "icon": "⚖️",
        "description": "动量、突破和趋势内回调三类独立信号加权",
        "source": "TradingAgents 风险经理 + QuantDinger",
        "config": {
            "components": [
                {"strategy_id": "volatility_adjusted_momentum", "weight": 35},
                {"strategy_id": "quality_breakout", "weight": 35},
                {"strategy_id": "trend_mean_reversion", "weight": 30},
            ],
            "trigger_score": 30,
            "exit_score": 34,
            "risk": {**BASE_RISK, "max_holding_days": 12, "stop_loss_pct": 6, "take_profit_pct": 15},
        },
    },
    {
        "id": "risk_balanced_swing",
        "name": "波段风险平衡",
        "category": "composite",
        "mode": "swing",
        "icon": "🛡️",
        "description": "趋势、资金、质量成长与多因子信号加权",
        "source": "TradingAgents + Qlib",
        "config": {
            "components": [
                {"strategy_id": "market_tailwind_trend", "weight": 30},
                {"strategy_id": "capital_accumulation", "weight": 25},
                {"strategy_id": "quality_growth_value", "weight": 20},
                {"strategy_id": "multifactor_resonance", "weight": 25},
            ],
            "trigger_score": 25,
            "exit_score": 30,
            "risk": {**BASE_RISK, "max_holding_days": 40, "stop_loss_pct": 9, "take_profit_pct": 26},
        },
    },
]


LEGACY_BUILTIN_IDS = {
    "volume_breakout",
    "low_volume_pullback",
    "ma_bull",
    "oversold_rebound",
    "macd_cross",
    "strong_pullback",
    "value_trend",
    "earnings_growth",
    "short_composite",
    "swing_composite",
}

LEGACY_REPLACEMENTS = {
    "volume_breakout": "quality_breakout",
    "low_volume_pullback": "trend_mean_reversion",
    "ma_bull": "market_tailwind_trend",
    "oversold_rebound": "trend_mean_reversion",
    "macd_cross": "volatility_adjusted_momentum",
    "strong_pullback": "trend_mean_reversion",
    "value_trend": "quality_growth_value",
    "earnings_growth": "quality_growth_value",
    "short_composite": "risk_balanced_short",
    "swing_composite": "risk_balanced_swing",
}
