import type { DataMeta, Recommendation, ScoreMode } from './types'

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
