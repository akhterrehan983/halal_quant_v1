import { useEffect, useState } from 'react'
import { Activity, BarChart3, CircleDollarSign, ShieldCheck, Wallet } from 'lucide-react'
import { useApp } from '../context/AppContext'
import PageHeader from '../components/layout/PageHeader'
import MetricCard from '../components/common/MetricCard'
import EquityCurve from '../components/charts/EquityCurve'
import { ShellError } from '../components/layout/MainLayout'
import { api } from '../lib/api'
import { money, pct } from '../utils/format'

export default function BacktestingLab() {
  const { horizon, error, setError } = useApp()
  const [btResult, setBtResult] = useState(null)
  const [btMsg, setBtMsg] = useState('')
  const [list, setList] = useState([])

  const runBacktest = async () => {
    try {
      setBtMsg('Running…')
      const end = new Date()
      end.setDate(end.getDate() - 10)
      const start = new Date(end)
      start.setDate(start.getDate() - 60)
      const r = await api.createBacktest(
        {
          name: `lab_${horizon}`,
          start_date: start.toISOString().slice(0, 10),
          end_date: end.toISOString().slice(0, 10),
          horizon,
          shariah_mode: 'RESEARCH_ONLY',
          strategies: ['unified'],
        },
        true
      )
      setBtResult(r)
      setBtMsg(`Completed ${r.metrics?.total_trades ?? 0} trades`)
      api.backtests().then(b => setList(b.items || b.backtests || []))
    } catch (e) {
      setBtMsg(e.message)
      setError(e.message)
    }
  }

  useEffect(() => {
    api.backtests()
      .then(b => setList(b.items || b.backtests || []))
      .catch(() => {})
    if (!btResult) runBacktest()
  }, [])

  const equity =
    btResult?.equity_curve?.map(p => ({
      date: p.date,
      equity: Number(p.equity),
    })) || []

  return (
  <>
    <ShellError error={error} />
    <section className="panel signal-panel">
      <PageHeader eyebrow="BACKTESTING LAB" title="Historical simulation · not a forecast" />
      <div className="notice">
        <ShieldCheck size={17} />
        <span>Demo universe has survivorship limitations. Use RESEARCH_ONLY Shariah mode unless point-in-time snapshots exist.</span>
      </div>
      <button type="button" className="buy-btn" onClick={runBacktest}>
        Run demo backtest ({horizon})
      </button>
      {btMsg && <p className="muted small">{btMsg}</p>}
      {btResult?.metrics && (
        <section className="stats-grid">
          <MetricCard label="Total return" value={pct(Number(btResult.metrics.total_return) * 100)} sub={`Max DD ${(Number(btResult.metrics.max_drawdown) * 100).toFixed(1)}%`} icon={Activity} />
          <MetricCard label="Trades" value={btResult.metrics.total_trades} sub={`Win rate ${btResult.metrics.win_rate ? (Number(btResult.metrics.win_rate) * 100).toFixed(0) + '%' : '—'}`} icon={BarChart3} />
          <MetricCard label="Sharpe" value={btResult.metrics.sharpe ?? '—'} sub="When computed by engine" icon={CircleDollarSign} />
          <MetricCard label="Costs" value={money(btResult.metrics.transaction_costs)} sub="Scenario configured" icon={Wallet} />
        </section>
      )}
      {btResult?.validation && <pre className="md-pre">{JSON.stringify(btResult.validation, null, 2)}</pre>}
      <EquityCurve points={equity} />
      {list.length > 0 && (
        <>
          <h4>Past runs</h4>
          <pre className="md-pre">{JSON.stringify(list.slice(0, 5), null, 2)}</pre>
        </>
      )}
    </section>
  </>
  )
}