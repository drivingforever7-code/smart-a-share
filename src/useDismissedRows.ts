import { useCallback, useEffect, useMemo, useState } from 'react'

const PREFIX = 'smart-a-share:dismissed:'

function read(scope: string): string[] {
  try {
    const value = localStorage.getItem(`${PREFIX}${scope}`)
    return value ? JSON.parse(value) as string[] : []
  } catch {
    return []
  }
}

export function useDismissedRows(scope: string) {
  const [keys, setKeys] = useState<string[]>(() => read(scope))

  useEffect(() => setKeys(read(scope)), [scope])

  const dismissed = useMemo(() => new Set(keys), [keys])
  const dismiss = useCallback((key: string | number) => {
    const normalized = String(key)
    setKeys((current) => {
      if (current.includes(normalized)) return current
      const next = [...current, normalized]
      localStorage.setItem(`${PREFIX}${scope}`, JSON.stringify(next))
      return next
    })
  }, [scope])

  return { dismissed, dismiss }
}
