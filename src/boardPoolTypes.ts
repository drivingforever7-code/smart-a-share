export type BoardPoolType = 'streak' | 'down_repair'

export interface BoardPoolItem {
  id: number
  trade_date: string
  pool_type: BoardPoolType
  code: string
  name: string
  industry?: string | null
  rank: number
  predicted_at: string
  predicted_probability: number
  recommendation: string
  reasons: string[]
  risks: string[]
  features: Record<string, number>
  model_version: string
  outcome: 'pending' | 'success' | 'failed'
  outcome_date?: string | null
  review?: { prediction_correct: boolean; summary: string; main_factors: [string, number][] } | null
  source: string
}

export interface BoardPoolStats {
  pool_type: BoardPoolType
  sample_count: number
  trading_days: number
  success_rate: number | null
  accuracy: number | null
  brier_score: number | null
  method: string
}

export interface BoardPoolResponse {
  days: number
  available_dates: string[]
  items: BoardPoolItem[]
  stats: Record<BoardPoolType, BoardPoolStats>
  versions: Array<Record<string, unknown>>
  warning?: string | null
  methodology: Record<string, string>
}
