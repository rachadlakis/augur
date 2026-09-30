const usd = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 2 })
const usdCompact = new Intl.NumberFormat('en-US', {
  style: 'currency', currency: 'USD', notation: 'compact', maximumFractionDigits: 1,
})
const num = new Intl.NumberFormat('en-US', { maximumFractionDigits: 4 })

export const money = (value: number) => usd.format(value)
export const moneyCompact = (value: number) => (Math.abs(value) >= 10_000 ? usdCompact.format(value) : usd.format(value))
export const quantity = (value: number) => num.format(value)

/** Signed money with an explicit sign, e.g. +$12.50 / −$3.10. */
export const signedMoney = (value: number) => (value > 0 ? '+' : value < 0 ? '−' : '') + usd.format(Math.abs(value))

export const signedPct = (value: number, digits = 2) =>
  (value > 0 ? '+' : value < 0 ? '−' : '') + Math.abs(value).toFixed(digits) + '%'

export const pct = (value: number, digits = 2) => value.toFixed(digits) + '%'

export const clockTime = (iso: string) =>
  new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })

export const dateTime = (iso: string) =>
  new Date(iso).toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })

/** "3 min ago" style relative time. */
export function ago(iso: string, now = Date.now()): string {
  const seconds = Math.max(0, Math.round((now - new Date(iso).getTime()) / 1000))
  if (seconds < 60) return `${seconds}s ago`
  if (seconds < 3600) return `${Math.round(seconds / 60)} min ago`
  if (seconds < 86400) return `${Math.round(seconds / 3600)} h ago`
  return `${Math.round(seconds / 86400)} d ago`
}

/** Direction class for P&L text: up / down / flat. */
export const tone = (value: number) => (value > 0 ? 'up' : value < 0 ? 'down' : 'flat')
