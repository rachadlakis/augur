// Shared type definitions for dashboard
export interface Position {
  symbol: string
  quantity: number
  entry_price: number
  current_price: number
  unrealized_pnl: number
  unrealized_pnl_pct: number
  side: string
  thesis_valid: boolean
  stop_price?: number
  target_price?: number
}

export interface Trade {
  trade_id: string
  symbol: string
  entry_price: number
  exit_price: number
  quantity: number
  side: string
  pnl: number
  pnl_pct: number
  entry_time: string
  exit_time: string
  thesis_status: string
  analysis_tags: string[]
}

export interface Alert {
  alert_type: string
  symbol?: string
  message: string
  severity: string
  timestamp: string
}

export interface PortfolioState {
  account_equity: number
  cash: number
  buying_power: number
  total_pnl: number
  total_pnl_pct: number
  max_drawdown: number
  positions: Position[]
  recent_trades: Trade[]
  timestamp: string
}
