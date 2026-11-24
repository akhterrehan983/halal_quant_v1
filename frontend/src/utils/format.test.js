import { describe, expect, it } from 'vitest'
import { money, pct } from './format'

describe('format utils', () => {
  it('formats INR money without decimals by default', () => {
    expect(money(100000)).toMatch(/1,00,000/)
  })

  it('formats percent', () => {
    expect(pct(12.345)).toBe('12.3%')
  })

  it('handles nullish money as zero', () => {
    expect(money(null)).toMatch(/0/)
  })
})