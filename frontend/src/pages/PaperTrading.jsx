import { useEffect, useState } from 'react'
import { Activity } from 'lucide-react'
import PageHeader from '../components/layout/PageHeader'
import MetricCard from '../components/common/MetricCard'
import StatusBadge from '../components/common/StatusBadge'
import { ShellError } from '../components/layout/MainLayout'
import { api } from '../lib/api'
import { useApp } from '../context/AppContext'
import { money } from '../utils/format'

export default function PaperTrading() {
  const { error, setError } = useApp()
  const [orders, setOrders] = useState([])
  const [execHoldings, setExecHoldings] = useState([])
  const [proposals, setProposals] = useState([])
  const [paperMsg, setPaperMsg] = useState('')

  const loadPaper = async () => {
    try {
      const [o, h, p] = await Promise.all([api.executionOrders(), api.executionHoldings(), api.bookProposals()])
      setOrders(o.items || [])
      setExecHoldings(h.holdings || [])
      setProposals(p.items || [])
    } catch (e) {
      setError(e.message)
    }
  }

  useEffect(() => {
    loadPaper()
  }, [])

  const createPaperBuy = async pid => {
    try {
      setPaperMsg('')
      const p = proposals.find(x => x.proposal_id === pid)
      if (!p) return
      const o = await api.createPaperOrder({
        symbol: p.symbol,
        sleeve: p.sleeve,
        side: 'BUY',
        order_type: 'MARKET',
        quantity: p.quantity,
        proposal_id: p.proposal_id,
      })
      setPaperMsg(`Order ${o.order_id} ${o.state}`)
      await loadPaper()
    } catch (e) {
      setPaperMsg(e.message)
    }
  }

  const pending = orders.filter(o => o.state === 'PENDING_APPROVAL' || o.state === 'APPROVED')
  const filled = orders.filter(o => o.state === 'FILLED' || o.state === 'SETTLED')
  const rejected = orders.filter(o => o.state === 'REJECTED')
  const cancelled = orders.filter(o => o.state === 'CANCELLED')

  return (
  <>
    <ShellError error={error} onRetry={loadPaper} />
    <section className="panel signal-panel">
      <PageHeader eyebrow="PAPER TRADING" title="Simulated delivery · no live broker" chip="SIMULATED ONLY" />
      <p className="muted small">Workflow: proposal → order → approve → simulate → settle → ownership verify → sell authorization.</p>
      {paperMsg && <p>{paperMsg}</p>}
      <MetricCard label="Open orders" value={pending.length} sub={`Filled ${filled.length} · simulated book`} icon={Activity} />

      <h4>Pending / approved</h4>
      <OrderTable orders={pending} loadPaper={loadPaper} actions />

      <h4>Filled</h4>
      <OrderTable orders={filled} />

      <h4>Rejected / cancelled</h4>
      <OrderTable orders={[...rejected, ...cancelled]} />

      <button type="button" className="buy-btn" style={{ marginTop: 10 }} onClick={() => api.processSettlements().then(loadPaper)}>
        Process settlements
      </button>

      <h4>Proposals → orders</h4>
      {proposals
        .filter(p => p.status === 'PENDING')
        .slice(0, 8)
        .map(p => (
          <button key={p.proposal_id} type="button" className="buy-btn" style={{ marginRight: 8, marginBottom: 8 }} onClick={() => createPaperBuy(p.proposal_id)}>
            Order {p.symbol}
          </button>
        ))}

      <h4>Holdings (research book + ownership overlay)</h4>
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th>Symbol</th>
              <th>Sleeve</th>
              <th>Qty</th>
              <th>Avg</th>
              <th>Value</th>
              <th>Ownership</th>
              <th>Sellable</th>
            </tr>
          </thead>
          <tbody>
            {execHoldings.map(h => (
              <tr key={`${h.symbol}-${h.sleeve}`}>
                <td>{h.symbol}</td>
                <td>{h.sleeve}</td>
                <td>{h.quantity}</td>
                <td>{money(h.average_entry)}</td>
                <td>{money(h.market_value)}</td>
                <td>
                  <StatusBadge>{h.ownership_state || '—'}</StatusBadge>
                </td>
                <td>{h.sellable_quantity ?? '—'}</td>
              </tr>
            ))}
            {execHoldings.length === 0 && (
              <tr>
                <td colSpan={7} className="muted">
                  No holdings
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

function OrderTable({ orders, loadPaper, actions }) {
  return (
    <div className="table-scroll">
      <table>
        <thead>
          <tr>
            <th>ID</th>
            <th>Sym</th>
            <th>Side</th>
            <th>Qty</th>
            <th>State</th>
            {actions && <th>Actions</th>}
          </tr>
        </thead>
        <tbody>
          {orders.map(o => (
            <tr key={o.order_id}>
              <td>{o.order_id}</td>
              <td>{o.symbol}</td>
              <td>{o.side}</td>
              <td>{o.quantity}</td>
              <td>
                <StatusBadge>{o.state}</StatusBadge>
              </td>
              {actions && (
                <td>
                  {o.state === 'PENDING_APPROVAL' && (
                    <button
                      type="button"
                      className="icon-btn"
                      onClick={async () => {
                        await api.approveOrder(o.order_id)
                        loadPaper()
                      }}
                    >
                      Approve
                    </button>
                  )}
                  {o.state === 'APPROVED' && (
                    <button
                      type="button"
                      className="icon-btn"
                      onClick={async () => {
                        await api.simulateOrder(o.order_id)
                        loadPaper()
                      }}
                    >
                      Simulate
                    </button>
                  )}
                </td>
              )}
            </tr>
          ))}
          {orders.length === 0 && (
            <tr>
              <td colSpan={actions ? 6 : 5} className="muted">
                None
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  )
}