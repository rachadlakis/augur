import React, { useState, useEffect } from 'react'
import './HoldingsDetail.css'
import { formatCurrency, formatNumber, formatPercent } from '../utils/formatters'

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

interface HoldingsDetailProps {
  positions: Position[]
  onBack: () => void
}

// Simple chart using canvas
const SimpleChart: React.FC<{ prices: number[]; symbol: string }> = ({ prices, symbol }) => {
  const canvasRef = React.useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    if (!canvasRef.current || prices.length === 0) return

    const canvas = canvasRef.current
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    const width = canvas.width
    const height = canvas.height
    const padding = 40

    // Clear canvas
    ctx.fillStyle = '#0f172a'
    ctx.fillRect(0, 0, width, height)

    // Calculate min/max
    const minPrice = Math.min(...prices)
    const maxPrice = Math.max(...prices)
    const range = maxPrice - minPrice || 1
    const scale = (height - 2 * padding) / range

    // Draw grid
    ctx.strokeStyle = '#1e293b'
    ctx.lineWidth = 1
    for (let i = 0; i <= 5; i++) {
      const y = padding + (i * (height - 2 * padding)) / 5
      ctx.beginPath()
      ctx.moveTo(padding, y)
      ctx.lineTo(width - padding, y)
      ctx.stroke()
    }

    // Draw line chart
    ctx.strokeStyle = '#10b981'
    ctx.lineWidth = 2
    ctx.beginPath()

    prices.forEach((price, index) => {
      const x = padding + (index / (prices.length - 1 || 1)) * (width - 2 * padding)
      const y = height - padding - (price - minPrice) * scale
      if (index === 0) ctx.moveTo(x, y)
      else ctx.lineTo(x, y)
    })
    ctx.stroke()

    // Draw axes
    ctx.strokeStyle = '#64748b'
    ctx.lineWidth = 2
    ctx.beginPath()
    ctx.moveTo(padding, height - padding)
    ctx.lineTo(width - padding, height - padding)
    ctx.stroke()
    ctx.beginPath()
    ctx.moveTo(padding, padding)
    ctx.lineTo(padding, height - padding)
    ctx.stroke()

    // Draw labels
    ctx.fillStyle = '#cbd5e1'
    ctx.font = '12px Arial'
    ctx.textAlign = 'right'
    ctx.fillText(`$${maxPrice.toFixed(2)}`, padding - 10, padding + 5)
    ctx.fillText(`$${minPrice.toFixed(2)}`, padding - 10, height - padding + 5)
  }, [prices])

  return <canvas ref={canvasRef} width={400} height={250} style={{ display: 'block', margin: '0 auto' }} />
}

export const HoldingsDetail: React.FC<HoldingsDetailProps> = ({ positions, onBack }) => {
  // Generate mock price history (in real app, would come from backend)
  const getPriceHistory = (currentPrice: number, entryPrice: number): number[] => {
    const history = [entryPrice]
    let price = entryPrice
    for (let i = 1; i < 20; i++) {
      const change = (Math.random() - 0.5) * (currentPrice - entryPrice) * 0.1
      price = Math.max(price + change, Math.min(entryPrice, currentPrice) * 0.8)
      history.push(price)
    }
    history.push(currentPrice)
    return history
  }

  return (
    <div className="holdings-detail">
      <button className="back-button" onClick={onBack}>
        ← Back to Dashboard
      </button>

      <h1>Holdings & Price History</h1>

      {positions.length === 0 ? (
        <p className="no-holdings">No active holdings</p>
      ) : (
        <div className="holdings-grid">
          {positions.map((position) => {
            const priceHistory = getPriceHistory(position.current_price, position.entry_price)
            const gainColor = position.unrealized_pnl >= 0 ? '#10b981' : '#ef4444'

            return (
              <div key={position.symbol} className="holding-card">
                <div className="holding-header">
                  <h2>{position.symbol}</h2>
                  <span className="quantity">Qty: {position.quantity}</span>
                </div>

                <div className="holding-stats">
                  <div className="stat">
                    <span className="label">Entry Price</span>
                    <span className="value">${position.entry_price.toFixed(2)}</span>
                  </div>
                  <div className="stat">
                    <span className="label">Current Price</span>
                    <span className="value">${position.current_price.toFixed(2)}</span>
                  </div>
                  <div className="stat">
                    <span className="label">Position Value</span>
                    <span className="value">${(position.quantity * position.current_price).toFixed(2)}</span>
                  </div>
                  <div className="stat">
                    <span className="label">P&L</span>
                    <span className="value" style={{ color: gainColor }}>
                      ${position.unrealized_pnl.toFixed(2)} ({position.unrealized_pnl_pct.toFixed(2)}%)
                    </span>
                  </div>
                </div>

                {position.stop_price && (
                  <div className="stop-target">
                    <div>Stop Loss: ${position.stop_price.toFixed(2)}</div>
                  </div>
                )}
                {position.target_price && (
                  <div className="stop-target">
                    <div>Target: ${position.target_price.toFixed(2)}</div>
                  </div>
                )}

                <div className="chart-container">
                  <h3>Price History</h3>
                  <SimpleChart prices={priceHistory} symbol={position.symbol} />
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

export default HoldingsDetail
