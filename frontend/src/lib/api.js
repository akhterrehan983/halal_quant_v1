const BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000'
async function request(path, options={}) {
  const res = await fetch(`${BASE}${path}`, options)
  const data = await res.json()
  if (!res.ok) throw new Error(data.detail || 'API request failed')
  return data
}
async function upload(path, file, query = '') {
  const form = new FormData()
  form.append('file', file)
  const res = await fetch(`${BASE}${path}${query}`, { method: 'POST', body: form })
  const data = await res.json()
  if (!res.ok) throw new Error(data.detail?.message || data.detail || 'Upload failed')
  return data
}

export const api = {
  health: () => request('/api/health'),
  universe: () => request('/api/universe'),
  history: (symbol) => request(`/api/history/${symbol}?limit=260`),
  signals: (symbol,horizon) => request(`/api/signals/${symbol}?horizon=${horizon}`),
  scan: (horizon) => request(`/api/scan?horizon=${horizon}`),
  portfolio: () => request('/api/portfolio'),
  trade: (side,payload) => request(`/api/portfolio/${side}`, {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)}),
  uploadCsvLegacy: (file) => upload('/api/data/upload', file),
  importCsv: (file, conflictPolicy) =>
    upload('/api/v1/market-data/import/csv', file, conflictPolicy ? `?conflict_policy=${conflictPolicy}` : ''),
  validateCsv: (file) => upload('/api/v1/market-data/validate', file),
  marketImports: () => request('/api/v1/market-data/imports'),
  marketQuality: (symbol) => request(`/api/v1/market-data/quality/${symbol}`),
  marketCandles: (symbol, limit = 30) => request(`/api/v1/market-data/${symbol}/candles?limit=${limit}`),
  marketLatest: (symbol) => request(`/api/v1/market-data/${symbol}/latest`),
  strategies: () => request('/api/v1/strategies'),
  strategyEvaluate: (id, symbol, horizon) =>
    request(`/api/v1/strategies/${id}/evaluate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ symbol, horizon }),
    }),
  strategyToggle: (id, enabled) =>
    request(`/api/v1/strategies/${id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ enabled }),
    }),
  evaluateAllStrategies: (symbol, horizon) =>
    request('/api/v1/strategies/evaluate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ symbol, horizon }),
    }),
  regimeCurrent: () => request('/api/v1/regime/current'),
  regimeHistory: (limit = 60) => request(`/api/v1/regime/history?limit=${limit}`),
  unifiedSignals: ({ horizon = 'swing', symbol, category, lifecycle, minScore = 0 } = {}) => {
    const q = new URLSearchParams({ horizon, mode: 'unified', min_score: String(minScore) })
    if (symbol) q.set('symbol', symbol)
    if (category) q.set('category', category)
    if (lifecycle) q.set('lifecycle', lifecycle)
    return request(`/api/v1/signals?${q}`)
  },
  signalRankings: (horizon = 'swing', limit = 50) =>
    request(`/api/v1/signals/rankings?horizon=${horizon}&limit=${limit}`),
  generateSignals: (body) =>
    request('/api/v1/signals/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),
  signalById: (id) => request(`/api/v1/signals/${id}`),
  signalHistory: (id) => request(`/api/v1/signals/${id}/history`),
  bookSummary: () => request('/api/v1/portfolio/summary'),
  bookHoldings: () => request('/api/v1/portfolio/holdings'),
  bookProposals: (status) =>
    request(`/api/v1/portfolio/allocation-proposals${status ? `?status=${status}` : ''}`),
  generateProposals: (horizon, limit = 10) =>
    request('/api/v1/portfolio/allocate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ horizon, limit }),
    }),
  riskExposure: () => request('/api/v1/risk/exposure'),
  riskLimits: () => request('/api/v1/risk/limits'),
  riskConfig: () => request('/api/v1/risk/config'),
  patchRiskConfig: body =>
    request('/api/v1/risk/config', {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),
  riskEvents: () => request('/api/v1/risk/events'),
  rebalancePropose: () => request('/api/v1/portfolio/rebalance/propose', { method: 'POST' }),
  shariahStandards: () => request('/api/v1/shariah/standards'),
  shariahScreening: (symbol) => request(`/api/v1/shariah/screening/${symbol}`),
  shariahEvaluate: (symbol, body) =>
    request(`/api/v1/shariah/screening/${symbol}/evaluate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),
  shariahSnapshots: (symbol) => request(`/api/v1/shariah/snapshots/${symbol}`),
  executionOrders: () => request('/api/v1/execution/orders'),
  createPaperOrder: (body) =>
    request('/api/v1/execution/orders', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),
  approveOrder: (id) => request(`/api/v1/execution/orders/${id}/approve`, { method: 'POST' }),
  simulateOrder: (id) => request(`/api/v1/execution/orders/${id}/simulate`, { method: 'POST' }),
  executionHoldings: () => request('/api/v1/execution/holdings'),
  sellAuth: (symbol, quantity, sleeve = 'swing') =>
    request(`/api/v1/execution/sell-authorizations?symbol=${symbol}&quantity=${quantity}&sleeve=${sleeve}`),
  processSettlements: () => request('/api/v1/execution/settlements/process', { method: 'POST' }),
  backtests: () => request('/api/v1/backtests'),
  createBacktest: (config, runNow = true) =>
    request(`/api/v1/backtests?run_now=${runNow}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(config),
    }),
  backtestSummary: (id) => request(`/api/v1/backtests/${id}/summary`),
  backtestEquity: (id) => request(`/api/v1/backtests/${id}/equity-curve`),
  backtestValidation: (id) => request(`/api/v1/backtests/${id}/validation`),
}
