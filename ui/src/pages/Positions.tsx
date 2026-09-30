import { useMemo, useState } from 'react'
import { api, ApiError } from '../lib/api'
import type { Position } from '../lib/api'
import { money, quantity, signedMoney, signedPct, tone } from '../lib/format'
import { Badge, Card, ConfirmDialog, Empty } from '../components/ui'
import type { ToastKind } from '../hooks/useToasts'

type SortKey = 'symbol' | 'value' | 'pnl'

function stopError(position: Position, stop: number): string | null {
  if (!Number.isFinite(stop) || stop <= 0) return 'Enter a positive price'
  const long = position.side === 'BUY'
  if (long && stop >= position.current_price) return `Must be below ${money(position.current_price)}`
  if (!long && stop <= position.current_price) return `Must be above ${money(position.current_price)}`
  return null
}

function StopEditor({ position, notify, onDone }: {
  position: Position
  notify: (kind: ToastKind, message: string) => void
  onDone: () => void
}) {
  const [value, setValue] = useState(String(position.stop_price ?? ''))
  const [busy, setBusy] = useState(false)
  const error = value ? stopError(position, Number(value)) : 'Enter a price'

  const save = async () => {
    if (error) return
    setBusy(true)
    try {
      await api.updateStop(position.symbol, Number(value))
      notify('success', `${position.symbol} stop moved to ${money(Number(value))}`)
      onDone()
    } catch (e) {
      notify('error', e instanceof ApiError ? e.message : 'Could not reach the server')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="inline-edit">
      <input
        className="input small"
        inputMode="decimal"
        aria-label={`New stop for ${position.symbol}`}
        aria-invalid={Boolean(error)}
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={(e) => { if (e.key === 'Enter') save(); if (e.key === 'Escape') onDone() }}
        autoFocus
      />
      <button className="btn primary small" disabled={Boolean(error) || busy} onClick={save}>Save</button>
      <button className="btn ghost small" onClick={onDone}>Cancel</button>
      {error && <span className="field-error">{error}</span>}
    </div>
  )
}

export function Positions({ positions, notify }: {
  positions: Position[]
  notify: (kind: ToastKind, message: string) => void
}) {
  const [sort, setSort] = useState<SortKey>('value')
  const [editing, setEditing] = useState<string | null>(null)
  const [closing, setClosing] = useState<Position | null>(null)

  const rows = useMemo(() => {
    const withValue = positions.map((p) => ({ ...p, value: p.quantity * p.current_price }))
    return withValue.sort((a, b) =>
      sort === 'symbol' ? a.symbol.localeCompare(b.symbol) : sort === 'pnl' ? b.unrealized_pnl - a.unrealized_pnl : b.value - a.value,
    )
  }, [positions, sort])

  const confirmClose = async () => {
    const position = closing
    setClosing(null)
    if (!position) return
    try {
      const result = await api.closePosition(position.symbol)
      if (result.success) notify('success', `Closed ${position.symbol}: ${signedMoney(result.pnl ?? 0)}`)
      else notify('error', result.error ?? `Could not close ${position.symbol}`)
    } catch (e) {
      notify('error', e instanceof ApiError ? e.message : 'Could not reach the server')
    }
  }

  const header = (key: SortKey, label: string, numeric = false) => (
    <th className={numeric ? 'num' : ''} aria-sort={sort === key ? 'descending' : 'none'}>
      <button className="th-btn" onClick={() => setSort(key)}>{label}{sort === key ? ' ↓' : ''}</button>
    </th>
  )

  return (
    <div className="page">
      <Card title={`Open positions (${positions.length})`}>
        {rows.length === 0 ? (
          <Empty title="No open positions">When Augur opens a trade it appears here with its stop and target.</Empty>
        ) : (
          <div className="table-scroll">
            <table className="table">
              <thead>
                <tr>
                  {header('symbol', 'Symbol')}
                  <th>Side</th>
                  <th className="num">Qty</th>
                  <th className="num">Entry</th>
                  <th className="num">Price</th>
                  {header('value', 'Value', true)}
                  {header('pnl', 'Profit/loss', true)}
                  <th className="num">Stop</th>
                  <th className="num">Target</th>
                  <th><span className="sr-only">Actions</span></th>
                </tr>
              </thead>
              <tbody>
                {rows.map((p) => (
                  <tr key={p.symbol}>
                    <td className="strong">{p.symbol}</td>
                    <td>{p.side === 'BUY' ? 'Long' : 'Short'}</td>
                    <td className="num">{quantity(p.quantity)}</td>
                    <td className="num">{money(p.entry_price)}</td>
                    <td className="num">{money(p.current_price)}</td>
                    <td className="num">{money(p.value)}</td>
                    <td className={`num ${tone(p.unrealized_pnl)}`}>
                      {signedMoney(p.unrealized_pnl)}
                      <div className="small">{signedPct(p.unrealized_pnl_pct)}</div>
                    </td>
                    <td className="num">
                      {editing === p.symbol ? (
                        <StopEditor position={p} notify={notify} onDone={() => setEditing(null)} />
                      ) : p.stop_price ? (
                        <button className="link-btn" onClick={() => setEditing(p.symbol)} title="Move stop">
                          {money(p.stop_price)}
                        </button>
                      ) : (
                        <button className="link-btn" onClick={() => setEditing(p.symbol)}>
                          <Badge status="warning">No stop, add one</Badge>
                        </button>
                      )}
                    </td>
                    <td className="num">{p.target_price ? money(p.target_price) : '—'}</td>
                    <td className="actions">
                      <button className="btn ghost small" onClick={() => setClosing(p)}>Close</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <ConfirmDialog
        open={closing !== null}
        title={`Close ${closing?.symbol ?? ''}?`}
        body={closing && (
          <p>
            Sells the whole position at the current price, about {money(closing.quantity * closing.current_price)}.
            Profit/loss right now: <strong className={tone(closing.unrealized_pnl)}>{signedMoney(closing.unrealized_pnl)}</strong>.
          </p>
        )}
        confirmLabel="Close position"
        danger
        onConfirm={confirmClose}
        onCancel={() => setClosing(null)}
      />
    </div>
  )
}
