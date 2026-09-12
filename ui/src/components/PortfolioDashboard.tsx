import React from 'react'
import './PortfolioDashboard.css'

interface Position {
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

interface PortfolioState {
  account_equity: number
  cash: number
  buying_power: number
  total_pnl: number
  total_pnl_pct: number
  max_drawdown: number
  positions: Position[]
  recent_trades: any[]
  timestamp: string
}

interface Props {
  portfolio: PortfolioState
  onAction: (symbol: string) => void
}

export const PortfolioDashboard: React.FC<Props> = ({ portfolio, onAction }) => {
  const gainColor = portfolio.total_pnl >= 0 ? '#10b981' : '#ef4444'

  return (
    <div className="portfolio-dashboard">
      <h2>Portfolio Overview</h2>
      
      <div className="metrics-grid">
        <div className="metric-card">
          <span className="label">Account Equity</span>
          <span className="value">${portfolio.account_equity.toFixed(2)}</span>
        </div>
        
        <div className="metric-card">
          <span className="label">Total P&L</span>
          <span className="value" style={{ color: gainColor }}>
            ${portfolio.total_pnl.toFixed(2)} ({portfolio.total_pnl_pct.toFixed(2)}%)
          </span>
        </div>
        
        <div className="metric-card">
          <span className="label">Cash Available</span>
          <span className="value">${portfolio.cash.toFixed(2)}</span>
        </div>
        
        <div className="metric-card">
          <span className="label">Buying Power</span>
          <span className="value">${portfolio.buying_power.toFixed(2)}</span>
        </div>
        
        <div className="metric-card">
          <span className="label">Max Drawdown</span>
          <span className="value" style={{ color: '#ef4444' }}>
            ${Math.abs(portfolio.max_drawdown).toFixed(2)}
          </span>
        </div>
        
        <div className="metric-card">
          <span className="label">Active Positions</span>
          <span className="value">{portfolio.positions.length}</span>
        </div>
      </div>

      <h3>Open Positions</h3>
      {portfolio.positions.length === 0 ? (
        <p className="empty-state">No open positions</p>
      ) : (
        <div className="positions-table">
          <table>
            <thead>
              <tr>
                <th>Symbol</th>
                <th>Side</th>
                <th>Qty</th>
                <th>Entry Price</th>
                <th>Current Price</th>
                <th>Unrealized P&L</th>
                <th>Thesis</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {portfolio.positions.map((pos) => (
                <tr key={pos.symbol} className={pos.unrealized_pnl >= 0 ? 'gain' : 'loss'}>
                  <td className="symbol">{pos.symbol}</td>
                  <td className="side">{pos.side}</td>
                  <td>{pos.quantity.toFixed(2)}</td>
                  <td>${pos.entry_price.toFixed(2)}</td>
                  <td>${pos.current_price.toFixed(2)}</td>
                  <td className="pnl">
                    ${pos.unrealized_pnl.toFixed(2)} ({pos.unrealized_pnl_pct.toFixed(2)}%)
                  </td>
                  <td>
                    <span className={`thesis ${pos.thesis_valid ? 'valid' : 'invalid'}`}>
                      {pos.thesis_valid ? '✓ Valid' : '✗ Invalid'}
                    </span>
                  </td>
                  <td className="actions">
                    <button
                      className="btn btn-small btn-danger"
                      onClick={() => onAction(pos.symbol)}
                      title="Close this position"
                    >
                      Close
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
