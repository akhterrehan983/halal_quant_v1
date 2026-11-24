import { useEffect, useState } from 'react'
import { RefreshCw, ShieldCheck } from 'lucide-react'
import { useApp } from '../context/AppContext'
import PageHeader from '../components/layout/PageHeader'
import StatusBadge from '../components/common/StatusBadge'
import { ShellError } from '../components/layout/MainLayout'
import { api } from '../lib/api'
import { pct } from '../utils/format'

export default function SignalCenter() {
  const { horizon, setHorizon, error, setError, setView } = useApp()
  const [regime, setRegime] = useState(null)
  const [regimeHist, setRegimeHist] = useState([])
  const [unifiedSignals, setUnifiedSignals] = useState([])
  const [selectedSignal, setSelectedSignal] = useState(null)
  const [sigCategory, setSigCategory] = useState('')
  const [sigLifecycle, setSigLifecycle] = useState('')
  const [sigFilterSymbol, setSigFilterSymbol] = useState('')
  const [sigGenMsg, setSigGenMsg] = useState('')

  const loadSignalCenter = async () => {
    try {
      setSigGenMsg('')
      const [r, h, sigs] = await Promise.all([
        api.regimeCurrent(),
        api.regimeHistory(40),
        api.unifiedSignals({
          horizon,
          symbol: sigFilterSymbol || undefined,
          category: sigCategory || undefined,
          lifecycle: sigLifecycle || undefined,
        }),
      ])
      setRegime(r)
      setRegimeHist(h.history || [])
      setUnifiedSignals(sigs.items || [])
    } catch (e) {
      setError(e.message)
    }
  }

  const runSignalGenerate = async () => {
    try {
      setSigGenMsg('')
      const r = await api.generateSignals({ horizon, persist: true })
      setSigGenMsg(`Generated ${r.count} research signal(s).`)
      await loadSignalCenter()
    } catch (e) {
      setSigGenMsg(e.message)
    }
  }

  const openSignal = async id => {
    try {
      setSelectedSignal(await api.signalById(id))
    } catch (e) {
      setError(e.message)
    }
  }

  useEffect(() => {
    loadSignalCenter()
  }, [horizon, sigCategory, sigLifecycle, sigFilterSymbol])

  return (
  <>
    <ShellError error={error} onRetry={loadSignalCenter} />
    <section className="panel signal-panel">
      <PageHeader eyebrow="SIGNAL CENTER" title="Unified research signals · not orders" chip="RESEARCH ONLY" />
      <div className="notice">
        <ShieldCheck size={17} />
        <span>Scores are heuristic research labels, not profit probabilities. High scores do not bypass future Shariah, risk, or portfolio gates.</span>
      </div>
      <div className="md-grid">
        <div className="md-card">
          <label>Horizon</label>
          <select value={horizon} onChange={e => setHorizon(e.target.value)}>
            <option value="swing">Swing</option>
            <option value="positional">Positional</option>
          </select>
          <label>Symbol filter</label>
          <input placeholder="All symbols" value={sigFilterSymbol} onChange={e => setSigFilterSymbol(e.target.value.toUpperCase())} />
          <label>Category</label>
          <select value={sigCategory} onChange={e => setSigCategory(e.target.value)}>
            <option value="">All</option>
            <option value="STRONG_BUY">Strong buy</option>
            <option value="BUY">Buy</option>
            <option value="WATCHLIST">Watchlist</option>
            <option value="NO_ACTION">No action</option>
          </select>
          <label>Lifecycle</label>
          <select value={sigLifecycle} onChange={e => setSigLifecycle(e.target.value)}>
            <option value="">All</option>
            <option value="ACTIVE">Active</option>
            <option value="CREATED">Created</option>
            <option value="EXPIRED">Expired</option>
            <option value="SUPERSEDED">Superseded</option>
          </select>
          <div className="trade-buttons">
            <button type="button" className="buy-btn" onClick={runSignalGenerate}>
              Generate universe
            </button>
            <button type="button" className="icon-btn" onClick={loadSignalCenter} title="Refresh">
              <RefreshCw size={16} />
            </button>
          </div>
          {sigGenMsg && <p className="muted small">{sigGenMsg}</p>}
        </div>
        <div className="md-card">
          <div className="eyebrow">BENCHMARK REGIME</div>
          {regime ? (
            <>
              <StatusBadge>{regime.regime}</StatusBadge>
              <p className="muted small">
                Confidence {pct(regime.confidence * 100)} · as of {regime.as_of_date} · {regime.benchmark_symbol}
              </p>
              <pre className="md-pre">{JSON.stringify(regime.factors, null, 2)}</pre>
            </>
          ) : (
            <p className="muted">Loading regime…</p>
          )}
          {regimeHist.length > 0 && (
            <table>
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Regime</th>
                </tr>
              </thead>
              <tbody>
                {regimeHist.slice(-8).map((row, i) => (
                  <tr key={i}>
                    <td>{row.as_of_date}</td>
                    <td>
                      <StatusBadge>{row.regime}</StatusBadge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
      <div className="table-scroll" style={{ marginTop: 16 }}>
        <table>
          <thead>
            <tr>
              <th>ID</th>
              <th>Symbol</th>
              <th>Score</th>
              <th>Category</th>
              <th>Regime</th>
              <th>Consensus</th>
              <th>Lifecycle</th>
            </tr>
          </thead>
          <tbody>
            {unifiedSignals.map(s => (
              <tr
                key={s.signal_id || `${s.symbol}-${s.evaluation_date}`}
                className="click-row"
                onClick={() => s.signal_id && openSignal(s.signal_id)}
              >
                <td>{s.signal_id ?? '—'}</td>
                <td>
                  <b>{s.symbol}</b>
                </td>
                <td>
                  <b>{s.overall_score}</b>
                </td>
                <td>
                  <StatusBadge>{s.category}</StatusBadge>
                </td>
                <td>{s.market_regime}</td>
                <td>
                  {s.consensus_effective_buys} ({s.agreement_level})
                </td>
                <td>{s.lifecycle_state}</td>
              </tr>
            ))}
            {unifiedSignals.length === 0 && (
              <tr>
                <td colSpan={7} className="muted">
                  No persisted signals — run Generate universe.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      {selectedSignal && (
        <div className="md-card" style={{ marginTop: 16 }}>
          <div className="panel-head">
            <div>
              <div className="eyebrow">SIGNAL DETAIL</div>
              <h3>
                {selectedSignal.symbol} · {selectedSignal.category}
              </h3>
            </div>
            <button type="button" className="icon-btn" onClick={() => setSelectedSignal(null)}>
              Close
            </button>
          </div>
          <p>
            Overall score <b>{selectedSignal.overall_score}</b> · lifecycle {selectedSignal.lifecycle_state}
          </p>
          <pre className="md-pre">{JSON.stringify(selectedSignal.score_breakdown, null, 2)}</pre>
          <h4>Strategy contributions</h4>
          <div className="strategy-grid">
            {selectedSignal.strategy_results?.map(sr => (
              <div key={sr.strategy_id || sr.strategy} className="strategy-card">
                <b>{sr.strategy_name || sr.strategy}</b> <StatusBadge>{sr.legacy_signal || sr.direction}</StatusBadge>
                <p className="muted small">{sr.rationale}</p>
              </div>
            ))}
          </div>
          <button type="button" className="buy-btn" style={{ marginTop: 12 }} onClick={() => setView('portfolio')}>
            View allocation proposals
          </button>
        </div>
      )}
    </section>
  </>
  )
}