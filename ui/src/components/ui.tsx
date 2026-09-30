import { useEffect, useRef } from 'react'
import type { ReactNode } from 'react'
import type { Toast } from '../hooks/useToasts'

// ---------------------------------------------------------------------------
// Icons: inline 20px strokes so they inherit text color.
// ---------------------------------------------------------------------------

const paths = {
  overview: 'M3 13h8V3H3v10zm0 8h8v-6H3v6zm10 0h8V11h-8v10zm0-18v6h8V3h-8z',
  positions: 'M4 19V9m6 10V5m6 14v-7m4 7H2',
  markets: 'M3 17l6-6 4 4 8-8m0 0h-5m5 0v5',
  trades: 'M7 7h13l-3-3M17 17H4l3 3',
  assistant: 'M21 12a8 8 0 0 1-11.9 7L3 21l2-6A8 8 0 1 1 21 12z',
  integrations: 'M9 7V3m6 4V3M7 7h10v5a5 5 0 0 1-10 0V7zm5 10v4',
  safety: 'M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6l8-3z',
  sun: 'M12 4V2m0 20v-2m8-8h2M2 12h2m13.7-5.7l1.4-1.4M4.9 19.1l1.4-1.4m0-11.4L4.9 4.9m14.2 14.2l-1.4-1.4M12 17a5 5 0 1 0 0-10 5 5 0 0 0 0 10z',
  moon: 'M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z',
  check: 'M5 12l5 5L20 7',
  alert: 'M12 9v4m0 4h.01M10.3 3.9L2 18a2 2 0 0 0 1.7 3h16.6a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z',
  info: 'M12 16v-4m0-4h.01M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20z',
  close: 'M18 6L6 18M6 6l12 12',
  external: 'M14 4h6v6m0-6L10 14M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5',
  eye: 'M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12zm10 3a3 3 0 1 0 0-6 3 3 0 0 0 0 6z',
  up: 'M12 19V5m-6 6l6-6 6 6',
  down: 'M12 5v14m6-6l-6 6-6-6',
  send: 'M22 2L11 13M22 2l-7 20-4-9-9-4 20-7z',
  power: 'M12 2v10m6.4-6.4a9 9 0 1 1-12.8 0',
  refresh: 'M21 12a9 9 0 1 1-3-6.7L21 8m0-5v5h-5',
} as const

export type IconName = keyof typeof paths

export function Icon({ name, size = 20 }: { name: IconName; size?: number }) {
  return (
    <svg className="icon" width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d={paths[name]} />
    </svg>
  )
}

// ---------------------------------------------------------------------------
// Figures
// ---------------------------------------------------------------------------

export function StatTile({ label, value, delta, deltaTone, hint }: {
  label: string
  value: ReactNode
  delta?: string
  deltaTone?: 'up' | 'down' | 'flat'
  hint?: string
}) {
  return (
    <div className="tile">
      <div className="tile-label">{label}</div>
      <div className="tile-value">{value}</div>
      {delta && (
        <div className={`tile-delta ${deltaTone ?? 'flat'}`}>
          {deltaTone === 'up' && <Icon name="up" size={14} />}
          {deltaTone === 'down' && <Icon name="down" size={14} />}
          {delta}
        </div>
      )}
      {hint && <div className="tile-hint">{hint}</div>}
    </div>
  )
}

/** Status is always icon + label, never color alone. */
export function Badge({ status, children }: { status: 'good' | 'warning' | 'critical' | 'neutral'; children: ReactNode }) {
  const icon: IconName = status === 'good' ? 'check' : status === 'neutral' ? 'info' : 'alert'
  return (
    <span className={`badge ${status}`}>
      <Icon name={icon} size={14} />
      {children}
    </span>
  )
}

export function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="empty">
      <div className="empty-title">{title}</div>
      {children && <div className="empty-body">{children}</div>}
    </div>
  )
}

export function Card({ title, action, children, className = '' }: {
  title?: ReactNode
  action?: ReactNode
  children: ReactNode
  className?: string
}) {
  return (
    <section className={`card ${className}`}>
      {(title || action) && (
        <header className="card-head">
          {title && <h2>{title}</h2>}
          {action}
        </header>
      )}
      {children}
    </section>
  )
}

// ---------------------------------------------------------------------------
// Confirm dialog (native <dialog>: focus trap and Esc for free)
// ---------------------------------------------------------------------------

export function ConfirmDialog({ open, title, body, confirmLabel, danger, onConfirm, onCancel }: {
  open: boolean
  title: string
  body: ReactNode
  confirmLabel: string
  danger?: boolean
  onConfirm: () => void
  onCancel: () => void
}) {
  const ref = useRef<HTMLDialogElement>(null)
  useEffect(() => {
    const dialog = ref.current
    if (!dialog) return
    if (open && !dialog.open) dialog.showModal()
    if (!open && dialog.open) dialog.close()
  }, [open])

  return (
    <dialog ref={ref} className="dialog" onCancel={(e) => { e.preventDefault(); onCancel() }}>
      <h3>{title}</h3>
      <div className="dialog-body">{body}</div>
      <div className="dialog-actions">
        <button className="btn ghost" onClick={onCancel}>Cancel</button>
        <button className={`btn ${danger ? 'danger' : 'primary'}`} onClick={onConfirm} autoFocus>
          {confirmLabel}
        </button>
      </div>
    </dialog>
  )
}

export function Toasts({ toasts, onDismiss }: { toasts: Toast[]; onDismiss: (id: number) => void }) {
  return (
    <div className="toasts" role="status" aria-live="polite">
      {toasts.map((t) => (
        <div key={t.id} className={`toast ${t.kind}`}>
          <Icon name={t.kind === 'success' ? 'check' : t.kind === 'error' ? 'alert' : 'info'} size={16} />
          <span>{t.message}</span>
          <button className="icon-btn" aria-label="Dismiss" onClick={() => onDismiss(t.id)}>
            <Icon name="close" size={14} />
          </button>
        </div>
      ))}
    </div>
  )
}
