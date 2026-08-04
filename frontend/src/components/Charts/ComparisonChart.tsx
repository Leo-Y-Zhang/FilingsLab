/**
 * ComparisonChart
 * Overlays portfolio value histories for multiple traders on a single chart.
 * Each trader gets a distinct colour; starting capital shown as reference line.
 */

import {
  ResponsiveContainer, LineChart, Line, XAxis, YAxis,
  CartesianGrid, Tooltip, ReferenceLine, Legend,
} from 'recharts'
import type { ComparisonEntry } from '@/types'
import { currency } from '@/utils/format'

interface Props {
  entries: ComparisonEntry[]
  colours: Record<number, string>   // trader_id → hex colour
  bestTraderId?: number
  initialCapital: number
}

function CustomTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null
  return (
    <div className="rounded-lg border border-surface-border bg-surface-elevated p-3 shadow-xl text-xs">
      <p className="font-medium text-slate-300 mb-1.5">{label}</p>
      {payload.map((p: any) => (
        <div key={p.dataKey} className="flex justify-between gap-4">
          <span style={{ color: p.color }}>{p.name}</span>
          <span className="font-mono font-semibold" style={{ color: p.color }}>{currency(p.value)}</span>
        </div>
      ))}
    </div>
  )
}

export default function ComparisonChart({ entries, colours, bestTraderId, initialCapital }: Props) {
  const MAX_POINTS = 400
  const maxLen = Math.max(...entries.map(e => e.portfolio_history.length), 1)
  const step = Math.max(1, Math.floor(maxLen / MAX_POINTS))

  // Build combined date-indexed data, downsampled for performance
  const dateMap = new Map<string, Record<string, number>>()
  entries.forEach(entry => {
    entry.portfolio_history
      .filter((_, i) => i % step === 0)
      .forEach(pt => {
        if (!dateMap.has(pt.date)) dateMap.set(pt.date, {})
        dateMap.get(pt.date)![entry.name] = pt.portfolio_value
      })
  })

  const chartData = Array.from(dateMap.entries())
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([date, vals]) => ({ date, ...vals }))

  const allVals = entries.flatMap(e => e.portfolio_history.map(p => p.portfolio_value))
  const minY = Math.min(...allVals, initialCapital) * 0.94
  const maxY = Math.max(...allVals, initialCapital) * 1.06

  return (
    <ResponsiveContainer width="100%" height="100%">
      <LineChart data={chartData} margin={{ top: 10, right: 10, bottom: 0, left: 10 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#334155" vertical={false} />
        <XAxis dataKey="date" tick={{ fill: '#94a3b8', fontSize: 10 }} tickLine={false} axisLine={false}
               tickFormatter={v => v.slice(0, 7)} interval="preserveStartEnd" />
        <YAxis domain={[minY, maxY]} tick={{ fill: '#94a3b8', fontSize: 10 }} tickLine={false} axisLine={false}
               tickFormatter={v => typeof v === 'number' ? `$${(v / 1000).toFixed(0)}k` : ''} width={60} />
        <Tooltip content={<CustomTooltip />} />
        <Legend wrapperStyle={{ fontSize: 11, color: '#94a3b8', paddingTop: 8 }} />
        <ReferenceLine y={initialCapital} stroke="#475569" strokeDasharray="4 3"
                       label={{ value: 'Start', fill: '#64748b', fontSize: 10, position: 'right' }} />
        {entries.map(entry => (
          <Line
            key={entry.trader_id}
            type="monotone"
            dataKey={entry.name}
            stroke={colours[entry.trader_id]}
            strokeWidth={entry.trader_id === bestTraderId ? 2.5 : 1.5}
            dot={false}
            activeDot={{ r: 4 }}
          />
        ))}
      </LineChart>
    </ResponsiveContainer>
  )
}
