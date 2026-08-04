const PURCHASED_KEY = 'smart-a-share:purchased'
const TRADE_JOURNAL_KEY = 'smart-a-share:trade-journal'
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

export interface PurchasedStock {
  code: string
  name?: string
  buyPrice?: number
  buyDate?: string
  addedAt: string
}

export interface TradeJournalEntry {
  id: string
  createdAt: string
  payload: any
  review?: Record<string, unknown>
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
  return getPurchasedStocks().map((item) => item.code)
}

export function toggleWatchlist(code: string): string[] {
  const existing = getPurchasedStocks()
  if (existing.some((item) => item.code === code)) removePurchasedStock(code)
  else savePurchasedStock({ code })
  return getWatchlist()
}

export function getPurchasedStocks(): PurchasedStock[] {
  return readJson<PurchasedStock[]>(PURCHASED_KEY, [])
}

export function savePurchasedStock(input: Omit<PurchasedStock, 'addedAt'>): PurchasedStock[] {
  const next = [
    { ...input, addedAt: new Date().toISOString() },
    ...getPurchasedStocks().filter((item) => item.code !== input.code),
  ]
  localStorage.setItem(PURCHASED_KEY, JSON.stringify(next))
  window.dispatchEvent(new CustomEvent('purchased-change', { detail: next }))
  return next
}

export function removePurchasedStock(code: string): PurchasedStock[] {
  const next = getPurchasedStocks().filter((item) => item.code !== code)
  localStorage.setItem(PURCHASED_KEY, JSON.stringify(next))
  window.dispatchEvent(new CustomEvent('purchased-change', { detail: next }))
  return next
}

export function getTradeJournal(): TradeJournalEntry[] {
  return readJson<TradeJournalEntry[]>(TRADE_JOURNAL_KEY, [])
}

export function saveTradeJournal(entry: Omit<TradeJournalEntry, 'id' | 'createdAt'>): TradeJournalEntry[] {
  const next = [{ id: crypto.randomUUID(), createdAt: new Date().toISOString(), ...entry }, ...getTradeJournal()]
  localStorage.setItem(TRADE_JOURNAL_KEY, JSON.stringify(next))
  return next
}

export function deleteTradeJournal(id: string): TradeJournalEntry[] {
  const next = getTradeJournal().filter((item) => item.id !== id)
  localStorage.setItem(TRADE_JOURNAL_KEY, JSON.stringify(next))
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
