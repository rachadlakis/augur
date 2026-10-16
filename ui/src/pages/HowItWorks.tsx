import { useState } from 'react'
import { Badge, Card } from '../components/ui'

// Every number on this page is the default in agents/augur_agents/trading/
// (risk.py, execution.py, guard.py, orchestrator.py, specialists.py). If one
// changes there, change it here.

type StageId = 'data' | 'specialists' | 'consensus' | 'risk' | 'execution' | 'broker' | 'watch'

interface Stage {
  id: StageId
  step: number
  title: string
  short: string
  detail: string[]
}

const STAGES: Stage[] = [
  {
    id: 'data', step: 1, title: 'Gather data', short: 'Prices, macro, news, whale flows',
    detail: [
      'Prices: hourly and daily bars from Alpaca for crypto, gold, silver, oil and the S&P 500.',
      'Macro: the 10-year real yield (FRED) for gold, and the Economic Policy Uncertainty index.',
      'News: the tone of worldwide coverage of rates, inflation, trade, war and recession (GDELT), plus the Fed’s own press releases.',
      'Whales: dollars and ETH moving onto and off seven verified exchange wallets, read straight from the Ethereum chain.',
      'Missing data is reported as missing. Augur never fills a gap with a guess.',
    ],
  },
  {
    id: 'specialists', step: 2, title: 'Specialists vote', short: 'Each one says BUY, SELL or nothing',
    detail: [
      'Technical: do the 1h, 4h and 1d bars agree on a direction? Bigger timeframes count more (weights 1, 1.5, 2).',
      'Macro: Fed tone and the dollar for risk assets; real yields for gold (rising real yields push gold down).',
      'Term structure: for oil funds, whether rolling futures costs or pays.',
      'News, policy and whale specialists are “secondary”: they can agree or disagree, but they are the easiest inputs to fake, so they can never be the deciding vote.',
      'A specialist with no data abstains. It never votes BUY by default.',
    ],
  },
  {
    id: 'consensus', step: 3, title: 'Weigh the evidence', short: 'Needs a score of ±0.25 with no conflict',
    detail: [
      'Each vote counts confidence × evidence quality × freshness. A strong technical read alone reaches about 0.18: on purpose, one signal is never enough.',
      'The score must reach ±0.25 — and the primary specialists must reach it without help from news or whales.',
      'If anyone with weight says BUY while another says SELL, that is a conflict and the answer is “no trade”.',
      'With enough history, stated confidences are replaced by measured hit rates (calibration), and a trade must show a positive Kelly edge.',
    ],
  },
  {
    id: 'risk', step: 4, title: 'Risk engine', short: 'Sizes the trade, or vetoes it',
    detail: [
      'At most 0.5% of the account is risked per trade: size = equity × 0.5% ÷ distance to the stop.',
      'Stop at 2× the average true range (ATR), target at 4× ATR, so reward/risk is 2:1 (minimum 1.5:1).',
      'Caps: 10% of equity in one asset, 20% across the portfolio and across correlated assets. Shorts don’t offset longs.',
      'After a 2% loss in one day, no new entries until tomorrow.',
      'Very high policy uncertainty halves the risk per trade. Nothing can enlarge it.',
    ],
  },
  {
    id: 'execution', step: 5, title: 'Execution checks', short: 'Is now a sane moment to enter?',
    detail: [
      'Refuses when the spread or expected slippage is above 0.2%, or liquidity is thin.',
      'Refuses signals older than 20 seconds, and entries that chase a move of more than 0.75% in the last hour.',
      'Kill switch and rate limits: at most 2 new entries per hour and 6 per day. Overtrading is the most common way automated traders lose.',
      'Pauses entries for 2 hours after an FOMC statement or minutes are released.',
    ],
  },
  {
    id: 'broker', step: 6, title: 'Bracketed order', short: 'Entry, stop and target sent together',
    detail: [
      'Stocks and funds: one bracket order at Alpaca, so the stop and target live at the broker from the first second.',
      'Crypto (no brackets at Alpaca): fill, then attach a stop at once. If the stop can’t be attached, the position is closed immediately.',
      'Real-money accounts require typing “REAL MONEY” for every order. Practice (paper) is the default.',
      'The server re-derives size from the live price; numbers from the browser are never trusted.',
    ],
  },
  {
    id: 'watch', step: 7, title: 'Watch & learn', short: 'Exits, reconciliation, journal',
    detail: [
      'Prices refresh every 5 seconds; the broker book is reconciled every 15 seconds and exits are recorded at the broker’s real fill price.',
      'Stops and targets the broker can’t hold are enforced by Augur. A refused exit is retried every 30 seconds and raised as a critical alert.',
      'Every closed trade is journaled. Outcomes feed the calibrator so specialists that keep being wrong lose their vote.',
      'The kill switch flattens everything. If the broker refuses, Augur says so and keeps the positions on screen rather than pretending.',
    ],
  },
]

