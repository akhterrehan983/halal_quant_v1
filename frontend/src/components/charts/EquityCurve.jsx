import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { money } from '../../utils/format'

export default function EquityCurve({ points, dataKey = 'equity', height = 220 }) {
  if (!points?.length) return null
  return (
    <ResponsiveContainer width="100%" height={height}>
      <AreaChart data={points}>
        <CartesianGrid strokeDasharray="3 3" stroke="var(--grid-stroke)" />
        <XAxis dataKey="date" tick={{ fontSize: 10 }} />
        <YAxis tick={{ fontSize: 10 }} width={55} />
        <Tooltip formatter={v => money(v)} />
        <Area type="monotone" dataKey={dataKey} stroke="#239b7c" fill="#239b7c33" />
      </AreaChart>
    </ResponsiveContainer>
  )
}