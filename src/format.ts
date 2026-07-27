import dayjs from 'dayjs'
import type { Recommendation } from './types'

export function formatNumber(value?: number | null, digits = 2): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—'
  return value.toLocaleString('zh-CN', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })
}

export function formatAmount(value?: number | null): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—'
  if (Math.abs(value) >= 1e8) return `${formatNumber(value / 1e8)} 亿`
  if (Math.abs(value) >= 1e4) return `${formatNumber(value / 1e4)} 万`
  return formatNumber(value, 0)
}

export function formatMarketCap(value?: number | null): string {
  return formatAmount(value)
}

export function formatPercent(value?: number | null, withSign = false): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—'
  const sign = withSign && value > 0 ? '+' : ''
  return `${sign}${formatNumber(value)}%`
}

export function formatTime(value?: string | null): string {
  if (!value) return '时间未知'
  const parsed = dayjs(value)
  return parsed.isValid() ? parsed.format('MM-DD HH:mm:ss') : value
}

export function changeClass(value?: number | null): string {
  if (!value) return 'is-flat'
  return value > 0 ? 'is-up' : 'is-down'
}

export function recommendationColor(value: Recommendation): string {
  if (value === '建议买入') return 'red'
  if (value === '建议小仓位试买') return 'volcano'
  if (value === '建议观察') return 'gold'
  if (value === '建议回避') return 'green'
  return 'default'
}
