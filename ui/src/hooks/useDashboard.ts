import { useCallback, useEffect, useRef, useState } from 'react'
import { api, WS_URL } from '../lib/api'
import type { Alert, Health, Portfolio } from '../lib/api'

export type Connection = 'connecting' | 'live' | 'polling' | 'offline'

/**
 * Live dashboard state: WebSocket first, REST polling while the socket is down,
 * and a health poll for mode / kill-switch status. Nothing is ever faked: until
 * the backend answers, `portfolio` stays null and the UI says so.
 */
export function useDashboard() {
  const [portfolio, setPortfolio] = useState<Portfolio | null>(null)
  const [health, setHealth] = useState<Health | null>(null)
  const [alerts, setAlerts] = useState<Alert[]>([])
  const [connection, setConnection] = useState<Connection>('connecting')
  const socketRef = useRef<WebSocket | null>(null)

  const refresh = useCallback(async () => {
    try {
      const [p, h] = await Promise.all([api.portfolio(), api.health()])
      setPortfolio(p)
      setHealth(h)
      setConnection((c) => (c === 'live' ? c : 'polling'))
    } catch {
      setConnection((c) => (c === 'live' ? c : 'offline'))
    }
  }, [])

  const pushAlert = useCallback((alert: Alert) => {
    setAlerts((prev) => [alert, ...prev].slice(0, 100))
  }, [])

  useEffect(() => {
    let retry: ReturnType<typeof setTimeout> | undefined
    let stopped = false

    const connect = () => {
      const ws = new WebSocket(WS_URL)
      socketRef.current = ws
      ws.onopen = () => {
        setConnection('live')
        // The server pushes on its own schedule; ask once so the first frame is immediate.
        ws.send(JSON.stringify({ type: 'hello' }))
      }
      ws.onmessage = (event) => {
        try {
          const message = JSON.parse(event.data)
          if (message.type === 'portfolio_update' && message.data) setPortfolio(message.data)
          if (message.type === 'alert' && message.data) pushAlert(message.data)
        } catch {
          // ignore malformed frames
        }
      }
      ws.onclose = () => {
        if (stopped) return
        setConnection((c) => (c === 'live' ? 'polling' : c))
        retry = setTimeout(connect, 3000)
      }
      ws.onerror = () => ws.close()
    }

    connect()
    return () => {
      stopped = true
      clearTimeout(retry)
      socketRef.current?.close()
    }
  }, [pushAlert])

  // REST fallback while the socket is down, plus a steady health poll either way.
  useEffect(() => {
    refresh()
    const interval = setInterval(() => {
      if (connection !== 'live') refresh()
      else api.health().then(setHealth).catch(() => undefined)
    }, connection === 'live' ? 5000 : 3000)
    return () => clearInterval(interval)
  }, [connection, refresh])

  return { portfolio, health, alerts, connection, refresh, pushAlert }
}
