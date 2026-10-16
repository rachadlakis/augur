import { useCallback, useEffect, useState } from 'react'
import { api, ApiError } from '../lib/api'
import type { AnalystReading, IntelResponse, NewsContext, WhaleFlows, WhaleTransfer } from '../lib/api'
import { ago, moneyCompact, quantity } from '../lib/format'
import { Badge, Card, Empty, Icon } from '../components/ui'
import type { ToastKind } from '../hooks/useToasts'

const THEME_LABELS: Record<string, string> = {
  rates: 'Interest rates & the Fed',
  inflation: 'Inflation',
  trade: 'Tariffs, trade & sanctions',
  conflict: 'War & conflict',
  recession: 'Recession & jobs',
}

/** GDELT tone shifts this large (points vs. last week) fill the bar. */
const TONE_RANGE = 3

function Signal({ reading }: { reading?: AnalystReading }) {
  if (!reading) return <Badge status="neutral">No data</Badge>
  const pct = Math.round(reading.confidence * 100)
  if (reading.signal === 'BUY') return <Badge status="good">Leans up · {pct}%</Badge>
  if (reading.signal === 'SELL') return <Badge status="warning">Leans down · {pct}%</Badge>
  if (reading.signal === 'NO_TRADE') return <Badge status="neutral">Not enough data</Badge>
  return <Badge status="neutral">No lean</Badge>
}

function ToneBar({ shift }: { shift: number }) {
  const width = Math.min(1, Math.abs(shift) / TONE_RANGE) * 50
  const side = shift < 0 ? 'neg' : 'pos'
  return (
    <span className="diverge" aria-hidden="true">
      <span className="diverge-mid" />
      <span className={`diverge-fill ${side}`} style={{ width: `${width}%`, [side === 'neg' ? 'right' : 'left']: '50%' }} />
    </span>
  )
}

function NewsCard({ news, readings }: { news: NewsContext | null; readings: IntelResponse['readings'] }) {
  if (!news) return <Card title="Politics & economy"><Empty title="Not loaded yet" /></Card>
  const themes = Object.entries(news.themes)
  const pctile = news.epu?.percentile_1y
  const fomc = news.fomc_hours_ago
  const blackout = fomc !== undefined && fomc !== null && fomc >= 0 && fomc < 2
  const errors = Object.entries(news.errors)
  return (
    <Card title="Politics & economy" action={<Signal reading={readings.policy_for_risk_assets} />}>
      <div className="intel-grid">
        <div className="intel-stat">
          <div className="tile-label">Policy uncertainty</div>
          {pctile !== undefined ? (
            <>
              <div className="tile-value">{Math.round(pctile * 100)}<span className="unit">th pct</span></div>
              <div className="meter" role="meter" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(pctile * 100)}
                aria-label="Policy uncertainty percentile">
                <span className={`meter-fill ${pctile >= 0.9 ? 'hot' : ''}`} style={{ width: `${pctile * 100}%` }} />
              </div>
              <div className="tile-hint">
                {pctile >= 0.9 ? 'Unusually high: Augur halves every trade size.' : 'Versus the past year (FRED, Baker-Bloom-Davis index).'}
              </div>
            </>
          ) : <div className="muted small">Add a FRED key on the Integrations page to see this.</div>}
        </div>
        <div className="intel-stat">
          <div className="tile-label">Last Fed (FOMC) release</div>
          {fomc !== undefined && fomc !== null ? (
            <>
              <div className="tile-value">{fomc < 48 ? `${fomc.toFixed(1)} h` : `${Math.round(fomc / 24)} days`}<span className="unit"> ago</span></div>
              <div className="tile-hint">
                {blackout ? <Badge status="warning">Entries paused for 2 h after a release</Badge> : news.fed_releases?.[0]?.title}
              </div>
            </>
          ) : <div className="muted small">Fed feed unavailable.</div>}
        </div>
      </div>

      <h3 className="subhead">How the news is turning <span className="muted small">(last 24 h vs. the week before)</span></h3>
      {themes.length === 0 ? <p className="muted small">GDELT didn't answer this round; it rate-limits busy networks.</p> : (
        <ul className="bars tone-bars">
          {themes.map(([name, t]) => (
            <li key={name} className="bar-row">
              <span className="bar-label" title={name}>{THEME_LABELS[name] ?? name}</span>
              <ToneBar shift={t.shift} />
              <span className={`bar-value ${t.shift < 0 ? 'down' : t.shift > 0 ? 'up' : ''}`}>
                {t.shift > 0 ? '+' : ''}{t.shift.toFixed(2)}
              </span>
            </li>
          ))}
        </ul>
      )}
      <p className="caption">
        Tone of worldwide English coverage (GDELT). Left = darker than usual. Gold reads the mirror image:{' '}
        <Signal reading={readings.policy_for_gold} />
      </p>
      {errors.length > 0 && (
        <details className="caption"><summary>{errors.length} source(s) unavailable</summary>
          <ul className="why">{errors.map(([k, v]) => <li key={k}><strong>{k}</strong>: {v}</li>)}</ul>
        </details>
      )}
    </Card>
  )
}

function txLink(t: WhaleTransfer) {
  return t.tx ? `https://etherscan.io/tx/${t.tx}` : undefined
}

