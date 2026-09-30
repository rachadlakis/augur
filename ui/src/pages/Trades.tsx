import type { Trade } from '../lib/api'
import { dateTime, money, quantity, signedMoney, signedPct, tone } from '../lib/format'
import { Card, Empty, StatTile } from '../components/ui'

const REASONS: Record<string, string> = {
  hit_stop: 'Stop hit',
  hit_target: 'Target hit',
  thesis_invalidated: 'Idea no longer valid',
  manual_close: 'Closed by you',
}

const reason = (status: string) =>
  REASONS[status] ?? (status.startsWith('kill_switch') ? 'Kill switch' : status.replace(/_/g, ' '))

export function Trades({ trades }: { trades: Trade[] }) {
  const wins = trades.filter((t) => t.pnl > 0)
  const losses = trades.filter((t) => t.pnl < 0)
  const grossWin = wins.reduce((s, t) => s + t.pnl, 0)
  const grossLoss = Math.abs(losses.reduce((s, t) => s + t.pnl, 0))
  const total = trades.reduce((s, t) => s + t.pnl, 0)

  return (
    <div className="page">
      <div className="tiles">
        <StatTile label="Closed trades" value={String(trades.length)} />
        <StatTile label="Win rate" value={trades.length ? `${Math.round((wins.length / trades.length) * 100)}%` : '—'}
          hint="Winning trades ÷ all trades" />
        <StatTile label="Profit factor" value={grossLoss > 0 ? (grossWin / grossLoss).toFixed(2) : grossWin > 0 ? '∞' : '—'}
          hint="Money won ÷ money lost; above 1 is good" />
        <StatTile label="Net result" value={signedMoney(total)} deltaTone={tone(total)} />
      </div>

      <Card title="Trade history">
        {trades.length === 0 ? (
          <Empty title="No closed trades yet">Every closed trade lands here with why it closed.</Empty>
        ) : (
          <div className="table-scroll">
            <table className="table">
              <thead>
                <tr>
                  <th>Closed</th>
                  <th>Symbol</th>
                  <th>Side</th>
                  <th className="num">Qty</th>
                  <th className="num">Entry</th>
                  <th className="num">Exit</th>
                  <th className="num">Profit/loss</th>
                  <th>Why it closed</th>
                </tr>
              </thead>
              <tbody>
                {[...trades].reverse().map((t) => (
                  <tr key={t.trade_id}>
                    <td className="muted">{dateTime(t.exit_time)}</td>
                    <td className="strong">{t.symbol}</td>
                    <td>{t.side === 'BUY' ? 'Long' : 'Short'}</td>
                    <td className="num">{quantity(t.quantity)}</td>
                    <td className="num">{money(t.entry_price)}</td>
                    <td className="num">{money(t.exit_price)}</td>
                    <td className={`num ${tone(t.pnl)}`}>
                      {signedMoney(t.pnl)}
                      <div className="small">{signedPct(t.pnl_pct)}</div>
                    </td>
                    <td>{reason(t.thesis_status)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  )
}
