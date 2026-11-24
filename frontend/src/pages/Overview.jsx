import { useEffect, useMemo, useState } from 'react'
import { Activity, BarChart3, CircleDollarSign, ShieldCheck, Wallet } from 'lucide-react'
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { useApp } from '../context/AppContext'
import MetricCard from '../components/common/MetricCard'
import StatusBadge from '../components/common/StatusBadge'
import { ShellError } from '../components/layout/MainLayout'
import { api } from '../lib/api'
import EquityCurve from '../components/charts/EquityCurve'
import { money, pct } from '../utils/format'

export default function Overview() {
  const {
    symbol,
    setSymbol,
    horizon,
    setHorizon,
    universe,
    scan,
    detail,
    history,
    loading,
    error,
    loadAll,
    setError,
    setView,
  } = useApp()

  const [regime, setRegime] = useState(null)
  const [book, setBook] = useState(null)
  const [holdings, setHoldings] = useState([])
  const [sigSummary, setSigSummary] = useState({ buy: 0, strong: 0, watch: 0 })
  const [perfHistory, setPerfHistory] = useState({ points: [] })

  useEffect(() => {
    const loadDashboard = async () => {
      try {
        const [r, b, sigs, h, perf] = await Promise.all([
          api.regimeCurrent().catch(() => null),
          api.bookSummary().catch(() => null),
          api.unifiedSignals({ horizon, lifecycle: 'ACTIVE' }).catch(() => ({ items: [] })),
          api.bookHoldings().catch(() => ({ holdings: [] })),
          api.valuationHistory({ limit: 90 }).catch(() => ({ points: [] })),
        ])
        setRegime(r)
        setBook(b)
        setHoldings(h.holdings || [])
        setPerfHistory(perf)
        const items = sigs.items || []
        setSigSummary({
          buy: items.filter(s => s.category === 'BUY').length,
          strong: items.filter(s => s.category === 'STRONG_BUY').length,
          watch: items.filter(s => s.category === 'WATCHLIST').length,
        })
      } catch (e) {
        setError(e.message)
      }
    }
    loadDashboard()
  }, [horizon, setError])

  const latest = detail?.features
  const sortedStrategies = useMemo(() => detail?.strategies || [], [detail])

  return (
  <>
    <ShellError error={error} onRetry={loadAll} />
    <section className="hero">
      <div>
        <div className="eyebrow light">HALAL QUANT · V1 RESEARCH BUILD</div>
        <h2>
          Find the signal.
          <br />
          <em>Respect the process.</em>
        </h2>
        <p>One research workspace for swing and positional strategies, portfolio risk and Shariah-aware trading controls.</p>
        <div className="hero-tags">
          <span>SWING · 2–15 DAYS</span>
          <span>POSITIONAL · 15–120 DAYS</span>
          <span>LONG ONLY</span>
        </div>
      </div>
      <div className="hero-art">
        <div className="orb orb1" />
        <div className="orb orb2" />
        <div className="hero-chart">
          <div className="chart-label">STRATEGY SIGNAL FLOW</div>
          <svg viewBox="0 0 330 150" role="img" aria-label="Illustrative rising price line">
            <path
              d="M5 120 L35 105 L55 112 L82 75 L108 90 L132 60 L158 68 L190 32 L214 52 L245 22 L272 35 L320 8"
              fill="none"
              stroke="#72e0c0"
              strokeWidth="3"
              strokeLinecap="round"
            />
          </svg>
          <div className="chart-foot">
            <span>DATA → FEATURES → SIGNAL</span>
            <span>DAILY</span>
          </div>
        </div>
      </div>
    </section>
    <div className="notice">
      <ShieldCheck size={17} />
      <span>
        <b>Research prototype:</b> demo prices are synthetic. Shariah status is unverified. Signals are educational and do not constitute investment advice.
      </span>
    </div>
    <section className="stats-grid">
      <MetricCard
        label="Market regime"
        value={regime?.regime || latest?.regime || '—'}
        sub={regime ? `Confidence ${pct((regime.confidence || 0) * 100)}` : 'Regime unavailable'}
        icon={Activity}
        tone="green"
      />
      <MetricCard
        label="Research book equity"
        value={book ? money(book.portfolio_value) : '—'}
        sub={book ? `Drawdown ${(Number(book.current_drawdown_pct || 0) * 100).toFixed(1)}%` : 'Book summary unavailable'}
        icon={CircleDollarSign}
      />
      <MetricCard
        label="Active signals"
        value={sigSummary.buy + sigSummary.strong}
        sub={`Strong ${sigSummary.strong} · Watch ${sigSummary.watch}`}
        icon={BarChart3}
      />
      <MetricCard
        label="Available cash"
        value={book ? money(book.available_cash) : '—'}
        sub={book ? `Reserved ${money(book.swing?.reserved_cash)} swing` : 'Research book'}
        icon={Wallet}
      />
    </section>
    {perfHistory.points?.length > 0 ? (
      <section className="panel" style={{ marginBottom: 16 }}>
        <div className="eyebrow">RESEARCH BOOK VALUATION HISTORY</div>
        <p className="muted small">Point-in-time snapshots — not backtest curves.</p>
        <ResponsiveContainer width="100%" height={180}>
          <AreaChart data={perfHistory.points}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--grid-stroke)" />
            <XAxis dataKey="date" tick={{ fontSize: 10 }} />
            <YAxis tick={{ fontSize: 10 }} width={55} />
            <Tooltip formatter={v => money(v)} />
            <Area type="monotone" dataKey="equity" stroke="#239b7c" fill="#239b7c33" />
          </AreaChart>
        </ResponsiveContainer>
      </section>
    ) : (
      <p className="muted small" style={{ margin: '0 0 16px' }}>
        No portfolio valuation snapshots yet — use Portfolio → Record valuation snapshot.
      </p>
    )}
    <section className="content-grid">
      <div className="panel chart-panel">
        <div className="panel-head">
          <div>
            <div className="eyebrow">MARKET MONITOR</div>
            <h3>Stock research</h3>
          </div>
          <div className="selectors">
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
        </div>
        <div className="price-row">
          <div>
            <span className="muted">{symbol} · Latest demo close</span>
            <div className="price">{money(latest?.close)}</div>
          </div>
          <div className="price-change">
            <span className="muted">3-month return</span>
            <b className={(latest?.return_3m || 0) >= 0 ? 'positive' : 'negative'}>{pct(latest?.return_3m)}</b>
          </div>
        </div>
        <div className="chart-wrap">
          {history.length > 0 ? (
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={history}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--grid-stroke, #e9edf2)" vertical={false} />
                <XAxis dataKey="date" tickFormatter={v => v.slice(5)} tick={{ fontSize: 10 }} axisLine={false} tickLine={false} minTickGap={35} />
                <YAxis domain={['auto', 'auto']} tick={{ fontSize: 10 }} axisLine={false} tickLine={false} width={55} />
                <Tooltip formatter={v => money(v)} />
                <Area type="monotone" dataKey="close" stroke="#239b7c" strokeWidth={2} fill="#239b7c33" />
              </AreaChart>
            </ResponsiveContainer>
          ) : (
            <div className="empty">{loading ? 'Loading…' : 'Waiting for market history…'}</div>
          )}
        </div>
        <div className="indicator-strip">
          <div>
            <span>RSI (14)</span>
            <b>{latest?.rsi14 ?? '—'}</b>
          </div>
          <div>
            <span>ADX (14)</span>
            <b>{latest?.adx14 ?? '—'}</b>
          </div>
          <div>
            <span>EMA 20</span>
            <b>{money(latest?.ema20)}</b>
          </div>
          <div>
            <span>SMA 200</span>
            <b>{money(latest?.sma200)}</b>
          </div>
          <div>
            <span>ATR 14</span>
            <b>{money(latest?.atr14)}</b>
          </div>
        </div>
      </div>
      <div className="panel trade-panel">
        <div className="panel-head">
          <div>
            <div className="eyebrow">PAPER EXECUTION</div>
            <h3>Simulated delivery book</h3>
          </div>
          <span className="paper-chip">NO REAL ORDERS</span>
        </div>
        <p className="muted small">
          Direct BUY/SELL on this dashboard is disabled. Use Paper Trading for Shariah-screened proposals, approvals and ownership-gated sells.
        </p>
        <button type="button" className="buy-btn" onClick={() => setView('paper')}>
          Open Paper Trading
        </button>
      </div>
    </section>
    <section className="panel strategy-panel">
      <div className="panel-head">
        <div>
          <div className="eyebrow">RULE-BASED STRATEGY LIBRARY</div>
          <h3>Strategy evaluation · {symbol}</h3>
        </div>
        <span className="muted small">Profile: {horizon}</span>
      </div>
      <div className="strategy-grid">
        {sortedStrategies.map(s => (
          <div className="strategy-card" key={s.strategy}>
            <div className="strategy-title">
              <b>{s.strategy}</b>
              <StatusBadge>{s.signal}</StatusBadge>
            </div>
            <div className="score-line">
              <div className="score">
                <strong>{s.score}</strong>
                <span>/100</span>
              </div>
              <div className="scorebar">
                <i style={{ width: `${s.score}%` }} />
              </div>
            </div>
            <p>{s.rationale}</p>
            <div className="levels">
              <div>
                <span>Entry ref.</span>
                <b>{money(s.entry_price)}</b>
              </div>
              <div>
                <span>Stop</span>
                <b className="negative">{money(s.stop_loss)}</b>
              </div>
              <div>
                <span>Target</span>
                <b className="positive">{money(s.target)}</b>
              </div>
              <div>
                <span>R:R</span>
                <b>{s.risk_reward}:1</b>
              </div>
            </div>
          </div>
        ))}
      </div>
    </section>
    <section className="bottom-grid">
      <div className="panel">
        <div className="panel-head">
          <div>
            <div className="eyebrow">UNIVERSE SCANNER</div>
            <h3>Top ranked demo candidates</h3>
          </div>
          <span className="muted small">{horizon} profile</span>
        </div>
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Symbol</th>
                <th>Signal</th>
                <th>Best strategy</th>
                <th>Score</th>
                <th>3M return</th>
              </tr>
            </thead>
            <tbody>
              {scan.map(r => (
                <tr key={r.symbol} onClick={() => setSymbol(r.symbol)} className="click-row">
                  <td>
                    <b>{r.symbol}</b>
                  </td>
                  <td>
                    <StatusBadge>{r.signal}</StatusBadge>
                  </td>
                  <td>{r.best_strategy}</td>
                  <td>
                    <b>{r.score}</b>
                  </td>
                  <td className={r.return_3m >= 0 ? 'positive' : 'negative'}>{pct(r.return_3m)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
      <div className="panel">
        <div className="panel-head">
          <div>
            <div className="eyebrow">VIRTUAL HOLDINGS</div>
            <h3>Research book holdings</h3>
          </div>
        </div>
        {holdings?.length ? (
          <div className="holdings">
            {holdings.map(p => (
              <div className="holding" key={`${p.symbol}-${p.sleeve}`}>
                <div>
                  <b>{p.symbol}</b>
                  <small>
                    {p.quantity} shares · {p.sleeve} · Avg {money(p.average_entry)}
                  </small>
                </div>
                <div className="holding-right">
                  <b>{money(p.market_value)}</b>
                  <small className="muted">{p.ownership_state || '—'}</small>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="empty-holdings">
            <Wallet size={25} />
            <b>No open positions yet</b>
            <span>Use Paper Trading after an allocation proposal passes screening.</span>
          </div>
        )}
      </div>
    </section>
  </>
  )
}