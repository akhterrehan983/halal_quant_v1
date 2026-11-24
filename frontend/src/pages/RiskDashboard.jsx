import { useEffect, useState } from 'react'
import { Activity, ShieldCheck } from 'lucide-react'
import PageHeader from '../components/layout/PageHeader'
import MetricCard from '../components/common/MetricCard'
import StatusBadge from '../components/common/StatusBadge'
import { ShellError } from '../components/layout/MainLayout'
import { api } from '../lib/api'
import { money } from '../utils/format'
import { useApp } from '../context/AppContext'

export default function RiskDashboard() {
  const { error, setError } = useApp()
  const [book, setBook] = useState(null)
  const [limits, setLimits] = useState(null)
  const [exposure, setExposure] = useState(null)
  const [events, setEvents] = useState([])

  const load = async () => {
    try {
      const [b, l, e, ev] = await Promise.all([api.bookSummary(), api.riskLimits(), api.riskExposure(), api.riskEvents()])
      setBook(b)
      setLimits(l)
      setExposure(e)
      setEvents(ev.items || ev.events || [])
    } catch (err) {
      setError(err.message)
    }
  }

  useEffect(() => {
    load()
  }, [])

  return (
  <>
    <ShellError error={error} onRetry={load} />
    <section className="panel signal-panel">
      <PageHeader eyebrow="RISK DASHBOARD" title="Exposure & limit monitoring" chip="Server-enforced limits" />
      <div className="notice">
        <ShieldCheck size={17} />
        <span>Risk configuration changes belong in Settings and are validated on the server. The UI cannot bypass limits.</span>
      </div>
      {book && (
        <section className="stats-grid">
          <MetricCard label="Current equity" value={money(book.portfolio_value)} sub={`Peak ${money(book.peak_value)}`} icon={Activity} />
          <MetricCard
            label="Drawdown"
            value={`${(Number(book.current_drawdown_pct || 0) * 100).toFixed(2)}%`}
            sub={book.drawdown_locked ? 'Drawdown lock active' : 'Within policy'}
            icon={Activity}
          />
          <MetricCard label="Open risk" value={money(book.open_risk)} sub="Aggregate open risk budget" icon={Activity} />
          <MetricCard label="Cash reserve" value={money(book.cash_reserve)} sub="Mandatory reserve sleeve" icon={Activity} />
        </section>
      )}
      <div className="md-grid">
        <div className="md-card">
          <div className="eyebrow">LIMITS (SWING)</div>
          {limits?.swing && <pre className="md-pre">{JSON.stringify(limits.swing, null, 2)}</pre>}
          <div className="eyebrow" style={{ marginTop: 12 }}>
            LIMITS (POSITIONAL)
          </div>
          {limits?.positional && <pre className="md-pre">{JSON.stringify(limits.positional, null, 2)}</pre>}
        </div>
        <div className="md-card">
          <div className="eyebrow">CURRENT EXPOSURE</div>
          {exposure ? <pre className="md-pre">{JSON.stringify(exposure, null, 2)}</pre> : <p className="muted">Unavailable</p>}
        </div>
      </div>
      <h4>Risk events</h4>
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th>Type</th>
              <th>Symbol</th>
              <th>Severity</th>
              <th>Limit</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {events.map((ev, i) => (
              <tr key={ev.event_id || i}>
                <td>{ev.event_type}</td>
                <td>{ev.symbol || '—'}</td>
                <td>
                  <StatusBadge>{ev.severity}</StatusBadge>
                </td>
                <td className="muted small">{ev.violated_limit || ev.limit_name || '—'}</td>
                <td>{ev.resolution_status || ev.status || '—'}</td>
              </tr>
            ))}
            {events.length === 0 && (
              <tr>
                <td colSpan={5} className="muted">
                  No risk events recorded.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  </>
  )
}