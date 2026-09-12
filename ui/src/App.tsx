import React, { useState, useEffect, useRef } from 'react'
import './App-new.css'
import { PortfolioDashboard } from './components/PortfolioDashboard'
import { TradeHistory } from './components/TradeHistory'
import { ChatInterface } from './components/ChatInterface'
import { AlertCenter } from './components/AlertCenter'
// Inline types - avoiding import from types.ts which seems to cause issues
interface PortfolioState {
  account_equity: number
  cash: number
  buying_power: number
  total_pnl: number
  total_pnl_pct: number
  max_drawdown: number
  positions: any[]
  recent_trades: any[]
  timestamp: string
}

interface Alert {
  alert_type: string
  symbol?: string
  message: string
  severity: string
  timestamp: string
}

function App() {
  const [portfolio, setPortfolio] = useState<PortfolioState>({
    account_equity: 100000,
    cash: 30000,
    buying_power: 50000,
    total_pnl: 0,
    total_pnl_pct: 0,
    max_drawdown: 0,
    positions: [],
    recent_trades: [],
    timestamp: new Date().toISOString(),
  })

  const [alerts, setAlerts] = useState<Alert[]>([])
  const [connectionStatus, setConnectionStatus] = useState<'connected' | 'disconnected' | 'connecting'>('connecting')
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  // WebSocket connection management
  useEffect(() => {
    const connectWebSocket = () => {
      setConnectionStatus('connecting')
      try {
        const ws = new WebSocket('ws://localhost:8000/ws/dashboard')
        ws.onopen = () => {
          setConnectionStatus('connected')
        }
        ws.onmessage = (event) => {
          try {
            const message = JSON.parse(event.data)
            if (message.type === 'portfolio_update' && message.data) {
              setPortfolio(message.data)
            }
            if (message.type === 'alert' && message.data) {
              setAlerts((prev) => [message.data, ...prev].slice(0, 50))
            }
          } catch (e) {
            // silent
          }
        }
        ws.onerror = () => {
          setConnectionStatus('disconnected')
        }
        ws.onclose = () => {
          setConnectionStatus('disconnected')
          reconnectTimeoutRef.current = setTimeout(() => {
            connectWebSocket()
          }, 3000)
        }
        wsRef.current = ws
      } catch (e) {
        setConnectionStatus('disconnected')
      }
    }
    connectWebSocket()
    return () => {
      if (wsRef.current) wsRef.current.close()
      if (reconnectTimeoutRef.current) clearTimeout(reconnectTimeoutRef.current)
    }
  }, [])

  // REST API fallback
  useEffect(() => {
    if (connectionStatus === 'connected') return
    const interval = setInterval(async () => {
      try {
        const response = await fetch('http://localhost:8000/api/portfolio')
        if (response.ok) {
          const data = await response.json()
          setPortfolio(data)
        }
      } catch (e) {
        // silent
      }
    }, 5000)
    return () => clearInterval(interval)
  }, [connectionStatus])

  const handleSendCommand = async (text: string) => {
    if (!text.trim()) return
    try {
      const response = await fetch('http://localhost:8000/api/command', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text }),
      })
      if (response.ok) {
        const result = await response.json()
        if (result.understood && result.action) {
          handleAction(result.action, result.params || {})
        }
      }
    } catch (e) {
      // silent
    }
  }

  const handleAction = async (action: string, params: any) => {
    try {
      const response = await fetch('http://localhost:8000/api/action', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ type: action, ...params }),
      })
      if (response.ok) {
        setAlerts((prev) => [
          {
            alert_type: 'SUCCESS',
            message: `${action} executed`,
            severity: 'INFO',
            timestamp: new Date().toISOString(),
          },
          ...prev,
        ])
      }
    } catch (e) {
      setAlerts((prev) => [
        {
          alert_type: 'ERROR',
          message: `Failed to execute ${action}`,
          severity: 'ERROR',
          timestamp: new Date().toISOString(),
        },
        ...prev,
      ])
    }
  }

  const handlePositionClose = (symbol: string) => {
    handleAction('CLOSE_POSITION', { symbol })
  }

  return (
    <div className="app">
      <header className="app-header">
        <h1>📊 Augur Trading Dashboard</h1>
        <div className="connection-status">
          <span className={`status-indicator ${connectionStatus}`}></span>
          {connectionStatus === 'connected' && 'Connected'}
          {connectionStatus === 'connecting' && 'Connecting...'}
          {connectionStatus === 'disconnected' && 'Disconnected'}
        </div>
      </header>
      <div className="app-layout">
        <div className="left-panel">
          <PortfolioDashboard portfolio={portfolio} onAction={handlePositionClose} />
          <TradeHistory trades={portfolio.recent_trades} />
        </div>
        <div className="right-panel">
          <ChatInterface onSendCommand={handleSendCommand} />
          <AlertCenter alerts={alerts} />
        </div>
      </div>
    </div>
  )
}

export default App
