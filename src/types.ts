export type ScoreMode = 'short' | 'swing'

export type Recommendation =
  | '建议买入'
  | '建议小仓位试买'
  | '建议观察'
  | '暂不建议'
  | '建议回避'

export interface DataMeta {
  source: string
  quote_time?: string | null
  fetched_at: string
  is_cached: boolean
  cache_age_seconds?: number | null
  financial_note?: string
}

export interface Opportunity {
  code: string
  name: string
  market: string
  board: string
  industry?: string | null
  price: number | null
  change_pct: number | null
  amount: number | null
  turnover_rate: number | null
  volume_ratio: number | null
  pe: number | null
  pb: number | null
  total_market_cap: number | null
  score: number
  short_score: number
  swing_score: number
  score_change?: number | null
  recommendation: Recommendation
  confidence: number
  reasons: string[]
  risks: string[]
  entry_low?: number | null
  entry_high?: number | null
  stop_loss?: number | null
  invalidation: string
  meta: DataMeta
}

export interface MarketOverview {
  quote_count: number
  rising: number
  falling: number
  flat: number
  limit_up: number
  limit_down: number
  average_change_pct: number
  median_change_pct: number
  meta: DataMeta
}

export interface ScoreDimension {
  key: string
  name: string
  score: number
  max_score: number
  summary: string
}

export interface StockAnalysis extends Opportunity {
  mode: ScoreMode
  dimensions: ScoreDimension[]
  indicators: Record<string, number | null>
  data_completeness: number
}

export interface Bar {
  time: string
  open: number
  high: number
  low: number
  close: number
  volume: number
  amount?: number | null
}

export interface BarResponse {
  code: string
  timeframe: string
  bars: Bar[]
  meta: DataMeta
}

export interface Preset {
  id: string
  name: string
  mode: ScoreMode | 'both'
  description: string
  icon: string
}

export interface ScreenerFilters {
  mode: ScoreMode
  preset?: string | null
  boards: string[]
  industries: string[]
  min_score?: number | null
  min_change_pct?: number | null
  max_change_pct?: number | null
  min_turnover_rate?: number | null
  min_volume_ratio?: number | null
  min_pe?: number | null
  max_pe?: number | null
  min_pb?: number | null
  max_pb?: number | null
  min_market_cap?: number | null
  max_market_cap?: number | null
  include_st: boolean
  include_new: boolean
  page: number
  page_size: number
  sort_by: string
  sort_order: 'asc' | 'desc'
}

export interface ScreenerResponse {
  total: number
  page: number
  page_size: number
  items: Opportunity[]
  industries: string[]
  meta: DataMeta
}

export interface BacktestRequest {
  code: string
  strategy_id?: string
  preset?: string
  start_date?: string
  end_date?: string
  holding_days?: number
  max_holding_days?: number
  stop_loss_pct?: number
  take_profit_pct?: number
  commission_pct?: number
  slippage_pct?: number
  stamp_duty_pct?: number
}

export interface BacktestTrade {
  signal_date: string
  entry_date: string
  exit_date: string
  entry_price: number
  exit_price: number
  return_pct: number
  gross_return_pct?: number
  cost_pct?: number
  estimated_exit?: boolean
  exit_reason: string
  entry_score?: number
  exit_score?: number
}

export interface EquityPoint {
  date: string
  strategy: number
  benchmark: number
}

export interface BacktestMarker {
  date: string
  type: 'buy' | 'sell'
  price: number
  label: string
  detail: string
}

export interface BacktestResult {
  code: string
  name: string
  preset: string
  strategy_id?: string
  strategy_name?: string
  start_date: string
  end_date: string
  total_return: number
  annual_return: number
  max_drawdown: number
  sharpe_ratio: number
  win_rate: number
  trade_count: number
  profit_factor: number
  expectancy: number
  benchmark_return: number
  equity_curve: EquityPoint[]
  trades: BacktestTrade[]
  markers: BacktestMarker[]
  risk?: Record<string, number>
  meta: DataMeta
}

export interface DataStatusItem {
  key: string
  name: string
  status: 'ready' | 'empty' | 'stale' | 'error'
  records: number
  updated_at?: string | null
  description: string
}

export interface DataStatus {
  service: string
  database_path: string
  items: DataStatusItem[]
  akshare_available: boolean
}

export type PageKey =
  | 'dashboard'
  | 'autoBacktest'
  | 'limitBreaks'
  | 'screener'
  | 'ranking'
  | 'detail'
  | 'backtest'
  | 'ai'
  | 'workshop'
  | 'watchlist'
  | 'settings'
