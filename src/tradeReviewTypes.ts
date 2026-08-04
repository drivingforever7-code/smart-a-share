export interface TradeReviewPayload {
  description: string
  code?: string
  trade_date?: string
  action: '买入' | '卖出' | '加仓' | '清仓' | '其他'
  price?: number
  position_pct?: number
}

export interface TradeReviewResult {
  request: TradeReviewPayload
  review: {
    verdict?: string
    score?: number
    entry_review?: string
    exit_review?: string
    position_review?: string
    discipline_review?: string
    mistakes?: string[]
    good_decisions?: string[]
    better_plan?: string[] | string
    missed_alternatives?: string[]
    improvement_actions?: string[]
    risks?: string[]
    data_limits?: string[]
  }
}
