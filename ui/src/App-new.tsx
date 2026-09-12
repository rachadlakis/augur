import React, { useState, useEffect, useRef } from 'react'
import './App-new.css'
import { PortfolioDashboard } from './components/PortfolioDashboard'
import { TradeHistory } from './components/TradeHistory'
import { ChatInterface } from './components/ChatInterface'
import { AlertCenter } from './components/AlertCenter'

// Type definitions
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

interface Alert {
  alert_type: string
  symbol?: string
  message: string
  severity: string
  timestamp: string
}

interface PortfolioState {
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
  const [connectionStatus, setConnectionStatus] = useState<'connected' | 'disconnected' | 'connecting'>('disconnecting')
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null)

  // WebSocket connection management
  useEffect(() => {
    const connectWebSocket = () => {
      setConnectionStatus('connecting')

      try {
        const ws = new WebSocket('ws://localhost:8000/ws/dashboard')

        ws.onopen = () => {
          console.log('✅ WebSocket connected')
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
          } catch (error) {
            console.error('Error parsing WebSocket message:', error)
          }
        }

        ws.onerror = (error) => {
          console.error('❌ WebSocket error:', error)
          setConnectionStatus('disconnected')
        }

        ws.onclose = () => {
          console.log('⚠️ WebSocket disconnected')
          setConnectionStatus('disconnected')

          // Auto-reconnect after 3 seconds
          reconnectTimeoutRef.current = setTimeout(() => {
            connectWebSocket()
          }, 3000)
        }

        wsRef.current = ws
      } catch (error) {
        console.error('Failed to connect WebSocket:', error)
        setConnectionStatus('disconnected')
      }
    }

    connectWebSocket()

    return () => {
      if (wsRef.current) {
        wsRef.current.close()
      }
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current)
      }
    }
  }, [])

  // REST API fallback polling (if WebSocket not connected)
  useEffect(() => {
    if (connectionStatus === 'connected') return

    const interval = setInterval(async () => {
      try {
        const response = await fetch('http://localhost:8000/api/portfolio')
        if (response.ok) {
          const data = await response.json()
          setPortfolio(data)
        }
      } catch (error) {
        console.warn('API polling error:', error)
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
        console.log('Command response:', result)

        // Show confirmation or execute
        if (result.understood) {
          if (result.requires_confirmation) {
            // In a real app, show a confirmation dialog
            const confirmed = window.confirm(`Execute: ${result.reasoning}?`)
            if (confirmed && result.action) {
              await handleAction(result.action, result.params)
            }
          } else {
            // Execute immediately
            if (result.action) {
              await handleAction(result.action, result.params)
            }
          }
        }
      }
    } catch (error) {
      console.error('Error sending command:', error)
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
        const result = await response.json()
        console.log('Action result:', result)

        // Add success alert
        setAlerts((prev) => [
          {
            alert_type: 'EXECUTION_FAILURE',
            message: result.message || `${action} executed`,
            severity: 'INFO',
            timestamp: new Date().toISOString(),
          },
          ...prev,
        ])
      }
    } catch (error) {
      console.error('Error executing action:', error)
      setAlerts((prev) => [
        {
          alert_type: 'EXECUTION_FAILURE',
          message: `Failed to execute ${action}`,
          severity: 'CRITICAL',
          timestamp: new Date().toISOString(),
        },
        ...prev,
      ])
    }
  }

  const handlePositionClose = (symbol: string) => {
    handleAction('CLOSE_POSITION', { symbol, params: {} })
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
