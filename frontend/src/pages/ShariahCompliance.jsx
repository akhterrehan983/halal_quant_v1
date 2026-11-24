import { useEffect, useState } from 'react'
import { ShieldCheck } from 'lucide-react'
import { useApp } from '../context/AppContext'
import PageHeader from '../components/layout/PageHeader'
import StatusBadge from '../components/common/StatusBadge'
import { ShellError } from '../components/layout/MainLayout'
import { api } from '../lib/api'

export default function ShariahCompliance() {
  const { symbol, setSymbol, universe, error, setError } = useApp()
  const [shariahRec, setShariahRec] = useState(null)
  const [standards, setStandards] = useState([])
  const [snapshots, setSnapshots] = useState([])
  const [finJson, setFinJson] = useState(
    '{"data_source":"user_supplied","reporting_period":"FY2025","interest_bearing_debt":1000,"market_capitalization":100000,"non_compliant_income":100,"revenue":50000}'
  )

  const loadShariah = async () => {
    try {
      setShariahRec(await api.shariahScreening(symbol).catch(() => null))
      setSnapshots(await api.shariahSnapshots(symbol).catch(() => ({ items: [] })))
    } catch {
      setShariahRec(null)
    }
  }

  useEffect(() => {
    api.shariahStandards().then(r => setStandards(r.items || r.standards || [])).catch(() => {})
    loadShariah()
  }, [symbol])

  const runShariahEval = async () => {
    try {
      const body = {
        financials: JSON.parse(finJson),
        business_activity: [
          { category: 'it_services', prohibited: false, source: 'user_form', verified_at: new Date().toISOString().slice(0, 10) },
        ],
      }
      setShariahRec(await api.shariahEvaluate(symbol, body))
      await loadShariah()
    } catch (e) {
      setError(e.message)
    }
  }

  const snapItems = snapshots?.items || snapshots?.snapshots || []

  return (
  <>
    <ShellError error={error} />
    <section className="panel signal-panel">
      <PageHeader eyebrow="SHARIAH COMPLIANCE" title="User-supplied screening · not a fatwa" chip="Templates ≠ certification" />
      <div className="notice">
        <ShieldCheck size={17} />
        <span>Provide your own financial and activity data. Missing data yields INSUFFICIENT_DATA / NEEDS_REVIEW — not halal by default.</span>
      </div>
      {standards.length > 0 && (
        <p className="muted small">
          Profiles loaded: {standards.map(s => s.name || s.profile_name).join(', ')} (demo templates unless verified provider data exists).
        </p>
      )}
      <div className="md-grid">
        <div className="md-card">
          <label>Symbol</label>
          <select value={symbol} onChange={e => setSymbol(e.target.value)}>
            {universe.map(s => (
              <option key={s.symbol} value={s.symbol}>
                {s.symbol}
              </option>
            ))}
          </select>
          <label>Financial inputs (JSON)</label>
          <textarea rows={6} value={finJson} onChange={e => setFinJson(e.target.value)} style={{ width: '100%' }} />
          <button type="button" className="buy-btn" onClick={runShariahEval}>
            Evaluate screening
          </button>
        </div>
        <div className="md-card">
          {shariahRec ? (
            <>
              <StatusBadge>{shariahRec.status}</StatusBadge>
              <p className="muted small">{shariahRec.explanation}</p>
              <pre className="md-pre">{JSON.stringify({ ratios: shariahRec.ratios, activity: shariahRec.business_activity }, null, 2)}</pre>
            </>
          ) : (
            <p className="muted">No screening yet.</p>
          )}
        </div>
      </div>
      {snapItems.length > 0 && (
        <>
          <h4>Historical snapshots</h4>
          <pre className="md-pre">{JSON.stringify(snapItems.slice(0, 5), null, 2)}</pre>
        </>
      )}
    </section>
  </>
  )
}