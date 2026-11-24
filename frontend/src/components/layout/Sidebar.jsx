import React from 'react'
import {
  Database,
  FlaskConical,
  History,
  LayoutDashboard,
  PieChart,
  Radio,
  Settings,
  ShieldAlert,
  ShieldCheck,
  Wallet,
} from 'lucide-react'
import { useApp } from '../../context/AppContext'

const NAV = [
  { label: 'Research', items: [
    { id: 'overview', label: 'Overview', icon: LayoutDashboard },
    { id: 'market', label: 'Market Data', icon: Database },
    { id: 'strategies', label: 'Strategy Explorer', icon: FlaskConical },
    { id: 'signals', label: 'Signal Center', icon: Radio },
  ]},
  { label: 'Portfolio', items: [
    { id: 'portfolio', label: 'Portfolio', icon: PieChart },
    { id: 'risk', label: 'Risk Dashboard', icon: ShieldAlert },
    { id: 'paper', label: 'Paper Trading', icon: Wallet },
  ]},
  { label: 'Compliance', items: [{ id: 'shariah', label: 'Shariah Compliance', icon: ShieldCheck }] },
  { label: 'Analytics', items: [{ id: 'backtest', label: 'Backtesting Lab', icon: History }] },
  { label: 'System', items: [{ id: 'settings', label: 'Settings', icon: Settings }] },
]

const TITLES = Object.fromEntries(NAV.flatMap(g => g.items.map(i => [i.id, i.label])))

export function pageTitle(view) {
  return TITLES[view] || 'Overview'
}

export default function Sidebar() {
  const { view, setView } = useApp()
  return (
    <aside className="sidebar">
      <div className="brand">
        <div className="brand-mark">HQ</div>
        <div>
          <b>HALAL QUANT</b>
          <small>RESEARCH TERMINAL · V1</small>
        </div>
      </div>
      {NAV.map(group => (
        <React.Fragment key={group.label}>
          <div className="nav-label">{group.label}</div>
          {group.items.map(item => {
            const Icon = item.icon
            return (
              <div
                key={item.id}
                className={`nav-item ${view === item.id ? 'active' : ''}`}
                onClick={() => setView(item.id)}
                onKeyDown={e => e.key === 'Enter' && setView(item.id)}
                role="button"
                tabIndex={0}
                aria-current={view === item.id ? 'page' : undefined}
              >
                <Icon size={17} aria-hidden />
                {item.label}
              </div>
            )
          })}
        </React.Fragment>
      ))}
      <div className="sidebar-bottom">
        <span className="live-dot" aria-hidden />
        Demo research environment
        <small>Synthetic market data — not live NSE</small>
      </div>
    </aside>
  )
}