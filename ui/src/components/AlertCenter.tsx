import React, { useState } from 'react'
import { Alert } from '../App'
import './AlertCenter.css'

interface Props {
  alerts: Alert[]
}

export const AlertCenter: React.FC<Props> = ({ alerts }) => {
  const [dismissed, setDismissed] = useState<Set<string>>(new Set())

  const visibleAlerts = alerts.filter((_, idx) => !dismissed.has(idx.toString()))

  const dismissAlert = (idx: number) => {
    setDismissed((prev) => new Set([...prev, idx.toString()]))
  }

  const getSeverityIcon = (severity: string) => {
    switch (severity) {
      case 'CRITICAL':
        return '🚨'
      case 'WARNING':
        return '⚠️'
      case 'INFO':
        return 'ℹ️'
      default:
        return '📌'
    }
  }

  const getAlertTypeLabel = (type: string) => {
    switch (type) {
      case 'NEWS':
        return '📰 News'
      case 'POSITION_ALERT':
        return '📍 Position'
      case 'RISK_WARNING':
        return '⚠️ Risk'
      case 'EXECUTION_FAILURE':
        return '❌ Execution'
      default:
        return '📌 Alert'
    }
  }

  return (
    <div className="alert-center">
      <h3>Alerts & Notifications</h3>

      {visibleAlerts.length === 0 ? (
        <p className="empty-state">No alerts</p>
      ) : (
        <div className="alerts-list">
          {visibleAlerts.map((alert, idx) => (
            <div key={idx} className={`alert alert-${alert.severity.toLowerCase()}`}>
              <div className="alert-header">
                <span className="alert-type">{getAlertTypeLabel(alert.alert_type)}</span>
                {alert.symbol && <span className="alert-symbol">{alert.symbol}</span>}
                <time className="alert-time">
                  {new Date(alert.timestamp).toLocaleTimeString()}
                </time>
              </div>
              <p className="alert-message">{alert.message}</p>
              <button
                className="btn-dismiss"
                onClick={() => dismissAlert(idx)}
                title="Dismiss alert"
              >
                ✕
              </button>
            </div>
          ))}
        </div>
      )}

      <div className="alert-stats">
        <span>
          Total: <strong>{alerts.length}</strong>
        </span>
        <span>
          Critical:{' '}
          <strong>{alerts.filter((a) => a.severity === 'CRITICAL').length}</strong>
        </span>
        <span>
          Warnings:{' '}
          <strong>{alerts.filter((a) => a.severity === 'WARNING').length}</strong>
        </span>
      </div>
    </div>
  )
}