// ---------------------------------------------------------------------------
// Consensus playground: the same arithmetic as trading/orchestrator.py with
// the pipeline's defaults (evidence quality and freshness 0.5 each).
// ---------------------------------------------------------------------------

type Vote = 'BUY' | 'SELL' | 'NEUTRAL'

interface Voter {
  id: string
  label: string
  max: number
  secondary: boolean
  vote: Vote
  confidence: number
}

const INITIAL: Voter[] = [
  { id: 'technical', label: 'Technical (price trend)', max: 0.7, secondary: false, vote: 'BUY', confidence: 0.6 },
  { id: 'macro', label: 'Macro (Fed, dollar, yields)', max: 0.6, secondary: false, vote: 'NEUTRAL', confidence: 0.55 },
  { id: 'derivatives', label: 'Derivatives (funding, basis)', max: 0.7, secondary: false, vote: 'NEUTRAL', confidence: 0.7 },
  { id: 'news', label: 'News sentiment', max: 0.9, secondary: true, vote: 'BUY', confidence: 0.9 },
  { id: 'policy', label: 'Politics & economy', max: 0.5, secondary: true, vote: 'BUY', confidence: 0.5 },
  { id: 'whales', label: 'Whale flows', max: 0.4, secondary: true, vote: 'BUY', confidence: 0.4 },
]

const QUALITY = 0.5
const FRESHNESS = 0.5
const THRESHOLD = 0.25

function decide(voters: Voter[]) {
  let total = 0
  let primary = 0
  let buys = 0
  let sells = 0
  for (const v of voters) {
    const direction = v.vote === 'BUY' ? 1 : v.vote === 'SELL' ? -1 : 0
    const weight = v.confidence * QUALITY * FRESHNESS
    total += direction * weight
    if (!v.secondary) primary += direction * weight
    if (weight > 0 && v.vote === 'BUY') buys++
    if (weight > 0 && v.vote === 'SELL') sells++
  }
  let decision: 'BUY' | 'SELL' | 'NO_TRADE' = total > 0 ? 'BUY' : 'SELL'
  let why = `Score ${total.toFixed(3)} clears ±${THRESHOLD}, the price/macro evidence clears it alone (${primary.toFixed(3)}), and nobody disagrees.`
  if (buys && sells) {
    decision = 'NO_TRADE'
    why = 'Some specialists say BUY and others SELL. Disagreement means sitting out.'
  } else if (Math.abs(total) < THRESHOLD) {
    decision = 'NO_TRADE'
    why = `Score ${total.toFixed(3)} is inside ±${THRESHOLD}: not enough agreement.`
  } else if (Math.abs(primary) < THRESHOLD || primary * total <= 0) {
    decision = 'NO_TRADE'
    why = `Only news/whales push the score over the line (price/macro alone: ${primary.toFixed(3)}). They may confirm, never decide.`
  }
  return { total, primary, decision, why }
}

