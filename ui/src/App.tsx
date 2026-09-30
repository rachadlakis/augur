import { useEffect, useState } from 'react'
import { useDashboard } from './hooks/useDashboard'
import type { Connection } from './hooks/useDashboard'
import { useToasts } from './hooks/useToasts'
import { Badge, Empty, Icon, Toasts } from './components/ui'
import type { IconName } from './components/ui'
import { Overview } from './pages/Overview'
import { Markets } from './pages/Markets'
import { Positions } from './pages/Positions'
import { Trades } from './pages/Trades'
import { Assistant } from './pages/Assistant'
import { Integrations } from './pages/Integrations'
import { Safety } from './pages/Safety'

type Page = 'overview' | 'markets' | 'positions' | 'trades' | 'assistant' | 'integrations' | 'safety'

const NAV: { id: Page; label: string; icon: IconName }[] = [
  { id: 'overview', label: 'Overview', icon: 'overview' },
  { id: 'markets', label: 'Markets', icon: 'markets' },
  { id: 'positions', label: 'Positions', icon: 'positions' },
  { id: 'trades', label: 'Trades', icon: 'trades' },
  { id: 'assistant', label: 'Assistant', icon: 'assistant' },
  { id: 'integrations', label: 'Integrations', icon: 'integrations' },
  { id: 'safety', label: 'Safety', icon: 'safety' },
]

const CONNECTION: Record<Connection, { label: string; status: 'good' | 'warning' | 'critical' | 'neutral' }> = {
  live: { label: 'Live', status: 'good' },
  polling: { label: 'Reconnecting', status: 'warning' },
  connecting: { label: 'Connecting', status: 'neutral' },
  offline: { label: 'Offline', status: 'critical' },
}

function readStored(key: string): string | null {
  try { return localStorage.getItem(key) } catch { return null }
}

function writeStored(key: string, value: string) {
  try { localStorage.setItem(key, value) } catch { /* private mode: fine */ }
}

function pageFromHash(): Page {
  const hash = window.location.hash.slice(1)
  return (NAV.some((n) => n.id === hash) ? hash : 'overview') as Page
}

export default function App() {
  const { portfolio, health, alerts, connection, refresh } = useDashboard()
  const { toasts, notify, dismiss } = useToasts()
  const [page, setPage] = useState<Page>(pageFromHash)
  const [theme, setTheme] = useState<'light' | 'dark' | null>(() => readStored('augur-theme') as 'light' | 'dark' | null)

  useEffect(() => {
    const onHash = () => setPage(pageFromHash())
    window.addEventListener('hashchange', onHash)
    return () => window.removeEventListener('hashchange', onHash)
  }, [])

  useEffect(() => {
    if (theme) {
      document.documentElement.dataset.theme = theme
      writeStored('augur-theme', theme)
    }
  }, [theme])

  const go = (next: Page) => { window.location.hash = next }
  const isDark = theme === 'dark' || (theme === null && window.matchMedia('(prefers-color-scheme: dark)').matches)
  const halted = health?.halted ?? portfolio?.halted ?? false
  const conn = CONNECTION[connection]

  const content = () => {
    if (page === 'integrations') return <Integrations notify={notify} />
    if (page === 'markets') {
      return <Markets onConnect={() => go('integrations')} mode={health?.mode ?? portfolio?.mode ?? 'demo'} notify={notify} />
    }
    if (!portfolio) {
      return (
        <div className="page">
          {connection === 'offline' ? (
            <div className="card">
              <Empty title="The Augur server isn't running">
                Start it from the project folder with <code>python src/dashboard_api.py</code>, then this page connects by itself.
              </Empty>
            </div>
          ) : (
            <>
              <div className="skeleton hero-skel" />
              <div className="tiles">{[0, 1, 2, 3].map((i) => <div key={i} className="skeleton tile-skel" />)}</div>
              <div className="skeleton tall" />
            </>
          )}
        </div>
      )
    }
    switch (page) {
      case 'positions': return <Positions positions={portfolio.positions} notify={notify} />
      case 'trades': return <Trades trades={portfolio.recent_trades} />
      case 'assistant': return <Assistant portfolio={portfolio} alerts={alerts} notify={notify} />
      case 'safety': return <Safety health={health} portfolio={portfolio} notify={notify} onChanged={refresh} />
      default: return <Overview portfolio={portfolio} alerts={alerts} onNavigate={go} />
    }
  }

  return (
    <div className="shell">
      <nav className="sidebar" aria-label="Main">
        <div className="brand">
          <img className="brand-mark" src="/favicon.svg" alt="" width={30} height={30} />
          <span className="brand-name">Augur</span>
        </div>
        <ul>
          {NAV.map((item) => (
            <li key={item.id}>
              <a
                href={`#${item.id}`}
                className={`nav-item ${page === item.id ? 'active' : ''}`}
                aria-current={page === item.id ? 'page' : undefined}
              >
                <Icon name={item.icon} />
                <span className="nav-label">{item.label}</span>
                {item.id === 'positions' && portfolio && portfolio.positions.length > 0 && (
                  <span className="nav-count">{portfolio.positions.length}</span>
                )}
                {item.id === 'safety' && halted && <span className="nav-dot" aria-label="halted" />}
              </a>
            </li>
          ))}
        </ul>
        <div className="sidebar-foot muted small">Practice first. Real money only when you mean it.</div>
      </nav>

      <div className="main">
        <header className="topbar">
          <h1>{NAV.find((n) => n.id === page)?.label}</h1>
          <div className="topbar-right">
            {halted && <Badge status="critical">Trading halted</Badge>}
            {portfolio && portfolio.mode === 'demo' && <Badge status="neutral">Demo data</Badge>}
            {portfolio && portfolio.mode === 'paper' && <Badge status="good">Practice money</Badge>}
            {portfolio && portfolio.mode === 'live' && <Badge status="critical">REAL MONEY</Badge>}
            {portfolio && (portfolio.price_source === 'alpaca'
              ? <Badge status="good">Live prices</Badge>
              : <Badge status="neutral">Simulated prices</Badge>)}
            <Badge status={conn.status}>{conn.label}</Badge>
            <button
              className="icon-btn"
              aria-label={isDark ? 'Switch to light theme' : 'Switch to dark theme'}
              onClick={() => setTheme(isDark ? 'light' : 'dark')}
            >
              <Icon name={isDark ? 'sun' : 'moon'} />
            </button>
          </div>
        </header>
        <main>{content()}</main>
      </div>

      <Toasts toasts={toasts} onDismiss={dismiss} />
    </div>
  )
}
