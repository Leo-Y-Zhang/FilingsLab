import {
  ResponsiveContainer, LineChart, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, Legend, ReferenceLine,
} from 'recharts'
import type { AlphaDecayResult } from '@/types'

function CustomTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null
  return (
    <div className="rounded-lg border border-surface-border bg-surface-elevated p-3 shadow-xl text-xs">
      <p className="font-semibold text-slate-300 mb-1.5">Delay: {label} days</p>
      {payload.map((p: any) => (
        <div key={p.dataKey} className="flex justify-between gap-4">
          <span style={{ color: p.color }}>{p.name}</span>
          <span className="font-mono font-semibold" style={{ color: p.color }}>
            {p.value >= 0 ? '+' : ''}{p.value.toFixed(2)}%
          </span>
        </div>
      ))}
    </div>
  )
}

export default function AlphaDecayChart({ result }: { result: AlphaDecayResult }) {
  const data = result.data_points.map(pt => ({
    delay: pt.delay_days,
    'Excess Return': pt.excess_return_pct ?? 0,
    'Total Return':  pt.total_return_pct,
    'Sortino':       pt.sortino_ratio,
  }))

  const allValues = data.flatMap(d => [d['Excess Return'], d['Total Return']])
  const minY = Math.min(...allValues) * 1.1
  const maxY = Math.max(...allValues) * 1.1

  return (
    <ResponsiveContainer width="100%" height="100%">
      <LineChart data={data} margin={{ top: 10, right: 20, bottom: 10, left: 10 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#334155" vertical={false} />
        <XAxis dataKey="delay" tickLine={false} axisLine={false}
               tick={{ fill: '#94a3b8', fontSize: 11 }}
               label={{ value: 'Delay (days)', position: 'insideBottom', offset: -5, fill: '#64748b', fontSize: 11 }} />
        <YAxis domain={[minY, maxY]} tickLine={false} axisLine={false}
               tick={{ fill: '#94a3b8', fontSize: 11 }}
               tickFormatter={v => typeof v === 'number' ? `${v.toFixed(1)}%` : ''} width={55} />
        <Tooltip content={<CustomTooltip />} />
        <Legend wrapperStyle={{ fontSize: 12, color: '#94a3b8', paddingTop: 12 }} />
        <ReferenceLine y={0} stroke="#475569" strokeDasharray="4 3" />
        {result.half_life_days && (
          <ReferenceLine x={result.half_life_days} stroke="#f59e0b" strokeDasharray="4 3"
                         label={{ value: `½-life ~${result.half_life_days}d`, fill: '#f59e0b', fontSize: 10, position: 'top' }} />
        )}
        <Line type="monotone" dataKey="Excess Return" stroke="#3b82f6" strokeWidth={2.5}
              dot={{ r: 4, fill: '#3b82f6' }} activeDot={{ r: 6 }} />
        <Line type="monotone" dataKey="Total Return" stroke="#10b981" strokeWidth={1.5}
              strokeDasharray="5 3" dot={{ r: 3, fill: '#10b981' }} />
      </LineChart>
    </ResponsiveContainer>
  )
}