function Playground() {
  const [voters, setVoters] = useState(INITIAL)
  const result = decide(voters)
  const update = (id: string, patch: Partial<Voter>) =>
    setVoters((vs) => vs.map((v) => (v.id === id ? { ...v, ...patch } : v)))
  const scale = (x: number) => `${50 + Math.max(-1, Math.min(1, x / 0.5)) * 50}%`

  return (
    <Card title="Try it: how a decision is made" action={
      <button className="btn ghost" onClick={() => setVoters(INITIAL)}>Reset</button>
    }>
      <p className="muted">
        Change the votes and see what Augur would do. This is the same arithmetic the real system uses.
        Start by setting <strong>Macro</strong> to BUY.
      </p>
      <div className="voters">
        {voters.map((v) => (
          <div key={v.id} className={`voter ${v.secondary ? 'secondary' : ''}`}>
            <div className="voter-name">
              <span className="strong">{v.label}</span>
              {v.secondary && <span className="tag">confirm only</span>}
            </div>
            <div className="segmented small-seg" role="radiogroup" aria-label={`${v.label} vote`}>
              {(['BUY', 'NEUTRAL', 'SELL'] as Vote[]).map((option) => (
                <button key={option} role="radio" aria-checked={v.vote === option}
                  className={v.vote === option ? 'active' : ''} onClick={() => update(v.id, { vote: option })}>
                  {option === 'NEUTRAL' ? '—' : option}
                </button>
              ))}
            </div>
            <label className="voter-conf">
              <span className="sr-only">{v.label} confidence</span>
              <input type="range" min={0} max={v.max} step={0.05} value={v.confidence}
                onChange={(e) => update(v.id, { confidence: Number(e.target.value) })} />
              <span className="mono small">{Math.round(v.confidence * 100)}%</span>
            </label>
          </div>
        ))}
      </div>

      <div className="scale" aria-hidden="true">
        <span className="scale-zone sell" style={{ left: 0, width: scale(-THRESHOLD) }} />
        <span className="scale-zone buy" style={{ left: scale(THRESHOLD), right: 0 }} />
        <span className="scale-mark primary" style={{ left: scale(result.primary) }} title="price/macro only" />
        <span className="scale-mark total" style={{ left: scale(result.total) }} title="everything" />
      </div>
      <div className="scale-legend muted small">
        <span>SELL zone</span><span>◆ all evidence · ● price/macro only</span><span>BUY zone</span>
      </div>

      <div className={`verdict ${result.decision === 'NO_TRADE' ? 'no' : 'yes'}`} aria-live="polite">
        {result.decision === 'NO_TRADE' ? <Badge status="neutral">No trade</Badge>
          : <Badge status="good">{result.decision === 'BUY' ? 'Buy' : 'Sell'} → on to the risk engine</Badge>}
        <span>{result.why}</span>
      </div>
    </Card>
  )
}

export function HowItWorks() {
  const [open, setOpen] = useState<StageId>('consensus')
  const stage = STAGES.find((s) => s.id === open) ?? STAGES[0]

  return (
    <div className="page">
      <section className="hero how-hero">
        <div>
          <div className="hero-label">How Augur works</div>
          <div className="hero-title">Many opinions, one strict referee.</div>
          <p className="muted how-lede">
            Augur asks several specialists what they see, only acts when the strong evidence agrees, and then lets a
            rule-based risk engine — which no model can argue with — decide how much, if anything, to risk.
            Click a step to see exactly what it does.
          </p>
        </div>
      </section>

      <Card>
        <ol className="flow" aria-label="Decision pipeline">
          {STAGES.map((s) => (
            <li key={s.id} className="flow-item">
              <button className={`flow-step ${open === s.id ? 'active' : ''} ${s.id}`} aria-expanded={open === s.id}
                onClick={() => setOpen(s.id)}>
                <span className="flow-num">{s.step}</span>
                <span className="flow-text">
                  <span className="strong">{s.title}</span>
                  <span className="muted small">{s.short}</span>
                </span>
              </button>
            </li>
          ))}
        </ol>
        <div className="flow-detail" aria-live="polite">
          <h2>{stage.step}. {stage.title}</h2>
          <ul className="flow-points">{stage.detail.map((d) => <li key={d}>{d}</li>)}</ul>
        </div>
        <p className="caption">
          Any step can stop the trade. A trade only happens when every step says yes — most of the time the answer is
          “no trade”, and that is the system working.
        </p>
      </Card>

      <Playground />

      <Card title="What Augur will not do">
        <ul className="rules nots">
          <li><strong>Promise profits.</strong> Live studies of AI trading agents show small, inconsistent edges; the goal is to survive and learn, not to get rich fast.</li>
          <li><strong>Trade on a headline.</strong> Headline text never reaches the strategy, and news can’t be the deciding vote.</li>
          <li><strong>Copy whales blindly.</strong> The biggest wallets are mostly exchanges and funds; Augur reads exchange flows instead.</li>
          <li><strong>Hold a position without a stop.</strong> If protection can’t be attached, the position is closed.</li>
          <li><strong>Touch your private keys.</strong> Wallets are watch-only by public address; no code path signs a transaction.</li>
          <li><strong>Use real money by accident.</strong> Live mode needs two flags flipped and the typed phrase on every order.</li>
        </ul>
      </Card>
    </div>
  )
}
