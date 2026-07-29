export type LimitBreakOutcome = 'pending' | 'resealed' | 'failed'

export interface LimitBreakReview {
  summary: string
  strongest_factors: string[]
  prediction_correct: boolean
}

export interface LimitBreakItem {
  id: number
  trade_date: string
  code: string
  name: string
  industry?: string | null
  prediction_stage: 'midday' | 'afternoon' | 'close'
  observed_at: string
  first_limit_time?: string | null
  last_limit_time?: string | null
  price: number
  limit_price: number
  change_pct: number
  distance_to_limit_pct: number
  amount: number
  circulating_market_cap: number
  turnover_rate: number
  amplitude: number
  break_count: number
  limit_statistics: string
  streak_count: number
  market_seal_rate: number
  industry_heat: number
  predicted_probability: number
  probability_rank: number
  recommendation: '建议小仓位试买' | '建议观察' | '建议回避'
  position_pct: number
  reasons: string[]
  risks: string[]
  invalidation: string
  model_version: string
  outcome: LimitBreakOutcome
  eligible_for_evaluation: boolean
  review?: LimitBreakReview | null
  source: string
  observation_count: number
}

export interface LimitBreakDailyReview {
  trade_date: string
  total: number
  evaluated: number
  resealed: number
  failed: number
  reseal_rate: number | null
}

export interface CalibrationBand {
  range: string
  count: number
  average_probability: number
  actual_reseal_rate: number
}

export interface LimitBreakModelStats {
  active_model: string
  sample_count: number
  trading_days: number
  resealed_count: number
  failed_count: number
  reseal_rate: number | null
  brier_score: number | null
  accuracy: number | null
  calibration: CalibrationBand[]
  upgrade_gate: string
}

export interface LimitBreakResponse {
  days: number
  available_dates: string[]
  items: LimitBreakItem[]
  daily_reviews: LimitBreakDailyReview[]
  model_stats: LimitBreakModelStats
  capture?: {
    trade_date: string
    stage: string
    created: number
    broken_count: number
    resealed_count: number
    market_seal_rate: number
    source: string
    captured_at: string
  } | null
  warning?: string | null
  methodology: {
    prediction_rule: string
    source_url: string
    research_url: string
    risk_note: string
  }
}
