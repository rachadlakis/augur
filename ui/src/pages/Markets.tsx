import { useCallback, useEffect, useState } from 'react'
import { api, ApiError, REAL_MONEY_PHRASE } from '../lib/api'
import type { Mode, ScanOrder, ScanResponse, ScanRow } from '../lib/api'
import { ago, money, quantity, signedPct, tone } from '../lib/format'
import { Badge, Card, Empty, Icon } from '../components/ui'
import type { ToastKind } from '../hooks/useToasts'

const GROUPS: { id: ScanRow['asset_class']; title: string; blurb: string }[] = [
  { id: 'crypto', title: 'Blockchain', blurb: 'Crypto trades around the clock and moves fast.' },
  { id: 'commodity', title: 'Gold, silver & oil', blurb: 'Held through funds: gold and silver funds own metal, oil funds own futures.' },
  { id: 'equity', title: 'Benchmark', blurb: 'The S&P 500: the thing every strategy has to beat.' },
]

const TIMEFRAMES = ['1h', '4h', '1d'] as const

function TrendVotes({ votes }: { votes: Record<string, number> }) {
  return (
    <span className="votes" aria-label="Trend by timeframe">
      {TIMEFRAMES.map((tf) => {
        const v = votes[tf] ?? 0
        const label = v > 0 ? 'up' : v < 0 ? 'down' : 'flat'
        return (
          <span key={tf} className={`vote ${label}`} title={`${tf}: ${label}`}>
            <span className="vote-tf">{tf}</span>
            <span aria-hidden="true">{v > 0 ? '▲' : v < 0 ? '▼' : '–'}</span>
            <span className="sr-only">{label}</span>
          </span>
        )
      })}
    </span>
  )
}

function Decision({ decision }: { decision: ScanRow['decision'] }) {
  if (decision === 'BUY') return <Badge status="good">Buy setup</Badge>
  if (decision === 'SELL') return <Badge status="warning">Sell setup</Badge>
  return <Badge status="neutral">No trade</Badge>
}

