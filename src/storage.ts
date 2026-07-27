const WATCHLIST_KEY = 'smart-a-share:watchlist'
const SETTINGS_KEY = 'smart-a-share:settings'
const SCHEMES_KEY = 'smart-a-share:screener-schemes'

export interface LocalSettings {
  refreshSeconds: number
  includeSt: boolean
  includeNew: boolean
  includeSuspended: boolean
}

export interface SavedScheme {
  id: string
  name: string
  filters: Record<string, unknown>
  createdAt: string
}

const defaultSettings: LocalSettings = {
  refreshSeconds: 10,
  includeSt: false,
  includeNew: false,
  includeSuspended: false,
}

function readJson<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(key)
    return raw ? (JSON.parse(raw) as T) : fallback
  } catch {
    return fallback
  }
}

export function getWatchlist(): string[] {
  return readJson<string[]>(WATCHLIST_KEY, [])
}

export function toggleWatchlist(code: string): string[] {
  const current = getWatchlist()
  const next = current.includes(code)
    ? current.filter((item) => item !== code)
    : [...current, code]
  localStorage.setItem(WATCHLIST_KEY, JSON.stringify(next))
  window.dispatchEvent(new CustomEvent('watchlist-change', { detail: next }))
  return next
}

export function getSettings(): LocalSettings {
  return { ...defaultSettings, ...readJson<Partial<LocalSettings>>(SETTINGS_KEY, {}) }
}

export function saveSettings(settings: LocalSettings): void {
  localStorage.setItem(SETTINGS_KEY, JSON.stringify(settings))
  window.dispatchEvent(new CustomEvent('settings-change', { detail: settings }))
}

export function getSavedSchemes(): SavedScheme[] {
  return readJson<SavedScheme[]>(SCHEMES_KEY, [])
}

export function saveScheme(name: string, filters: Record<string, unknown>): SavedScheme[] {
  const schemes = getSavedSchemes()
  const next = [
    ...schemes.filter((item) => item.name !== name),
    {
      id: crypto.randomUUID(),
      name,
      filters,
      createdAt: new Date().toISOString(),
    },
  ]
  localStorage.setItem(SCHEMES_KEY, JSON.stringify(next))
  return next
}

export function deleteScheme(id: string): SavedScheme[] {
  const next = getSavedSchemes().filter((item) => item.id !== id)
  localStorage.setItem(SCHEMES_KEY, JSON.stringify(next))
  return next
}
