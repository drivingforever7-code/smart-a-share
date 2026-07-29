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

export interface AutoBacktestResponse {
  days: number
  available_dates: string[]
  items: AutoBacktestItem[]
  summaries: Record<ScoreMode, AutoBacktestSummary>
  meta: DataMeta
  history_note: string
}
