// Typed client for the Augur dashboard API (src/dashboard_api.py).

export const API_URL: string = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'
export const WS_URL: string = API_URL.replace(/^http/, 'ws') + '/ws/dashboard'

export type Side = 'BUY' | 'SELL'

export interface Position {
  symbol: string
  quantity: number
  entry_price: number
  current_price: number
  unrealized_pnl: number
  unrealized_pnl_pct: number
  side: Side
  thesis_valid: boolean
  stop_price: number | null
  target_price: number | null
}

export interface Trade {
  trade_id: string
  symbol: string
  entry_price: number
  exit_price: number
  quantity: number
  side: Side
  pnl: number
  pnl_pct: number
  entry_time: string
  exit_time: string
  thesis_status: string
  analysis_tags: string[]
}

export interface EquityPoint {
  t: string
  equity: number
}

export interface Portfolio {
  account_equity: number
  cash: number
  buying_power: number
  total_pnl: number
  total_pnl_pct: number
  max_drawdown: number
  positions: Position[]
  recent_trades: Trade[]
  timestamp: string
  realized_pnl: number
  unrealized_pnl: number
  mode: Mode
  price_source: 'alpaca' | 'simulated'
  last_price_at: string | null
  halted: boolean
  equity_curve: EquityPoint[]
}

export interface Alert {
  alert_type: string
  symbol?: string | null
  message: string
  severity: 'INFO' | 'WARNING' | 'CRITICAL' | string
  timestamp: string
}

export interface CommandResponse {
  understood: boolean
  action?: string | null
  params?: Record<string, unknown> | null
  reasoning: string
  risk_warning?: string | null
  requires_confirmation: boolean
}

export type Mode = 'demo' | 'paper' | 'live'

export interface Health {
  status: string
  mode: Mode
  price_source: 'alpaca' | 'simulated'
  last_price_at: string | null
  halted: boolean
  halt_reason: string | null
}

export interface Integration {
  id: string
  name: string
  emoji: string
  what_it_does: string
  category: 'broker' | 'data'
  required: boolean
  configured: boolean
  keys_present: number
  keys_needed: number
  env_vars: string[]
  safe_mode: boolean | null
  signup_url: string
  key_url: string
  steps: string[]
}

export interface IntegrationsResponse {
  integrations: Integration[]
  trading_mode: string
  env_file_exists: boolean
}

export interface ScanOrder {
  side: Side
  quantity: number
  notional: number
  entry: number
  stop_loss: number
  take_profit: number
}

export interface ScanRow {
  symbol: string
  name: string
  asset_class: 'crypto' | 'commodity' | 'equity'
  underlying: string
  note: string
  error?: string
  price?: number
  change_1d_pct?: number
  atr_pct?: number
  trend_score?: number
  trend_votes?: Record<string, number>
  decision?: 'BUY' | 'SELL' | 'NO_TRADE'
  reasons?: string[]
  order?: ScanOrder | null
  specialists?: { agent: string; signal: string; confidence: number }[]
  as_of?: string
}

export interface ScanResponse {
  scanned_at: string
  real_yield_change_bps: number | null
  instruments: ScanRow[]
}

export interface OrderTicket {
  symbol: string
  side: Side
  quantity: number
  stop_loss: number
  take_profit: number
  confirm_real_money?: string
}

export interface OrderResponse {
  order_id: string
  status: string
  quantity: number
  protection: string | null
  mode: Mode
  warning: string | null
}

export interface WalletRow {
  address: string
  eth?: number
  usd?: number | null
  error?: string
}

export interface WalletsResponse {
  wallets: WalletRow[]
  rpc_host: string | null
  eth_price: number | null
}

export const REAL_MONEY_PHRASE = 'REAL MONEY'

export class ApiError extends Error {
  readonly status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(API_URL + path, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...init?.headers },
  })
  const body = await response.json().catch(() => null)
  if (!response.ok) {
    const detail = body && typeof body.detail === 'string' ? body.detail : `Request failed (${response.status})`
    throw new ApiError(response.status, detail)
  }
  return body as T
}

const post = <T>(path: string, body?: unknown) =>
  request<T>(path, { method: 'POST', body: body === undefined ? undefined : JSON.stringify(body) })

export const api = {
  portfolio: () => request<Portfolio>('/api/portfolio'),
  health: () => request<Health>('/api/health'),
  command: (text: string) => post<CommandResponse>('/api/command', { text }),
  closePosition: (symbol: string) => post<{ success: boolean; pnl?: number; error?: string }>(
    '/api/action', { type: 'CLOSE_POSITION', symbol },
  ),
  updateStop: (symbol: string, stop_price: number) =>
    post<{ message: string }>('/api/action', { type: 'UPDATE_STOP', symbol, params: { stop_price } }),
  adjustSize: (symbol: string, quantity: number) =>
    post<{ message: string }>('/api/action', { type: 'ADJUST_SIZE', symbol, params: { quantity } }),
  killSwitch: (reason: string) => post<{ closed: number }>('/api/kill-switch', { reason }),
  resume: () => post<{ halted: boolean }>('/api/resume'),
  scan: (refresh = false) => request<ScanResponse>(`/api/markets/scan${refresh ? '?refresh=true' : ''}`),
  placeOrder: (ticket: OrderTicket) => post<OrderResponse>('/api/orders', ticket),
  wallets: () => request<WalletsResponse>('/api/wallets'),
  addWallet: (address: string) => post<{ watching: string[] }>('/api/wallets', { address }),
  removeWallet: (address: string) =>
    request<{ watching: string[] }>(`/api/wallets/${encodeURIComponent(address)}`, { method: 'DELETE' }),
  integrations: () => request<IntegrationsResponse>('/api/integrations'),
  saveKeys: (id: string, values: Record<string, string>) =>
    post<{ saved: string[]; integration: Integration }>(`/api/integrations/${id}/keys`, { values }),
  testIntegration: (id: string) => post<{ ok: boolean; message: string }>(`/api/integrations/${id}/test`),
}