function OrderDialog({ row, order, mode, onClose, notify }: {
  row: ScanRow
  order: ScanOrder
  mode: Mode
  onClose: () => void
  notify: (kind: ToastKind, message: string) => void
}) {
  const [phrase, setPhrase] = useState('')
  const [busy, setBusy] = useState(false)
  const live = mode === 'live'
  const ready = !live || phrase === REAL_MONEY_PHRASE

  const send = async () => {
    setBusy(true)
    try {
      const result = await api.placeOrder({
        symbol: row.symbol, side: order.side, quantity: order.quantity,
        stop_loss: order.stop_loss, take_profit: order.take_profit,
        confirm_real_money: live ? phrase : undefined,
      })
      const protection = result.protection === 'ATTACHED' ? 'stop and target attached'
        : result.protection === 'STOP_ATTACHED' ? 'stop attached, target watched by Augur' : String(result.protection)
      notify('success', `${row.symbol}: ${result.quantity} sent (${protection})`)
      if (result.warning) notify('info', result.warning)
      onClose()
    } catch (e) {
      notify('error', e instanceof ApiError ? e.message : 'Could not reach the server')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="dialog-overlay" role="dialog" aria-modal="true" aria-label={`Order ${row.symbol}`}>
      <div className={`dialog open ${live ? 'live' : ''}`}>
        <h3>{live ? '⚠️ Real-money order' : 'Send to practice account'}</h3>
        <div className="dialog-body">
          <p>
            {order.side === 'BUY' ? 'Buy' : 'Sell'} <strong>{row.name}</strong> ({row.symbol}) at the market price.
            The server re-checks the size with the risk rules before sending.
          </p>
          <dl className="ticket">
            <dt>Up to</dt><dd>{quantity(order.quantity)} (≈ {money(order.notional)})</dd>
            <dt>Stop</dt><dd>{money(order.stop_loss)}</dd>
            <dt>Target</dt><dd>{money(order.take_profit)}</dd>
            <dt>Account</dt><dd>{live ? 'REAL money' : 'Practice money (paper)'}</dd>
          </dl>
          {live && (
            <label className="field">
              <span className="field-label">Type {REAL_MONEY_PHRASE} to confirm</span>
              <input className="input" value={phrase} onChange={(e) => setPhrase(e.target.value)} autoFocus />
            </label>
          )}
        </div>
        <div className="dialog-actions">
          <button className="btn ghost" onClick={onClose}>Cancel</button>
          <button className={`btn ${live ? 'danger' : 'primary'}`} disabled={!ready || busy} onClick={send}>
            {busy ? 'Sending…' : live ? 'Place real order' : 'Send practice order'}
          </button>
        </div>
      </div>
    </div>
  )
}

function MarketCard({ row, mode, onOrder }: { row: ScanRow; mode: Mode; onOrder: (row: ScanRow) => void }) {
  if (row.error || row.price === undefined) {
    return (
      <article className="market">
        <header className="market-head">
          <div><div className="strong">{row.name}</div><div className="muted small">{row.symbol}</div></div>
          <Badge status="critical">No data</Badge>
        </header>
        <p className="muted small">{row.error ?? 'No price available'}</p>
      </article>
    )
  }
  const change = row.change_1d_pct ?? 0
  return (
    <article className="market">
      <header className="market-head">
        <div>
          <div className="strong">{row.name}</div>
          <div className="muted small">{row.symbol} · {row.note}</div>
        </div>
        <Decision decision={row.decision} />
      </header>

      <div className="market-price">
        <span className="market-value">{money(row.price)}</span>
        <span className={`market-change ${tone(change)}`}>
          <Icon name={change >= 0 ? 'up' : 'down'} size={14} /> {signedPct(change)} today
        </span>
      </div>

      <div className="market-meta">
        <TrendVotes votes={row.trend_votes ?? {}} />
        <span className="muted small" title="Average daily range (ATR) as % of price">
          Moves ~{(row.atr_pct ?? 0).toFixed(1)}%/day
        </span>
      </div>

      {row.order ? (
        <div className="suggestion">
          <div className="small strong">Suggested bracket (not sent)</div>
          <div className="suggestion-grid small">
            <span>{row.order.side === 'BUY' ? 'Buy' : 'Sell'} {quantity(row.order.quantity)}</span>
            <span>≈ {money(row.order.notional)}</span>
            <span>Stop {money(row.order.stop_loss)}</span>
            <span>Target {money(row.order.take_profit)}</span>
          </div>
          {mode !== 'demo' && (
            <button className={`btn small ${mode === 'live' ? 'danger' : 'primary'}`} onClick={() => onOrder(row)}>
              {mode === 'live' ? 'Place real order…' : 'Send to practice account…'}
            </button>
          )}
        </div>
      ) : (
        <ul className="why small">
          {(row.reasons ?? []).slice(0, 2).map((r) => <li key={r}>{r}</li>)}
        </ul>
      )}
    </article>
  )
}

const toError = (e: unknown) =>
  e instanceof ApiError ? { status: e.status, message: e.message } : { status: 0, message: 'Could not reach the Augur server' }

export function Markets({ onConnect, mode, notify }: {
  onConnect: () => void
  mode: Mode
  notify: (kind: ToastKind, message: string) => void
}) {
  const [data, setData] = useState<ScanResponse | null>(null)
  const [ordering, setOrdering] = useState<ScanRow | null>(null)
  const [error, setError] = useState<{ status: number; message: string } | null>(null)
  const [loading, setLoading] = useState(false)

  const load = useCallback(async (refresh = false) => {
    setLoading(true)
    try {
      setData(await api.scan(refresh))
      setError(null)
    } catch (e) {
      setError(toError(e))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    let active = true
    api.scan().then(
      (result) => { if (active) setData(result) },
      (e) => { if (active) setError(toError(e)) },
    )
    return () => { active = false }
  }, [])

  if (error && !data) {
    return (
      <div className="page">
        <Card>
          <Empty title={error.status === 409 ? 'Connect a data source first' : 'Markets unavailable'}>
            <p>{error.message}</p>
            {error.status === 409 && <button className="btn primary" onClick={onConnect}>Open Integrations</button>}
          </Empty>
        </Card>
      </div>
    )
  }
  if (!data) return <div className="page"><div className="skeleton tall" /></div>

  return (
    <div className="page">
      <div className="toolbar">
        <p className="muted">
          Scanned {ago(data.scanned_at)} with the same rules the robot trades by. Nothing here places an order.
          {data.real_yield_change_bps !== null
            ? ` Gold is reading the real yield: ${data.real_yield_change_bps > 0 ? '+' : ''}${data.real_yield_change_bps.toFixed(0)} bps over a month.`
            : ' Add a FRED key on Integrations so gold can read real yields.'}
        </p>
        <button className="btn ghost" onClick={() => load(true)} disabled={loading}>
          <Icon name="refresh" size={16} /> {loading ? 'Scanning…' : 'Scan again'}
        </button>
      </div>

      {GROUPS.map((group) => {
        const rows = data.instruments.filter((r) => r.asset_class === group.id)
        if (!rows.length) return null
        return (
          <section key={group.id} className="market-group">
            <header>
              <h2>{group.title}</h2>
              <p className="muted small">{group.blurb}</p>
            </header>
            <div className="markets">
              {rows.map((row) => <MarketCard key={row.symbol} row={row} mode={mode} onOrder={setOrdering} />)}
            </div>
          </section>
        )
      })}

      {ordering?.order && (
        <OrderDialog row={ordering} order={ordering.order} mode={mode} notify={notify} onClose={() => setOrdering(null)} />
      )}
    </div>
  )
}
