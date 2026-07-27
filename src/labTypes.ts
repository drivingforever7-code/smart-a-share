export interface LabMetrics {
  stock_count: number
  trade_count: number
  win_rate: number
  profit_factor: number
  expectancy: number
  median_total_return: number
  median_max_drawdown: number
  median_sharpe: number
}

export interface LabRow {
  strategy_id: string
  strategy_name: string
  mode: 'short' | 'swing'
  in_sample: LabMetrics
  out_of_sample: LabMetrics
  assessment: string
}

export interface StrategyLabResult {
  codes: string[]
  start_date: string
  split_date: string
  end_date: string
  rows: LabRow[]
  errors: {
    strategy_id: string
    sample_type: string
    code: string
    error: string
  }[]
  method: {
    in_sample: string
    out_of_sample: string
    ranking: string
    limitations: string[]
  }
}
