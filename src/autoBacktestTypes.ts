import type { DataMeta, Recommendation, ScoreMode } from './types'

export interface DailyActionHistory {
  advice_date: string
  current_price: number | null
  return_pct: number | null
  current_score: number | null
  action: string
  position_pct: number
  confidence: number
  reasons: string[]
  risks: string[]
  invalidation: string
  quote_time?: string | null
  source: string
}

export interface AutoBacktestItem {
  id: number
  discovery_date: string
  mode: ScoreMode
  rank: number
  code: string
  name: string
  industry?: string | null
  discovery_price: number
  current_price: number | null
  return_pct: number | null
  tracking_days: number
  discovery_score: number
  strategy_version: string
  recommendation: Recommendation
  confidence: number
  reasons: string[]
  risks: string[]
  quote_time?: string | null
  source: string
  current_quote_time?: string | null
  current_source?: string | null
  is_cached: boolean
  action_date: string
  action_advice: string
  action_position_pct: number
  current_score: number | null
  current_recommendation?: Recommendation | null
  action_confidence: number
  action_reasons: string[]
  action_risks: string[]
  action_invalidation: string
  advice_history: DailyActionHistory[]
}

export interface AutoBacktestLeader {
  code: string
  name: string
  return_pct: number
}

export interface AutoBacktestSummary {
  count: number
  priced_count: number
  average_return_pct: number | null
  positive_count: number
  best: AutoBacktestLeader | null
  worst: AutoBacktestLeader | null
}

export interface RankingOptimizationRun {
  run_date: string
  status: 'waiting' | 'activated' | 'rejected'
  candidate_version?: string | null
  sample_count: number
  trading_days: number
  metrics: Record<string, unknown>
  reason: string
  audit_samples?: Array<{
    sample_date: string
    split: 'train' | 'validation'
    code: string
    name: string
    features: Record<string, number>
    observations: Array<{ date: string; price: number; return_pct: number }>
    labels: { return_pct?: number | null; max_drawdown_pct?: number | null; positive?: boolean | null }
    candidate_score?: number | null
  }>
}

export interface RankingStrategyVersion {
  version: string
  status: string
  is_active: boolean
  trained_through?: string | null
  train_samples: number
  validation_samples: number
  validation_mean_return?: number | null
  validation_mean_drawdown?: number | null
  validation_positive_rate?: number | null
  activated_at?: string | null
  notes: string
}

export interface RankingStrategyStatus {
  active_version: string
  horizon_observations: number
  matured_samples: number
  pending_samples: number
  trading_days: number
  required_samples: number
  required_days: number
  sample_progress_pct: number
  day_progress_pct: number
  ready_for_optimization: boolean
  recent_runs: RankingOptimizationRun[]
  versions: RankingStrategyVersion[]
}

export interface AutoBacktestResponse {
  days: number
  available_dates: string[]
  items: AutoBacktestItem[]
  summaries: Record<ScoreMode, AutoBacktestSummary>
  meta: DataMeta
  training_cycle: {
    trade_date: string
    created_samples: number
    created_observations: number
    archived_after_clear?: number
    optimization: Record<ScoreMode, { mode: ScoreMode; status: string; reason?: string }>
  }
  strategy_optimization: Record<ScoreMode, RankingStrategyStatus>
  history_note: string
}
