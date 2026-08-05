export interface TradeReviewMessage {
  role: 'user' | 'assistant'
  content: string
}

export interface TradeReviewPayload {
  description: string
  history?: TradeReviewMessage[]
  code?: string
  trade_date?: string
  action?: '买入' | '卖出' | '加仓' | '清仓' | '其他'
  price?: number
  position_pct?: number
}

export interface TradeActionPlan {
  recommended_action?: '加仓' | '继续持有' | '减仓' | '清仓' | '等待' | '分批买入'
  action_summary?: string
  current_reference_price?: number | null
  target_price?: number | null
  second_target_price?: number | null
  stop_loss_price?: number | null
  add_or_rebuy_range?: [number, number] | null
  suggested_position_pct?: number | null
  holding_period?: string
  price_basis?: string
  trigger_plan?: string[]
  action_rationale?: string[]
}

export interface TradeReviewResult {
  request: TradeReviewPayload
  review: {
    reply?: string
    action_plan?: TradeActionPlan
    verdict?: string
    score?: number
    entry_review?: string
    exit_review?: string
    mistakes?: string[]
    risks?: string[]
    data_limits?: string[]
  }
}