import type { Alert, Portfolio } from '../lib/api'
import { ago, money, moneyCompact, pct, signedMoney, signedPct, tone } from '../lib/format'
import { EquityChart } from '../components/EquityChart'
import { Badge, Card, Empty, StatTile } from '../components/ui'

/** Share of equity per position, as thin bars with the value at the tip. */
function Exposure({ portfolio }: { portfolio: Portfolio }) {
  const rows = portfolio.positions
    .map((p) => ({ symbol: p.symbol, side: p.side, value: p.quantity * p.current_price }))
    .sort((a, b) => b.value - a.value)
  if (!rows.length) return <Empty title="No open positions">New trades will show up here.</Empty>
  const equity = Math.max(portfolio.account_equity, 1)
  const max = Math.max(...rows.map((r) => r.value))
  return (
    <ul className="bars" aria-label="Position size as share of equity">
      {rows.map((r) => {
        const share = (r.value / equity) * 100
        return (
          <li key={r.symbol} className="bar-row" title={`${r.symbol}: ${money(r.value)} (${pct(share, 1)} of equity)`}>
            <span className="bar-label">
              {r.symbol}
              <span className="muted"> {r.side === 'BUY' ? 'long' : 'short'}</span>
            </span>
            <span className="bar-track">
              <span className="bar-fill" style={{ width: `${(r.value / max) * 100}%` }} />
            </span>
            <span className="bar-value">{pct(share, 1)}</span>
          </li>
        )
      })}
    </ul>
  )
}

export function Overview({ portfolio, alerts, onNavigate }: {
  portfolio: Portfolio
  alerts: Alert[]
  onNavigate: (page: 'positions' | 'integrations' | 'safety') => void
}) {
  const start = portfolio.account_equity - portfolio.total_pnl
  const winners = portfolio.recent_trades.filter((t) => t.pnl > 0).length
  const closed = portfolio.recent_trades.length

  return (
    <div className="page">
      <section className="hero">
        <div>
          <div className="hero-label">Account equity</div>
          <div className="hero-value">{money(portfolio.account_equity)}</div>
          <div className={`hero-delta ${tone(portfolio.total_pnl)}`}>
            {signedMoney(portfolio.total_pnl)} ({signedPct(portfolio.total_pnl_pct)}) since start
          </div>
        </div>
        <div className="hero-badges">
          {portfolio.mode === 'demo'
            ? <Badge status="good">Practice mode: no real money</Badge>
            : <Badge status="warning">Live broker account</Badge>}
          {portfolio.halted
            ? <Badge status="critical">Trading halted</Badge>
            : <Badge status="neutral">Safety rules on</Badge>}
        </div>
      </section>

      <div className="tiles">
        <StatTile label="Cash" value={moneyCompact(portfolio.cash)} hint="Not tied up in positions" />
        <StatTile
          label="Open profit/loss"
          value={signedMoney(portfolio.unrealized_pnl)}
          deltaTone={tone(portfolio.unrealized_pnl)}
          delta={`${portfolio.positions.length} open position${portfolio.positions.length === 1 ? '' : 's'}`}
        />
        <StatTile
          label="Closed profit/loss"
          value={signedMoney(portfolio.realized_pnl)}
          deltaTone={tone(portfolio.realized_pnl)}
          delta={closed ? `${winners} of ${closed} trades won` : 'No closed trades yet'}
        />
        <StatTile label="Worst drop from peak" value={pct(portfolio.max_drawdown)} hint="Max drawdown this session" />
      </div>

      <div className="grid-2">
        <Card title="Equity this session" className="span-2">
          <EquityChart points={portfolio.equity_curve} baseline={start} />
          <p className="caption">Dashed line marks where the session started ({money(start)}).</p>
        </Card>

        <Card
          title="Where the money is"
          action={<button className="link-btn" onClick={() => onNavigate('positions')}>All positions →</button>}
        >
          <Exposure portfolio={portfolio} />
        </Card>

        <Card title="Latest activity">
          {alerts.length === 0 ? (
            <Empty title="All quiet">Stops, targets and safety events will appear here.</Empty>
          ) : (
            <ul className="feed">
              {alerts.slice(0, 6).map((a, i) => (
                <li key={i} className={`feed-item ${a.severity.toLowerCase()}`}>
                  <Badge status={a.severity === 'CRITICAL' ? 'critical' : a.severity === 'WARNING' ? 'warning' : 'neutral'}>
                    {a.symbol ?? a.alert_type.replace('_', ' ').toLowerCase()}
                  </Badge>
                  <span className="feed-msg">{a.message}</span>
                  <span className="muted small">{ago(a.timestamp)}</span>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>
    </div>
  )
}
