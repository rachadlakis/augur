import { useCallback, useEffect, useState } from 'react'
import { api, ApiError } from '../lib/api'
import type { Integration, IntegrationsResponse } from '../lib/api'
import { Badge, Card, Empty, Icon } from '../components/ui'
import type { ToastKind } from '../hooks/useToasts'

type Filter = 'all' | 'broker' | 'data'

const FIELD_LABELS: Record<string, string> = {
  ALPACA_API_KEY: 'Key ID',
  ALPACA_SECRET_KEY: 'Secret Key',
  BINANCE_API_KEY: 'API Key',
  BINANCE_API_SECRET: 'Secret Key',
}

function KeyField({ name, value, onChange }: { name: string; value: string; onChange: (v: string) => void }) {
  const [visible, setVisible] = useState(false)
  const label = FIELD_LABELS[name] ?? 'API key'
  return (
    <label className="field">
      <span className="field-label">{label} <code className="muted small">{name}</code></span>
      <span className="input-wrap">
        <input
          className="input mono"
          type={visible ? 'text' : 'password'}
          autoComplete="off"
          spellCheck={false}
          placeholder={`Paste your ${label.toLowerCase()} here`}
          value={value}
          onChange={(e) => onChange(e.target.value)}
        />
        <button type="button" className="icon-btn" aria-label={visible ? 'Hide key' : 'Show key'} onClick={() => setVisible((v) => !v)}>
          <Icon name="eye" size={16} />
        </button>
      </span>
    </label>
  )
}

function IntegrationCard({ integration, open, onToggle, onSaved, notify }: {
  integration: Integration
  open: boolean
  onToggle: () => void
  onSaved: (updated: Integration) => void
  notify: (kind: ToastKind, message: string) => void
}) {
  const [values, setValues] = useState<Record<string, string>>({})
  const [busy, setBusy] = useState<'save' | 'test' | null>(null)
  const [result, setResult] = useState<{ ok: boolean; message: string } | null>(null)
  const filled = integration.env_vars.filter((v) => values[v]?.trim()).length

  const test = async () => {
    setBusy('test')
    try {
      setResult(await api.testIntegration(integration.id))
    } catch (e) {
      setResult({ ok: false, message: e instanceof ApiError ? e.message : 'Could not reach the Augur server' })
    } finally {
      setBusy(null)
    }
  }

  const save = async () => {
    setBusy('save')
    setResult(null)
    try {
      const response = await api.saveKeys(integration.id, values)
      setValues({})  // never keep secrets in page state longer than needed
      onSaved(response.integration)
      notify('success', `${integration.name} keys saved`)
      if (integration.category === 'broker' && response.integration.configured) await test()
    } catch (e) {
      notify('error', e instanceof ApiError ? e.message : 'Could not reach the Augur server')
    } finally {
      setBusy((b) => (b === 'save' ? null : b))
    }
  }

  return (
    <article className={`integration ${integration.configured ? 'done' : ''} ${open ? 'open' : ''}`}>
      <button className="integration-head" onClick={onToggle} aria-expanded={open}>
        <span className="integration-emoji" aria-hidden="true">{integration.emoji}</span>
        <span className="integration-title">
          <span className="strong">{integration.name}</span>
          <span className="muted small">{integration.what_it_does}</span>
        </span>
        {integration.configured
          ? <Badge status="good">Connected</Badge>
          : integration.required ? <Badge status="warning">Start here</Badge> : <Badge status="neutral">Optional</Badge>}
      </button>

      {open && (
        <div className="integration-body">
          <ol className="steps">
            {integration.steps.map((step, i) => <li key={i}>{step}</li>)}
          </ol>
          <div className="row">
            <a className="btn ghost" href={integration.signup_url} target="_blank" rel="noreferrer">
              1. Open {integration.name} <Icon name="external" size={14} />
            </a>
            {integration.key_url !== integration.signup_url && (
              <a className="btn ghost" href={integration.key_url} target="_blank" rel="noreferrer">
                Go to the keys page <Icon name="external" size={14} />
              </a>
            )}
          </div>

          <div className="fields">
            {integration.env_vars.map((name) => (
              <KeyField key={name} name={name} value={values[name] ?? ''}
                onChange={(v) => setValues((all) => ({ ...all, [name]: v }))} />
            ))}
          </div>

          <div className="row">
            <button className="btn primary" disabled={filled === 0 || busy !== null} onClick={save}>
              {busy === 'save' ? 'Saving…' : '2. Save keys'}
            </button>
            <button className="btn ghost" disabled={!integration.configured || busy !== null} onClick={test}>
              {busy === 'test' ? 'Checking…' : '3. Test connection'}
            </button>
          </div>

          {result && (
            <div className={`callout ${result.ok ? 'good' : 'critical'}`} role="status">
              <Icon name={result.ok ? 'check' : 'alert'} size={16} />
              <span>{result.message}</span>
            </div>
          )}
          {integration.safe_mode && (
            <p className="muted small">🛡️ Practice mode is on for {integration.name}: it can't touch real money.</p>
          )}
        </div>
      )}
    </article>
  )
}

