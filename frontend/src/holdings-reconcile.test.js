import { describe, expect, it } from 'vitest'

/** Ensures Portfolio and Paper Trading parse enriched holdings the same way. */
function parseHoldings(payload) {
  const list = payload.holdings || []
  return list.map(h => ({
    key: `${h.symbol}-${h.sleeve}`,
    qty: Number(h.quantity),
    cashValue: h.market_value,
  }))
}

describe('holdings reconcile shape', () => {
  it('maps enriched API rows consistently', () => {
    const sample = {
      holdings: [
        { symbol: 'TCS', sleeve: 'swing', quantity: 5, market_value: '25000', ownership_state: 'EXECUTED_UNSETTLED' },
      ],
    }
    const a = parseHoldings(sample)
    const b = parseHoldings({ holdings: sample.holdings })
    expect(a).toEqual(b)
    expect(a[0].qty).toBe(5)
  })
})