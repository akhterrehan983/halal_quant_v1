import ErrorState from '../common/ErrorState'
import Header from './Header'
import Sidebar from './Sidebar'

export default function MainLayout({ children }) {
  return (
    <div className="app-shell">
      <Sidebar />
      <main className="main">
        <Header />
        {children}
        <footer>
          HALAL QUANT V1 · LOCAL RESEARCH PROTOTYPE <span>Built for swing &amp; positional strategy research</span>
        </footer>
      </main>
    </div>
  )
}

export function ShellError({ error, onRetry }) {
  if (!error) return null
  return (
    <ErrorState
      message={`${error} — ensure the FastAPI backend is running on port 8000.`}
      onRetry={onRetry}
    />
  )
}