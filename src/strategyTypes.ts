import type { DataMeta, ScoreMode } from './types'

export type StrategyCategory = 'rule' | 'composite'
export type ConditionLogic = 'all' | 'any'
export type ConditionOperator =
  | 'gt'
  | 'gte'
  | 'lt'
  | 'lte'
  | 'between'
  | 'cross_above'
  | 'cross_below'
  | 'is_true'

export interface StrategyCondition {
  left: string
  operator: ConditionOperator
  right_type: 'value' | 'indicator'
  right: number | string | number[] | null
}

export interface RiskConfig {
  stop_loss_pct: number
  take_profit_pct: number
  max_holding_days: number
  commission_pct: number
  slippage_pct: number
  stamp_duty_pct: number
}

export interface RuleStrategyConfig {
  entry_logic: ConditionLogic
  entry_conditions: StrategyCondition[]
  exit_logic: ConditionLogic
  exit_conditions: StrategyCondition[]
  risk: RiskConfig
}

export interface StrategyComponent {
  strategy_id: string
  weight: number
}

export interface CompositeStrategyConfig {
  components: StrategyComponent[]
  trigger_score: number
  exit_score: number
  risk: RiskConfig
}

export interface StrategyDefinition {
  id: string
  name: string
  category: StrategyCategory
  mode: ScoreMode
  description: string
  icon: string
  config: RuleStrategyConfig | CompositeStrategyConfig
  is_builtin: boolean
  created_at: string
  updated_at: string
}

export interface StrategyPayload {
  name: string
  category: StrategyCategory
  mode: ScoreMode
  description: string
  icon: string
  config: RuleStrategyConfig | CompositeStrategyConfig
}

export interface StrategyCatalogItem {
  id: string
  name: string
  group?: string
  unit?: string
  supports_indicator?: boolean
}

export interface StrategyCatalog {
  indicators: StrategyCatalogItem[]
  operators: StrategyCatalogItem[]
}

export interface IntradayPoint {
  time: string
  price: number
  average_price: number
  volume: number
}

export interface IntradayResponse {
  code: string
  date: string | null
  points: IntradayPoint[]
  meta: DataMeta
}
