export type SectorKind = 'industry' | 'concept'

export type SectorAdvice = '买入关注' | '观望' | '卖出/回避'

export type SectorItem = {
  rank: number
  kind: SectorKind
  name: string
  code: string
  change_pct: number | null
  price: number | null
  turnover_rate: number | null
  market_cap: number | null
  amount: number | null
  up_count: number
  down_count: number
  breadth: number
  leader: string
  leader_change_pct: number | null
  main_net_inflow: number | null
  main_net_inflow_ratio: number | null
  fund_flow_available: boolean
  strength: number
  heat: number
  recommendation: SectorAdvice
  reasons: string[]
  risks: string[]
  ai_score: number | null
  ai_view: {
    score: number
    action: SectorAdvice
    reason: string
    risk: string
  } | null
  combined_score?: number
}

export type SectorStock = {
  code: string
  name: string
  price: number | null
  change_pct: number | null
  amount: number | null
  turnover_rate: number | null
  amplitude: number | null
  pe: number | null
  pb: number | null
  market_cap: number | null
}

export type SectorProviderStatus = {
  configured: boolean
  status: string
  message?: string
}

export type SectorMeta = {
  fetched_at: string
  quote_time: string | null
  source: string
  is_cached: boolean
  status: string
  refresh_seconds: number
  error?: string
}

export type SectorHeatmapResponse = {
  kind: SectorKind
  label: string
  items: SectorItem[]
  overview: {
    total: number
    rising: number
    falling: number
    net_inflow: number | null
    strongest: string | null
    weakest: string | null
  }
  meta: SectorMeta
  ai: SectorProviderStatus & { model?: string; weight?: number }
  ifind: SectorProviderStatus
}

export type SectorDetailResponse = {
  sector: SectorItem
  description: string
  core_stocks: SectorStock[]
  sentiment_stocks: SectorStock[]
  members: SectorStock[]
  breadth: {
    total: number
    up: number
    down: number
    flat: number
  }
  meta: SectorMeta
  ai: SectorProviderStatus
  ifind: SectorProviderStatus
}
