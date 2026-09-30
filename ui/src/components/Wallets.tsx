import { useCallback, useEffect, useState } from 'react'
import { api, ApiError } from '../lib/api'
import type { WalletsResponse } from '../lib/api'
import { money } from '../lib/format'
import { Badge, Card, Empty, Icon } from './ui'
import type { ToastKind } from '../hooks/useToasts'

const EMPTY: WalletsResponse = { wallets: [], rpc_host: null, eth_price: null }

const short = (address: string) => `${address.slice(0, 6)}…${address.slice(-4)}`

/** Watch-only Ethereum wallets. Public addresses only; private keys are refused. */
export function Wallets({ notify }: { notify: (kind: ToastKind, message: string) => void }) {
  const [data, setData] = useState<WalletsResponse | null>(null)
  const [address, setAddress] = useState('')
  const [busy, setBusy] = useState(false)

  const load = useCallback(async () => {
    setData(await api.wallets().catch(() => EMPTY))
  }, [])

  useEffect(() => {
    let active = true
    api.wallets().catch(() => EMPTY).then((result) => { if (active) setData(result) })
    return () => { active = false }
  }, [])

  const add = async () => {
    setBusy(true)
    try {
      await api.addWallet(address)
      setAddress('')
      notify('success', 'Wallet added (watch-only)')
      await load()
    } catch (e) {
      notify('error', e instanceof ApiError ? e.message : 'Could not reach the server')
    } finally {
      setBusy(false)
    }
  }

  const remove = async (target: string) => {
    try {
      await api.removeWallet(target)
      await load()
    } catch (e) {
      notify('error', e instanceof ApiError ? e.message : 'Could not reach the server')
    }
  }

  return (
    <Card title={<>👛 Wallets <span className="muted small">watch-only</span></>}>
      <div className="callout good">
        <Icon name="safety" size={16} />
        <span>
          Paste a <strong>public</strong> address (starts with 0x). Augur only looks; it can never move coins.
          Never paste a private key or seed phrase anywhere: Augur will refuse it.
        </span>
      </div>

      <form className="row wallet-form" onSubmit={(e) => { e.preventDefault(); if (address.trim()) add() }}>
        <input
          className="input mono"
          placeholder="0x… public Ethereum address"
          value={address}
          onChange={(e) => setAddress(e.target.value)}
          spellCheck={false}
          autoComplete="off"
          aria-label="Public wallet address"
        />
        <button className="btn primary" disabled={!address.trim() || busy}>Watch</button>
      </form>

      {!data ? (
        <div className="skeleton" style={{ height: 60 }} />
      ) : data.wallets.length === 0 ? (
        <Empty title="No wallets yet">Add an address to see its ETH balance here.</Empty>
      ) : (
        <ul className="wallets">
          {data.wallets.map((w) => (
            <li key={w.address}>
              <span className="mono" title={w.address}>{short(w.address)}</span>
              {w.error ? (
                <Badge status="critical">Couldn't read</Badge>
              ) : (
                <span>
                  <span className="strong">{w.eth?.toFixed(4)} ETH</span>
                  {w.usd != null && <span className="muted"> ≈ {money(w.usd)}</span>}
                </span>
              )}
              <button className="icon-btn" aria-label={`Stop watching ${w.address}`} onClick={() => remove(w.address)}>
                <Icon name="close" size={16} />
              </button>
            </li>
          ))}
        </ul>
      )}
      {data?.rpc_host && <p className="muted small">Balances read from {data.rpc_host}.</p>}
    </Card>
  )
}
