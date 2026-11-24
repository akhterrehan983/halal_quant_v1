import { useEffect, useState } from 'react'
import { Activity, BarChart3, CircleDollarSign, ShieldCheck, Wallet } from 'lucide-react'
import { useApp } from '../context/AppContext'
import PageHeader from '../components/layout/PageHeader'
import MetricCard from '../components/common/MetricCard'
import StatusBadge from '../components/common/StatusBadge'
import { ShellError } from '../components/layout/MainLayout'
import { api } from '../lib/api'
import EquityCurve from '../components/charts/EquityCurve'
import { money } from '../utils/format'

export default function Portfolio() {
  const { horizon, setHorizon, error, setError } = useApp()
  const [book, setBook] = useState(null)
  const [proposals, setProposals] = useState([])
  const [holdings, setHoldings] = useState([])
  const [propMsg, setPropMsg] = useState('')
  const [perfHistory, setPerfHistory] = useState({ points: [] })
  const [drawdown, setDrawdown] = useState(null)
  const [snapMsg, setSnapMsg] = useState('')

  const loadPortfolio = async () => {
    try {
      const [b, p, h, perf, dd] = await Promise.all([
        api.bookSummary(),
        api.bookProposals(),
        api.bookHoldings(),
        api.valuationHistory({ limit: 180 }).catch(() => ({ points: [] })),
        api.portfolioDrawdown().catch(() => null),
      ])
      setBook(b)
      setProposals(p.items || [])
      setHoldings(h.holdings || h.items || [])
      setPerfHistory(perf)
      setDrawdown(dd)
    } catch (e) {
      setError(e.message)
    }
  }

  const recordSnapshot = async () => {
    try {
      setSnapMsg('')
      await api.recordValuationSnapshot({ trigger: 'on_demand' })
      setSnapMsg('Valuation snapshot recorded.')
      await loadPortfolio()
    } catch (e) {
      setSnapMsg(e.message)
    }
  }

  const runProposals = async () => {
    try {
      setPropMsg('')
      const r = await api.generateProposals(horizon, 12)
      setPropMsg(`Created ${r.count} allocation proposal(s).`)
      await loadPortfolio()
    } catch (e) {
      setPropMsg(e.message)
    }
  }

  useEffect(() => {
    loadPortfolio()
  }, [horizon])

  return (
  <>
    <ShellError error={error} onRetry={loadPortfolio} />
    <section className="panel signal-panel">
      <PageHeader eyebrow="PORTFOLIO" title="Research book & allocation proposals" chip="NOT EXECUTED ORDERS" />
      <div className="notice">
        <ShieldCheck size={17} />
        <span>Allocation proposals are not purchases. Use Paper Trading for simulated execution after screening.</span>
      </div>
      {book && (
        <section className="stats-grid">
          <MetricCard label="Portfolio value" value={money(book.portfolio_value)} sub={`Peak ${money(book.peak_value)}`} icon={CircleDollarSign} />
          <MetricCard label="Cash reserve" value={money(book.cash_reserve)} sub="Configurable sleeve reserve" icon={Wallet} />
          <MetricCard
            label="Open risk"
            value={money(book.open_risk)}
            sub={`Drawdown ${(Number(book.current_drawdown_pct || 0) * 100).toFixed(1)}%`}
            icon={Activity}
            tone={book.drawdown_locked ? '' : 'green'}
          />
          <MetricCard
            label="Unrealized P&L"
            value={money(book.unrealized_pnl)}
            sub={`Realized ${money(book.realized_pnl)}`}
            icon={BarChart3}
          />
          <MetricCard
            label="Invested (mkt)"
            value={money(book.market_value)}
            sub={`Max DD ${drawdown?.max_drawdown_pct ? (Number(drawdown.max_drawdown_pct) * 100).toFixed(1) : '—'}%`}
            icon={BarChart3}
          />
        </section>
      )}
      <div className="notice" style={{ marginTop: 12 }}>
        <span>
          Charts below use <b>recorded valuation snapshots</b> of the research book — not backtest engine results.
        </span>
        <button type="button" className="buy-btn" style={{ marginLeft: 12 }} onClick={recordSnapshot}>
          Record valuation snapshot
        </button>
        {snapMsg && <span className="muted small" style={{ marginLeft: 8 }}>{snapMsg}</span>}
      </div>
      {perfHistory.points?.length > 0 ? (
        <div className="md-grid" style={{ marginTop: 12 }}>
          <div className="md-card">
            <div className="eyebrow">EQUITY CURVE</div>
            <EquityCurve points={perfHistory.points.map(p => ({ date: p.date, equity: p.equity }))} />
          </div>
          <div className="md-card">
            <div className="eyebrow">DRAWDOWN (FROM SNAPSHOTS)</div>
            <EquityCurve
              points={perfHistory.points.map(p => ({ date: p.date, equity: Number(p.drawdown_pct) * 100 }))}
              dataKey="equity"
            />
          </div>
        </div>
      ) : (
        <p className="muted small" style={{ marginTop: 12 }}>
          No valuation history yet. Record a snapshot after market data and holdings are loaded.
        </p>
      )}
      <div className="md-grid">
        <div className="md-card">
          <label>Horizon for proposals</label>
          <select value={horizon} onChange={e => setHorizon(e.target.value)}>
            <option value="swing">Swing</option>
            <option value="positional">Positional</option>
          </select>
          <button type="button" className="buy-btn" style={{ marginTop: 10 }} onClick={runProposals}>
            Generate from active signals
          </button>
          {propMsg && <p className="muted small">{propMsg}</p>}
        </div>
        <div className="md-card">
          <div className="eyebrow">SLEEVES</div>
          {book && (
            <>
              <p>
                <b>Swing</b> cash {money(book.swing?.available_cash)} · invested {money(book.swing?.market_value)}
              </p>
              <p>
                <b>Positional</b> cash {money(book.positional?.available_cash)} · invested {money(book.positional?.market_value)}
              </p>
            </>
          )}
        </div>
      </div>
      <div className="table-scroll" style={{ marginTop: 16 }}>
        <table>
          <thead>
            <tr>
              <th>Symbol</th>
              <th>Qty</th>
              <th>Avg entry</th>
              <th>Mkt value</th>
              <th>Unrealized</th>
              <th>Ownership</th>
            </tr>
          </thead>
          <tbody>
            {holdings.map(h => (
              <tr key={`${h.symbol}-${h.sleeve}`}>
                <td>
                  <b>{h.symbol}</b> <span className="muted small">{h.sleeve}</span>
                </td>
                <td>{h.quantity}</td>
                <td>{money(h.average_entry ?? h.average_price)}</td>
                <td>{money(h.market_value)}</td>
                <td className="muted">—</td>
                <td>
                  <StatusBadge>{h.ownership_state || '—'}</StatusBadge>
                </td>
              </tr>
            ))}
            {holdings.length === 0 && (
              <tr>
                <td colSpan={6} className="muted">
                  No research holdings in the book yet.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      <h4>Allocation proposals</h4>
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th>Symbol</th>
              <th>Sleeve</th>
              <th>Qty</th>
              <th>Status</th>
              <th>Risk ₹</th>
              <th>Notes</th>
            </tr>
          </thead>
          <tbody>
            {proposals.map(p => (
              <tr key={p.proposal_id}>
                <td>
                  <b>{p.symbol}</b>
                </td>
                <td>{p.sleeve}</td>
                <td>{p.quantity}</td>
                <td>
                  <StatusBadge>{p.status}</StatusBadge>
                </td>
                <td>{money(p.risk_amount)}</td>
                <td className="muted small">{(p.rejections || []).join('; ') || (p.validations || []).join('; ')}</td>
              </tr>
            ))}
            {proposals.length === 0 && (
              <tr>
                <td colSpan={6} className="muted">
                  No proposals — generate signals then allocation proposals.
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