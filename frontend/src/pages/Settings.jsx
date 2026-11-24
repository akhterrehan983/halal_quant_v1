import { useEffect, useState } from 'react'
import PageHeader from '../components/layout/PageHeader'
import { ShellError } from '../components/layout/MainLayout'
import { api } from '../lib/api'
import { useApp } from '../context/AppContext'

export default function Settings() {
  const { error, setError } = useApp()
  const [riskCfg, setRiskCfg] = useState(null)
  const [strategies, setStrategies] = useState([])
  const [msg, setMsg] = useState('')
  const dbPersist = true

  const load = async () => {
    try {
      const [r, s] = await Promise.all([api.riskConfig(), api.strategies()])
      setRiskCfg(r)
      setStrategies(s.items || [])
    } catch (e) {
      setError(e.message)
    }
  }

  useEffect(() => {
    load()
  }, [])

  const saveSwingReserve = async () => {
    if (!riskCfg) return
    try {
      setMsg('')
      await api.patchRiskConfig({ cash_reserve_pct: riskCfg.cash_reserve_pct })
      setMsg('Risk configuration updated (persisted when PostgreSQL is enabled).')
      await load()
    } catch (e) {
      setMsg(e.message)
    }
  }

  return (
  <>
    <ShellError error={error} onRetry={load} />
    <section className="panel signal-panel">
      <PageHeader eyebrow="SETTINGS" title="System parameters" chip={dbPersist ? 'Backend validated' : 'In-memory only'} />
      <p className="muted small">Changes use PATCH /api/v1/risk/config and strategy toggle endpoints. Without DATABASE_URL, settings reset on restart.</p>
      {msg && <p className="muted small">{msg}</p>}
      <div className="md-grid">
        <div className="md-card">
          <div className="eyebrow">RISK CONFIGURATION</div>
          {riskCfg && (
            <>
              <label>Cash reserve %</label>
              <input
                type="number"
                step="0.01"
                min="0"
                max="1"
                value={riskCfg.cash_reserve_pct ?? 0.1}
                onChange={e => setRiskCfg({ ...riskCfg, cash_reserve_pct: Number(e.target.value) })}
              />
              <button type="button" className="buy-btn" style={{ marginTop: 10 }} onClick={saveSwingReserve}>
                Save cash reserve
              </button>
              <pre className="md-pre">{JSON.stringify(riskCfg, null, 2)}</pre>
            </>
          )}
        </div>
        <div className="md-card">
          <div className="eyebrow">STRATEGIES</div>
          {strategies.map(s => (
            <label key={s.id} className="toggle-row" style={{ display: 'block', marginBottom: 8 }}>
              <input
                type="checkbox"
                checked={s.enabled}
                onChange={async e => {
                  try {
                    await api.strategyToggle(s.id, e.target.checked)
                    await load()
                  } catch (err) {
                    setError(err.message)
                  }
                }}
              />{' '}
              {s.name}
            </label>
          ))}
        </div>
      </div>
    </section>
  </>
  )
}