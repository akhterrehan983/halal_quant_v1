import { useEffect, useState } from 'react'
import { Database, RefreshCw, Upload } from 'lucide-react'
import { useApp } from '../context/AppContext'
import PageHeader from '../components/layout/PageHeader'
import { ShellError } from '../components/layout/MainLayout'
import { api } from '../lib/api'

export default function MarketData() {
  const { symbol, setSymbol, universe, error, setError } = useApp()
  const [importFile, setImportFile] = useState(null)
  const [importPolicy, setImportPolicy] = useState('skip')
  const [importResult, setImportResult] = useState(null)
  const [validateResult, setValidateResult] = useState(null)
  const [marketQuality, setMarketQuality] = useState(null)
  const [recentCandles, setRecentCandles] = useState([])
  const [imports, setImports] = useState([])

  const loadMarketMeta = async (sym = symbol) => {
    try {
      const [q, c] = await Promise.all([api.marketQuality(sym), api.marketCandles(sym, 15)])
      setMarketQuality(q)
      setRecentCandles(c.candles || [])
    } catch (e) {
      setError(e.message)
    }
  }

  useEffect(() => {
    loadMarketMeta(symbol)
    api.marketImports().then(r => setImports(r.items || r.imports || [])).catch(() => setImports([]))
  }, [symbol])

  const runImport = async () => {
    if (!importFile) return
    try {
      setImportResult(null)
      const r = await api.importCsv(importFile, importPolicy)
      setImportResult(r)
      await loadMarketMeta(symbol)
    } catch (e) {
      setImportResult({ status: 'failed', message: e.message })
    }
  }

  const runValidate = async () => {
    if (!importFile) return
    try {
      setValidateResult(await api.validateCsv(importFile))
    } catch (e) {
      setValidateResult({ error: e.message })
    }
  }

  return (
  <>
    <ShellError error={error} onRetry={() => loadMarketMeta(symbol)} />
    <section className="panel market-panel">
      <PageHeader eyebrow="MARKET DATA" title="CSV import & data quality" chip="Not live NSE feed" />
      <div className="md-grid">
        <div className="md-card">
          <label>CSV file</label>
          <input type="file" accept=".csv,text/csv" onChange={e => setImportFile(e.target.files?.[0] || null)} />
          <label>Conflict policy</label>
          <select value={importPolicy} onChange={e => setImportPolicy(e.target.value)}>
            <option value="skip">Skip duplicates</option>
            <option value="update">Update conflicts</option>
            <option value="reject">Reject on conflict</option>
          </select>
          <div className="trade-buttons">
            <button type="button" className="buy-btn" onClick={runValidate}>
              <Upload size={16} /> Validate only
            </button>
            <button type="button" className="buy-btn" onClick={runImport}>
              <Database size={16} /> Import
            </button>
          </div>
          {validateResult && <pre className="md-pre">{JSON.stringify(validateResult, null, 2)}</pre>}
          {importResult && <pre className="md-pre">{JSON.stringify(importResult, null, 2)}</pre>}
          {imports.length > 0 && (
            <>
              <p className="eyebrow" style={{ marginTop: 12 }}>
                Import history
              </p>
              <pre className="md-pre">{JSON.stringify(imports.slice(0, 5), null, 2)}</pre>
            </>
          )}
        </div>
        <div className="md-card">
          <label>Symbol</label>
          <select value={symbol} onChange={e => setSymbol(e.target.value)}>
            {universe.map(s => (
              <option key={s.symbol} value={s.symbol}>
                {s.symbol}
              </option>
            ))}
          </select>
          <button type="button" className="icon-btn md-refresh" onClick={() => loadMarketMeta(symbol)} title="Refresh quality">
            <RefreshCw size={15} />
          </button>
          {marketQuality && (
            <div className="md-meta">
              <p>
                <b>Source:</b> {marketQuality.data_source}
              </p>
              <p>
                <b>Range:</b> {marketQuality.date_range?.start} → {marketQuality.date_range?.end}
              </p>
              <p>
                <b>Candles:</b> {marketQuality.candle_count}
              </p>
              <p>
                <b>Warnings:</b> {marketQuality.validation?.warning_count ?? 0}
              </p>
              {marketQuality.missing_sessions_approximate && (
                <p className="muted small">Missing-session checks are approximate (no licensed NSE holiday calendar).</p>
              )}
            </div>
          )}
          {recentCandles.length > 0 && (
            <table>
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Close</th>
                  <th>Volume</th>
                </tr>
              </thead>
              <tbody>
                {recentCandles.slice(-10).map(c => (
                  <tr key={c.trading_date}>
                    <td>{c.trading_date}</td>
                    <td>{c.close}</td>
                    <td>{c.volume}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </section>
  </>
  )
}