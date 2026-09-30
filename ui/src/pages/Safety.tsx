import { useState } from 'react'
import { api, ApiError } from '../lib/api'
import type { Health, Portfolio } from '../lib/api'
import { Badge, Card, ConfirmDialog, Icon } from '../components/ui'
import type { ToastKind } from '../hooks/useToasts'

const RULES = [
  ['Risk per trade', 'At most 0.5% of the account can be lost on any one trade.'],
  ['Daily loss limit', 'After losing 2% in a day, no new trades until tomorrow.'],
  ['Position size', 'No single asset can be more than 10% of the account.'],
  ['Every trade has a stop', 'Stops and targets are sent together with the order.'],
  ['No chasing', 'Won’t buy right after a big jump or sell right after a big drop.'],
  ['Slow and steady', 'At most 2 new trades an hour and 6 a day.'],
] as const

export function Safety({ health, portfolio, notify, onChanged }: {
  health: Health | null
  portfolio: Portfolio
  notify: (kind: ToastKind, message: string) => void
  onChanged: () => void
}) {
  const [confirming, setConfirming] = useState(false)
  const [reason, setReason] = useState('')
  const halted = health?.halted ?? portfolio.halted

  const trip = async () => {
    setConfirming(false)
    try {
      const result = await api.killSwitch(reason.trim() || 'stopped from the dashboard')
      notify('success', `Everything stopped. ${result.closed} position(s) closed.`)
      setReason('')
      onChanged()
    } catch (e) {
      notify('error', e instanceof ApiError ? e.message : 'Could not reach the server')
    }
  }

  const resume = async () => {
    try {
      await api.resume()
      notify('success', 'New trades are allowed again')
      onChanged()
    } catch (e) {
      notify('error', e instanceof ApiError ? e.message : 'Could not reach the server')
    }
  }

  return (
    <div className="page">
      <Card className={`kill ${halted ? 'halted' : ''}`}>
        <div className="kill-grid">
          <div>
            <h2>Emergency stop</h2>
            {halted ? (
              <>
                <Badge status="critical">Halted: {health?.halt_reason ?? 'kill switch'}</Badge>
                <p>No new trades will open. Existing positions were closed when this was pressed.</p>
                <button className="btn primary" onClick={resume}>Allow new trades again</button>
              </>
            ) : (
              <>
                <p>One press closes every position and blocks new trades until you allow them again.</p>
                <input className="input" placeholder="Why? (optional)" value={reason} onChange={(e) => setReason(e.target.value)} />
              </>
            )}
          </div>
          {!halted && (
            <button className="kill-button" onClick={() => setConfirming(true)}>
              <Icon name="power" size={40} />
              <span>STOP ALL</span>
            </button>
          )}
        </div>
      </Card>

      <Card title="Safety rules that are always on">
        <ul className="rules">
          {RULES.map(([title, text]) => (
            <li key={title}>
              <Icon name="check" size={18} />
              <div><div className="strong">{title}</div><div className="muted">{text}</div></div>
            </li>
          ))}
        </ul>
        <p className="muted small">
          These live in the code, not in a prompt, so no AI answer can switch them off.
          Mode: {portfolio.mode === 'demo' ? 'practice (simulated prices)' : 'broker account'}.
        </p>
      </Card>

      <ConfirmDialog
        open={confirming}
        title="Stop everything?"
        body={<p>This closes all {portfolio.positions.length} open position(s) right now and blocks new trades.</p>}
        confirmLabel="Yes, stop all"
        danger
        onConfirm={trip}
        onCancel={() => setConfirming(false)}
      />
    </div>
  )
}