function Transfers({ rows, unit }: { rows: WhaleTransfer[]; unit: 'usd' | 'eth' }) {
  if (rows.length === 0) return <p className="muted small">No large transfers in this window.</p>
  return (
    <ul className="feed">
      {rows.slice(0, 6).map((t, i) => {
        const kind = t.direction ?? t.kind ?? ''
        const into = kind === 'to_exchange'
        const out = kind === 'from_exchange'
        return (
          <li key={`${t.tx}-${i}`} className="feed-item">
            <Icon name={into ? 'down' : out ? 'up' : 'trades'} size={16} />
            <span className="feed-msg">
              <strong>{unit === 'usd' ? moneyCompact(t.usd ?? 0) : `${quantity(t.eth ?? 0)} ETH`}</strong>{' '}
              {into ? `into ${t.exchange}` : out ? `out of ${t.exchange}` : kind === 'exchange_internal' ? 'between exchanges' : 'wallet to wallet'}
            </span>
            {txLink(t) && (
              <a className="muted small" href={txLink(t)} target="_blank" rel="noreferrer noopener" aria-label="View on Etherscan">
                <Icon name="external" size={14} />
              </a>
            )}
          </li>
        )
      })}
    </ul>
  )
}

function WhaleCard({ whales, readings }: { whales: WhaleFlows | null; readings: IntelResponse['readings'] }) {
  if (!whales) return <Card title="Whale flows"><Empty title="Not loaded yet" /></Card>
  const s = whales.stablecoins
  const e = whales.eth
  const errors = Object.entries(whales.errors)
  return (
    <Card title="Whale flows" action={<span className="muted small">{whales.exchanges_tracked} exchange wallets tracked</span>}>
      <div className="intel-grid">
        <div className="intel-stat">
          <div className="tile-label">Dollars (USDT) onto exchanges · {s?.hours ?? 1} h</div>
          {s ? (
            <>
              <div className={`tile-value ${s.netflow_usd > 0 ? 'up' : s.netflow_usd < 0 ? 'down' : ''}`}>
                {s.netflow_usd >= 0 ? '+' : '−'}{moneyCompact(Math.abs(s.netflow_usd))}
              </div>
              <div className="tile-hint">in {moneyCompact(s.inflow_usd)} · out {moneyCompact(s.outflow_usd)}</div>
              <div className="row"><span className="small">For BTC:</span><Signal reading={readings.whales_for_btc} /></div>
            </>
          ) : <div className="muted small">Unavailable</div>}
        </div>
        <div className="intel-stat">
          <div className="tile-label">ETH onto exchanges · last {e?.blocks ?? 50} blocks</div>
          {e ? (
            <>
              <div className={`tile-value ${e.netflow_eth > 0 ? 'down' : e.netflow_eth < 0 ? 'up' : ''}`}>
                {e.netflow_eth >= 0 ? '+' : '−'}{quantity(Math.abs(e.netflow_eth))} ETH
              </div>
              <div className="tile-hint">in {quantity(e.inflow_eth)} · out {quantity(e.outflow_eth)} (transfers ≥ {e.min_eth} ETH)</div>
              <div className="row"><span className="small">For ETH:</span><Signal reading={readings.whales_for_eth} /></div>
            </>
          ) : <div className="muted small">Unavailable</div>}
        </div>
      </div>
      <div className="intel-grid">
        <div><h3 className="subhead">Biggest dollar moves</h3><Transfers rows={s?.largest ?? []} unit="usd" /></div>
        <div><h3 className="subhead">Biggest ETH moves</h3><Transfers rows={e?.largest ?? []} unit="eth" /></div>
      </div>
      <p className="caption">
        Why not just copy whales? The biggest wallets are mostly exchanges, ETFs and custodians, and studies find no
        reliable edge in copying them. What has predicted 1–6 h moves is money arriving <em>at exchanges</em>:
        dollars arriving → buying power (up); ETH arriving → supply to sell (down).
      </p>
      {errors.length > 0 && (
        <details className="caption"><summary>{errors.length} source(s) unavailable</summary>
          <ul className="why">{errors.map(([k, v]) => <li key={k}><strong>{k}</strong>: {v}</li>)}</ul>
        </details>
      )}
    </Card>
  )
}

export function Intel({ notify }: { notify: (kind: ToastKind, message: string) => void }) {
  const [intel, setIntel] = useState<IntelResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async (refresh: boolean) => {
    setLoading(true)
    try {
      setIntel(await api.intel(refresh))
      setError(null)
    } catch (e) {
      const message = e instanceof ApiError ? e.message : 'Could not reach the server'
      setError(message)
      if (refresh) notify('error', message)
    } finally {
      setLoading(false)
    }
  }, [notify])

  useEffect(() => {
    let active = true
    api.intel().then(
      (result) => { if (active) setIntel(result) },
      (e) => { if (active) setError(e instanceof ApiError ? e.message : 'Could not reach the server') },
    )
    return () => { active = false }
  }, [])

  return (
    <div className="page">
      <div className="toolbar">
        <p className="muted intel-lede">
          What politics, the economy and the biggest wallets are doing right now. These are <strong>supporting
          evidence only</strong>: they can confirm a setup, block it, or shrink it, but never start a trade on their own.
        </p>
        <div className="row">
          {intel?.refreshed_at && <span className="muted small">Updated {ago(intel.refreshed_at)}</span>}
          <button className="btn" onClick={() => void load(true)} disabled={loading}>
            <Icon name="refresh" size={16} /> {loading ? 'Loading… (up to a minute)' : 'Refresh'}
          </button>
        </div>
      </div>
      {error && !intel ? (
        <div className="card"><Empty title="Couldn't load intel">{error}</Empty></div>
      ) : !intel ? (
        <><div className="skeleton tall" /><div className="skeleton tall" /></>
      ) : (
        <div className="intel-cards">
          <NewsCard news={intel.news} readings={intel.readings} />
          <WhaleCard whales={intel.whales} readings={intel.readings} />
        </div>
      )}
    </div>
  )
}
