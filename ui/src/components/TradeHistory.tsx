import React from 'react'
import './TradeHistory.css'

interface Trade {
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

interface Props {
  trades: Trade[]
}

export const TradeHistory: React.FC<Props> = ({ trades }) => {
  return (
    <div className="trade-history">
      <h3>Recent Trades</h3>
      {trades.length === 0 ? (
        <p className="empty-state">No trades yet</p>
      ) : (
        <div className="trades-table">
          <table>
            <thead>
              <tr>
                <th>Symbol</th>
                <th>Entry</th>
                <th>Exit</th>
                <th>P&L</th>
                <th>Return %</th>
                <th>Exit Reason</th>
                <th>Tags</th>
              </tr>
            </thead>
            <tbody>
              {trades.map((trade) => (
                <tr key={trade.trade_id} className={trade.pnl >= 0 ? 'win' : 'loss'}>
                  <td className="symbol">{trade.symbol}</td>
                  <td>${trade.entry_price.toFixed(2)}</td>
                  <td>${trade.exit_price.toFixed(2)}</td>
                  <td className="pnl">
                    <span className={trade.pnl >= 0 ? 'gain' : 'loss'}>
                      ${Math.abs(trade.pnl).toFixed(2)}
                    </span>
                  </td>
                  <td>{trade.pnl_pct.toFixed(2)}%</td>
                  <td className="thesis">{trade.thesis_status}</td>
                  <td className="tags">
                    {trade.analysis_tags.map((tag) => (
                      <span key={tag} className="tag">
                        {tag}
                      </span>
                    ))}
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
