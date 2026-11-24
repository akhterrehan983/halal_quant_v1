export const money = n =>
  new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 }).format(Number(n) || 0)

export const moneyPrecise = n =>
  new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 2 }).format(Number(n) || 0)

export const pct = n => `${Number(n || 0).toFixed(1)}%`

export const fmtNum = (n, d = 2) => (n == null || n === '' ? '—' : Number(n).toFixed(d))