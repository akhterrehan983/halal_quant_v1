import { Moon, RefreshCw, Sun } from 'lucide-react'
import { useApp } from '../../context/AppContext'
import { pageTitle } from './Sidebar'

export default function Header() {
  const { view, theme, setTheme, loadAll, loadHealth, health } = useApp()
  const dbOn = health?.database_enabled
  const dataMode = dbOn ? 'PostgreSQL' : 'Demo store'

  return (
    <header className="topbar">
      <div>
        <div className="eyebrow">SYSTEMATIC EQUITY RESEARCH</div>
        <h1>{pageTitle(view)}</h1>
      </div>
      <div className="top-actions">
        <span className="market-status" title="Connection">
          <i aria-hidden /> {health ? 'API connected' : 'API offline'}
        </span>
        <span className="data-mode-chip" title="Persistence layer">
          {dataMode}
        </span>
        <span className="market-status paper-tag">PAPER MODE</span>
        <button
          type="button"
          className="icon-btn"
          onClick={() => {
            loadHealth()
            loadAll()
          }}
          title="Refresh core data"
          aria-label="Refresh"
        >
          <RefreshCw size={17} />
        </button>
        <button
          type="button"
          className="icon-btn"
          onClick={() => setTheme(theme === 'light' ? 'dark' : 'light')}
          title="Toggle theme"
          aria-label="Toggle theme"
        >
          {theme === 'light' ? <Moon size={17} /> : <Sun size={17} />}
        </button>
        <div className="avatar" aria-hidden>
          RA
        </div>
      </div>
    </header>
  )
}