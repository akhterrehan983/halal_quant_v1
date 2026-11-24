import { useEffect, useState } from 'react'
import { useApp } from '../context/AppContext'
import PageHeader from '../components/layout/PageHeader'
import StatusBadge from '../components/common/StatusBadge'
import { ShellError } from '../components/layout/MainLayout'
import { api } from '../lib/api'

export default function StrategyExplorer() {
  const { symbol, setSymbol, horizon, setHorizon, universe, error, setError } = useApp()
  const [strategyList, setStrategyList] = useState([])
  const [activeStrategy, setActiveStrategy] = useState('momentum')
  const [strategyEval, setStrategyEval] = useState(null)

  useEffect(() => {
    api.strategies()
      .then(r => setStrategyList(r.items || []))
      .catch(e => setError(e.message))
  }, [setError])

  const toggleStrategy = async (id, enabled) => {
    try {
      await api.strategyToggle(id, enabled)
      const r = await api.strategies()
      setStrategyList(r.items || [])
    } catch (e) {
      setError(e.message)
    }
  }

  const runStrategyEval = async (id = activeStrategy) => {
    try {
      setActiveStrategy(id)
      setStrategyEval(await api.strategyEvaluate(id, symbol, horizon))
    } catch (e) {
      setStrategyEval({ error: e.message })
    }
  }

  return (
  <>
    <ShellError error={error} />
    <section className="panel strategy-panel">
      <PageHeader eyebrow="STRATEGY EXPLORER" title="Modular rule engines · not executed trades" chip="RESEARCH CANDIDATES ONLY" />
      <div className="md-grid">
        <div className="md-card">
          {strategyList.map(s => (
            <div key={s.id} className="strat-row">
              <div>
                <b>{s.name}</b>
                <p className="muted small">{s.description}</p>
              </div>
              <label className="toggle-row">
                <input type="checkbox" checked={s.enabled} onChange={e => toggleStrategy(s.id, e.target.checked)} /> Enabled
              </label>
              <button type="button" className="icon-btn" onClick={() => runStrategyEval(s.id)} title="Evaluate">
                Run
              </button>
            </div>
          ))}
        </div>
        <div className="md-card">
          <label>Active strategy</label>
          <select value={activeStrategy} onChange={e => setActiveStrategy(e.target.value)}>
            {strategyList.map(s => (
              <option value={s.id} key={s.id}>
                {s.name}
              </option>
            ))}
          </select>
          <div className="selectors" style={{ marginTop: 10 }}>
            <select value={symbol} onChange={e => setSymbol(e.target.value)}>
              {universe.map(s => (
                <option key={s.symbol} value={s.symbol}>
                  {s.symbol}
                </option>
              ))}
            </select>
            <select value={horizon} onChange={e => setHorizon(e.target.value)}>
              <option value="swing">Swing</option>
              <option value="positional">Positional</option>
            </select>
          </div>
          <button type="button" className="buy-btn" style={{ marginTop: 12 }} onClick={() => runStrategyEval()}>
            Evaluate for {symbol}
          </button>
          {strategyEval && !strategyEval.error && (
            <div className="md-meta">
              <p>
                <StatusBadge>{strategyEval.legacy_signal}</StatusBadge> Score {strategyEval.score}/100 · {strategyEval.direction}
              </p>
              <p>{strategyEval.rationale}</p>
              <p className="muted small">Conditions: {(strategyEval.conditions_met || []).join('; ')}</p>
              {strategyEval.rejection_reasons?.length > 0 && (
                <p className="muted small">Rejections: {strategyEval.rejection_reasons.join('; ')}</p>
              )}
              <pre className="md-pre">{JSON.stringify(strategyEval.features_used, null, 2)}</pre>
            </div>
          )}
          {strategyEval?.error && <div className="error">{strategyEval.error}</div>}
        </div>
      </div>
    </section>
  </>
  )
}