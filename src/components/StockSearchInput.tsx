import { AutoComplete, Input } from 'antd'
import type { ReactNode } from 'react'
import { useEffect, useState } from 'react'
import { api } from '../api'
import type { Opportunity } from '../types'

export async function resolveStockQuery(query: string): Promise<Opportunity | null> {
  const normalized = query.trim()
  if (!normalized) return null
  const matches = await api.searchStocks(normalized)
  if (!matches.length) return null
  const lower = normalized.toLowerCase()
  return (
    matches.find(
      (item) => item.code === normalized || item.name.toLowerCase() === lower,
    ) ?? matches[0]
  )
}

export default function StockSearchInput({
  value,
  onChange,
  onSelect,
  placeholder = '输入6位代码、股票名称或拼音',
  className,
  enterButton = '查看',
  prefix,
}: {
  value: string
  onChange: (value: string) => void
  onSelect: (code: string) => void
  placeholder?: string
  className?: string
  enterButton?: ReactNode
  prefix?: ReactNode
}) {
  const [matches, setMatches] = useState<Opportunity[]>([])
  const [resolving, setResolving] = useState(false)

  useEffect(() => {
    const query = value.trim()
    if (!query) {
      setMatches([])
      return
    }
    const timer = window.setTimeout(() => {
      api.searchStocks(query).then(setMatches).catch(() => setMatches([]))
    }, 250)
    return () => window.clearTimeout(timer)
  }, [value])

  const submit = async (query: string) => {
    const normalized = query.trim()
    if (!normalized) return
    if (/^\d{6}$/.test(normalized)) {
      onSelect(normalized)
      return
    }
    setResolving(true)
    try {
      const match = await resolveStockQuery(normalized)
      if (match) onSelect(match.code)
    } finally {
      setResolving(false)
    }
  }

  return (
    <AutoComplete
      value={value}
      options={matches.map((item) => ({
        value: item.code,
        label: (
          <div className="search-option">
            <strong>{item.name}</strong>
            <span>{item.code} · {item.board}</span>
          </div>
        ),
      }))}
      onChange={onChange}
      onSelect={(code) => onSelect(String(code))}
      className={className}
    >
      <Input.Search
        prefix={prefix}
        placeholder={placeholder}
        enterButton={enterButton}
        loading={resolving}
        onSearch={(query) => void submit(query)}
      />
    </AutoComplete>
  )
}
