export interface ResearchStock {
  code: string; name: string; price: number | null; score: number; symbol?: string
  confidence?: number; quote_time?: string; atr_pct?: number; risks?: string[]; reasons?: string[]
  tracking_return_pct?: number | null
}
export interface ResearchRun {
  metrics: { net_return_pct: number; max_drawdown_pct: number; win_rate_pct: number; closed_trades: number; invested_days: number; days: number }
  equity: { date: string; equity: number }[]
  trades: { symbol: string; signal_date: string; entry_date: string; exit_date: string; entry_price: number; exit_price: number; return_pct: number; reason: string }[]
}
export interface ParallelResearchData {
  mode: string; period: string; today: string; latest_date: string | null
  policy: { name: string; holding: number; stop_atr: number; trailing_atr: number; take_atr: number; max_gap: number }
  research: { baseline: ResearchRun; candidate: ResearchRun; benchmark: { price_return_pct: number } }
  state: { running: boolean; completed: number; total: number; message: string; error: string | null }
  history: { date: string; items: ResearchStock[]; reasons: string[]; old_items: ResearchStock[]; old_note: string;
    market: { coverage: number; stocks: number; expected: number; rising_ratio: number; above20_ratio: number } }[]
  seed: { date: string; note: string; items: ResearchStock[]; rising_ratio: number; above20_ratio: number }
  limitations: string[]
}
