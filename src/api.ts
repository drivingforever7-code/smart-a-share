import type {
  BacktestRequest,
  BacktestResult,
  BarResponse,
  DataStatus,
  MarketOverview,
  Opportunity,
  Preset,
  ScoreMode,
  ScreenerFilters,
  ScreenerResponse,
  StockAnalysis,
} from './types'
import type {
  IntradayResponse,
  StrategyCatalog,
  StrategyDefinition,
  StrategyPayload,
} from './strategyTypes'
import type {
  AiAnalysisResult,
  AiDepth,
  AiHistoryItem,
  AiServiceStatus,
} from './aiTypes'
import type { StrategyLabResult } from './labTypes'
import type { AutoBacktestResponse } from './autoBacktestTypes'
import type { LimitBreakResponse } from './limitBreakTypes'

const API_BASE = import.meta.env.VITE_API_BASE ?? '/api'

export class ApiError extends Error {
  status: number
  detail?: string

  constructor(message: string, status: number, detail?: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.detail = detail
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...init?.headers,
    },
  })

  if (!response.ok) {
    let detail = ''
    try {
      const payload = await response.json()
      detail = payload.detail ?? payload.message ?? ''
    } catch {
      detail = await response.text()
    }
    throw new ApiError(detail || '数据服务暂时不可用', response.status, detail)
  }

  return response.json() as Promise<T>
}

export const api = {
  health: () => request<{ status: string; version: string }>('/health'),

  overview: () => request<MarketOverview>('/market/overview'),

  autoBacktest: (days = 5) =>
    request<AutoBacktestResponse>(`/auto-backtest?days=${days}`),

  limitBreaks: (days = 5) =>
    request<LimitBreakResponse>(`/limit-breaks?days=${days}&refresh=true`),

  opportunities: (mode: ScoreMode, limit = 20, preset?: string) => {
    const query = new URLSearchParams({ mode, limit: String(limit) })
    if (preset) query.set('preset', preset)
    return request<Opportunity[]>(`/market/opportunities?${query}`)
  },

  presets: () => request<Preset[]>('/presets'),

  searchStocks: (query: string) =>
    request<Opportunity[]>(`/stocks/search?q=${encodeURIComponent(query)}&limit=20`),

  stockAnalysis: (code: string, mode: ScoreMode) =>
    request<StockAnalysis>(`/stocks/${code}/analysis?mode=${mode}`),

  bars: (code: string, timeframe: string, limit = 250) =>
    request<BarResponse>(
      `/stocks/${code}/bars?timeframe=${encodeURIComponent(timeframe)}&limit=${limit}`,
    ),

  screen: (filters: ScreenerFilters) =>
    request<ScreenerResponse>('/screener', {
      method: 'POST',
      body: JSON.stringify(filters),
    }),

  backtest: (payload: BacktestRequest) =>
    request<BacktestResult>('/backtest', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  intraday: (code: string) =>
    request<IntradayResponse>(`/stocks/${code}/intraday`),

  strategies: () => request<StrategyDefinition[]>('/strategies'),

  strategyCatalog: () => request<StrategyCatalog>('/strategies/catalog'),

  createStrategy: (payload: StrategyPayload) =>
    request<StrategyDefinition>('/strategies', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  updateStrategy: (id: string, payload: StrategyPayload) =>
    request<StrategyDefinition>(`/strategies/${id}`, {
      method: 'PUT',
      body: JSON.stringify(payload),
    }),

  copyStrategy: (id: string) =>
    request<StrategyDefinition>(`/strategies/${id}/copy`, { method: 'POST' }),

  resetStrategy: (id: string) =>
    request<StrategyDefinition>(`/strategies/${id}/reset`, { method: 'POST' }),

  deleteStrategy: (id: string) =>
    request<{ message: string }>(`/strategies/${id}`, { method: 'DELETE' }),

  strategyLab: (payload: {
    codes: string[]
    strategy_ids: string[]
    start_date: string
    split_date: string
    end_date: string
  }) =>
    request<StrategyLabResult>('/strategy-lab/evaluate', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  aiStatus: (testConnection = false) =>
    request<AiServiceStatus>(`/ai/status?test_connection=${testConnection}`),

  aiAnalyze: (code: string, depth: AiDepth) =>
    request<AiAnalysisResult>('/ai/analyze', {
      method: 'POST',
      body: JSON.stringify({ code, depth }),
    }),

  aiHistory: (code?: string, limit = 20) => {
    const query = new URLSearchParams({ limit: String(limit) })
    if (code) query.set('code', code)
    return request<AiHistoryItem[]>(`/ai/history?${query}`)
  },

  aiRun: (id: number) => request<unknown>(`/ai/runs/${id}`),

  dataStatus: () => request<DataStatus>('/data/status'),

  refreshQuotes: () =>
    request<{ message: string; count: number; fetched_at: string }>('/data/refresh/quotes', {
      method: 'POST',
    }),
}
