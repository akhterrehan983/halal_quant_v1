import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import { api } from '../lib/api'

const AppContext = createContext(null)

export function AppProvider({ children }) {
  const [view, setView] = useState('overview')
  const [theme, setTheme] = useState(() => localStorage.getItem('hq-theme') || 'light')
  const [symbol, setSymbol] = useState('TCS')
  const [horizon, setHorizon] = useState('swing')
  const [universe, setUniverse] = useState([])
  const [scan, setScan] = useState([])
  const [detail, setDetail] = useState(null)
  const [history, setHistory] = useState([])
  const [portfolio, setPortfolio] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [health, setHealth] = useState(null)

  const loadHealth = useCallback(async () => {
    try {
      const h = await api.health()
      setHealth(h)
    } catch {
      setHealth(null)
    }
  }, [])

  const loadAll = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const [u, s, p] = await Promise.all([api.universe(), api.scan(horizon), api.portfolio()])
      setUniverse(u.symbols || [])
      setScan(s.results || [])
      setPortfolio(p)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }, [horizon])

  const loadDetail = useCallback(
    async (sym = symbol) => {
      try {
        const [d, h] = await Promise.all([api.signals(sym, horizon), api.history(sym)])
        setDetail(d)
        setHistory(h.data || [])
      } catch (e) {
        setError(e.message)
      }
    },
    [symbol, horizon]
  )

  useEffect(() => {
    document.documentElement.dataset.theme = theme
    localStorage.setItem('hq-theme', theme)
  }, [theme])

  useEffect(() => {
    loadHealth()
    loadAll()
  }, [loadAll, loadHealth])

  useEffect(() => {
    if (symbol) loadDetail(symbol)
  }, [symbol, horizon, loadDetail])

  const value = useMemo(
    () => ({
      view,
      setView,
      theme,
      setTheme,
      symbol,
      setSymbol,
      horizon,
      setHorizon,
      universe,
      scan,
      detail,
      history,
      portfolio,
      loading,
      error,
      setError,
      health,
      loadAll,
      loadDetail,
      loadHealth,
    }),
    [view, theme, symbol, horizon, universe, scan, detail, history, portfolio, loading, error, health, loadAll, loadDetail, loadHealth]
  )

  return <AppContext.Provider value={value}>{children}</AppContext.Provider>
}

export function useApp() {
  const ctx = useContext(AppContext)
  if (!ctx) throw new Error('useApp requires AppProvider')
  return ctx
}