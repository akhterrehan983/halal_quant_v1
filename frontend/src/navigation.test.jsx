import { describe, expect, it } from 'vitest'
import { pageTitle } from './components/layout/Sidebar'

const EXPECTED = [
  'overview',
  'market',
  'strategies',
  'signals',
  'portfolio',
  'risk',
  'shariah',
  'paper',
  'backtest',
  'settings',
]

describe('navigation', () => {
  it('maps every view id to a title', () => {
    for (const id of EXPECTED.filter(x => x !== 'overview')) {
      expect(pageTitle(id)).toBeTruthy()
      expect(pageTitle(id)).not.toBe('Overview')
    }
    expect(pageTitle('overview')).toBe('Overview')
  })
})