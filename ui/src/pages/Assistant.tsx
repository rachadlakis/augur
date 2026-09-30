import { useEffect, useRef, useState } from 'react'
import { api, ApiError } from '../lib/api'
import type { Alert, CommandResponse, Portfolio } from '../lib/api'
import { money, signedMoney } from '../lib/format'
import { Card, Icon } from '../components/ui'
import type { ToastKind } from '../hooks/useToasts'

interface Message {
  id: number
  from: 'you' | 'augur'
  text: string
  pending?: CommandResponse
}

const SUGGESTIONS = ['show portfolio summary', 'show alerts', 'close AAPL', 'adjust TSLA size to 20']

let nextId = 1

export function Assistant({ portfolio, alerts, notify }: {
  portfolio: Portfolio
  alerts: Alert[]
  notify: (kind: ToastKind, message: string) => void
}) {
  const [messages, setMessages] = useState<Message[]>([{
    id: nextId++,
    from: 'augur',
    text: 'Hi! Ask me about your portfolio, or tell me to close or resize a position. I always ask before doing anything risky.',
  }])
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const endRef = useRef<HTMLDivElement>(null)

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' }) }, [messages])

  const say = (message: Omit<Message, 'id'>) => setMessages((all) => [...all, { ...message, id: nextId++ }])

  const summary = () =>
    `Equity ${money(portfolio.account_equity)}, cash ${money(portfolio.cash)}. ` +
    `${portfolio.positions.length} open position(s), open P&L ${signedMoney(portfolio.unrealized_pnl)}, ` +
    `closed P&L ${signedMoney(portfolio.realized_pnl)}.`

  const send = async (input: string) => {
    const value = input.trim()
    if (!value || busy) return
    setText('')
    say({ from: 'you', text: value })
    setBusy(true)
    try {
      const response = await api.command(value)
      if (!response.understood) say({ from: 'augur', text: response.reasoning })
      else if (response.action === 'SHOW_SUMMARY') say({ from: 'augur', text: summary() })
      else if (response.action === 'SHOW_ALERTS') {
        say({
          from: 'augur',
          text: alerts.length ? alerts.slice(0, 5).map((a) => `• ${a.message}`).join('\n') : 'No alerts right now.',
        })
      } else if (response.action && response.requires_confirmation) {
        say({ from: 'augur', text: `${response.reasoning}. Confirm?`, pending: response })
      } else say({ from: 'augur', text: response.reasoning })
    } catch (e) {
      say({ from: 'augur', text: e instanceof ApiError ? e.message : 'I cannot reach the Augur server. Is it running?' })
    } finally {
      setBusy(false)
    }
  }

  const execute = async (message: Message) => {
    const pending = message.pending
    if (!pending) return
    setMessages((all) => all.map((m) => (m.id === message.id ? { ...m, pending: undefined } : m)))
    const symbol = String(pending.params?.symbol ?? '')
    try {
      if (pending.action === 'CLOSE_POSITION') {
        const result = await api.closePosition(symbol)
        say({ from: 'augur', text: result.success ? `Done: closed ${symbol} for ${signedMoney(result.pnl ?? 0)}.` : result.error ?? 'Close failed.' })
      } else if (pending.action === 'ADJUST_SIZE') {
        const qty = Number(pending.params?.quantity)
        const result = await api.adjustSize(symbol, qty)
        say({ from: 'augur', text: result.message })
      }
    } catch (e) {
      const text = e instanceof ApiError ? e.message : 'Could not reach the server'
      say({ from: 'augur', text: `Not done: ${text}` })
      notify('error', text)
    }
  }

  return (
    <div className="page">
      <Card title="Assistant" className="chat">
        <div className="chat-log" aria-live="polite">
          {messages.map((m) => (
            <div key={m.id} className={`bubble ${m.from}`}>
              <div className="bubble-text">{m.text}</div>
              {m.pending && (
                <div className="bubble-actions">
                  <button className="btn primary small" onClick={() => execute(m)}>Confirm</button>
                  <button
                    className="btn ghost small"
                    onClick={() => setMessages((all) => all.map((x) => (x.id === m.id ? { ...x, pending: undefined } : x)))}
                  >
                    Cancel
                  </button>
                </div>
              )}
            </div>
          ))}
          {busy && <div className="bubble augur typing" aria-label="Augur is thinking"><span /><span /><span /></div>}
          <div ref={endRef} />
        </div>
        <div className="chips">
          {SUGGESTIONS.map((s) => (
            <button key={s} className="chip" onClick={() => send(s)}>{s}</button>
          ))}
        </div>
        <form className="chat-input" onSubmit={(e) => { e.preventDefault(); send(text) }}>
          <input
            className="input"
            placeholder="Type a command, e.g. “close AAPL”"
            value={text}
            onChange={(e) => setText(e.target.value)}
            aria-label="Command"
          />
          <button className="btn primary" disabled={!text.trim() || busy} aria-label="Send">
            <Icon name="send" size={16} />
          </button>
        </form>
      </Card>
    </div>
  )
}
