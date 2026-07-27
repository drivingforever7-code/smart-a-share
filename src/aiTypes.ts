export type AiDepth = 'quick' | 'standard' | 'deep'

export interface AiServiceStatus {
  provider: string
  configured: boolean
  model: string
  base_url: string
  masked_key?: string | null
  connection: 'not_tested' | 'ok' | 'error'
  latency_ms?: number
  error?: string
}

export interface AiRoleReport {
  stance: string
  score: number
  summary: string
  evidence: string[]
  risks: string[]
  missing: string[]
}

export interface AiAnalysisResult {
  id: number
  code: string
  name: string
  created_at: string
  duration_ms: number
  rating: '强烈看多' | '看多' | '中性' | '看空' | '强烈看空'
  confidence: number
  action: string
  horizon: string
  summary: string
  bull_case: string[]
  bear_case: string[]
  risks: string[]
  invalidation: string[]
  checklist: string[]
  entry_plan: string
  position_note: string
  disagreement: string
  role_reports: Record<string, AiRoleReport>
  data_snapshot: {
    as_of: string
    quote_source?: string
    bar_source?: string
    financial_available_date?: string | null
    limitations: string[]
  }
  method: {
    provider: string
    model: string
    depth: AiDepth
    roles: string[]
    inspired_by: string[]
  }
}

export interface AiHistoryItem {
  id: number
  code: string
  name: string
  model: string
  depth: AiDepth
  status: 'running' | 'completed' | 'failed'
  rating?: string
  confidence?: number
  summary?: string
  error_message?: string | null
  duration_ms?: number | null
  created_at: string
}
