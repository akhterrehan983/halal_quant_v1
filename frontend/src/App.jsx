import { AppProvider, useApp } from './context/AppContext'
import MainLayout from './components/layout/MainLayout'
import Overview from './pages/Overview'
import MarketData from './pages/MarketData'
import StrategyExplorer from './pages/StrategyExplorer'
import SignalCenter from './pages/SignalCenter'
import Portfolio from './pages/Portfolio'
import RiskDashboard from './pages/RiskDashboard'
import ShariahCompliance from './pages/ShariahCompliance'
import PaperTrading from './pages/PaperTrading'
import BacktestingLab from './pages/BacktestingLab'
import Settings from './pages/Settings'

const PAGES = {
  overview: Overview,
  market: MarketData,
  strategies: StrategyExplorer,
  signals: SignalCenter,
  portfolio: Portfolio,
  risk: RiskDashboard,
  shariah: ShariahCompliance,
  paper: PaperTrading,
  backtest: BacktestingLab,
  settings: Settings,
}

function AppRoutes() {
  const { view } = useApp()
  const Page = PAGES[view] || Overview
  return <Page />
}

export default function App() {
  return (
    <AppProvider>
      <MainLayout>
        <AppRoutes />
      </MainLayout>
    </AppProvider>
  )
}