export function Integrations({ notify }: { notify: (kind: ToastKind, message: string) => void }) {
  const [data, setData] = useState<IntegrationsResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [filter, setFilter] = useState<Filter>('all')
  const [openId, setOpenId] = useState<string | null>(null)

  const load = useCallback(async () => {
    try {
      const response = await api.integrations()
      setData(response)
      setError(null)
      setOpenId((current) => current ?? response.integrations.find((i) => i.required && !i.configured)?.id ?? null)
    } catch {
      setError('Start the Augur server first: python src/dashboard_api.py')
    }
  }, [])

  useEffect(() => { load() }, [load])

  if (error) return <div className="page"><Card><Empty title="Can't reach Augur">{error}</Empty></Card></div>
  if (!data) return <div className="page"><div className="skeleton tall" /></div>

  const all = data.integrations
  const connected = all.filter((i) => i.configured).length
  const shown = all.filter((i) => filter === 'all' || i.category === filter)

  return (
    <div className="page">
      <section className="hero integrations-hero">
        <div>
          <div className="hero-label">Connections</div>
          <div className="hero-title">Plug Augur into the world</div>
          <p className="muted">Each one takes about two minutes: open the website, copy the keys, paste them here, press Test.</p>
        </div>
        <div className="progress" aria-label={`${connected} of ${all.length} connected`}>
          <div className="progress-text"><span className="strong">{connected}</span> of {all.length} connected</div>
          <div className="progress-track"><div className="progress-fill" style={{ width: `${(connected / all.length) * 100}%` }} /></div>
          <Badge status="good">Practice money only</Badge>
        </div>
      </section>

      <div className="segmented" role="tablist" aria-label="Filter connections">
        {(['all', 'broker', 'data'] as const).map((f) => (
          <button key={f} role="tab" aria-selected={filter === f} className={filter === f ? 'active' : ''} onClick={() => setFilter(f)}>
            {f === 'all' ? 'All' : f === 'broker' ? 'Trading accounts' : 'Data feeds'}
          </button>
        ))}
      </div>

      <div className="integrations">
        {shown.map((integration) => (
          <IntegrationCard
            key={integration.id}
            integration={integration}
            open={openId === integration.id}
            onToggle={() => setOpenId((id) => (id === integration.id ? null : integration.id))}
            onSaved={(updated) => setData((d) => d && {
              ...d, integrations: d.integrations.map((i) => (i.id === updated.id ? updated : i)),
            })}
            notify={notify}
          />
        ))}
      </div>

      <p className="muted small center">
        Keys are saved only on this computer, in the <code>.env</code> file. They are never shown again or sent anywhere else.
      </p>
    </div>
  )
}
