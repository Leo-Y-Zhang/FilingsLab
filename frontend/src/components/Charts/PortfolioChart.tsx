import {
  ResponsiveContainer, AreaChart, Area, XAxis, YAxis,
  CartesianGrid, Tooltip, ReferenceLine, Legend,
} from 'recharts'
import type { PortfolioPoint } from '@/types'
import { currency } from '@/utils/format'

interface Props {
  data: PortfolioPoint[]
  startingCapital: number
  benchmarkData?: { date: string; value: number }[]
}

function Tip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null
  return (
    <div className="rounded-lg border border-surface-border bg-surface-elevated p-3 shadow-xl text-xs">
      <p className="font-medium text-slate-300 mb-1">{label}</p>
      {payload.map((p: any) => (
        <div key={p.dataKey} className="flex justify-between gap-3">
          <span style={{ color: p.color }}>{p.name}</span>
          <span className="font-mono font-semibold" style={{ color: p.color }}>{currency(p.value)}</span>
        </div>
      ))}
    </div>
  )
}

export default function PortfolioChart({ data, startingCapital, benchmarkData }: Props) {
  const step = Math.max(1, Math.floor(data.length / 500))
  const sampled = data.filter((_, i) => i % step === 0)

  const chartData = sampled.map((pt, i) => ({
    date: pt.date,
    'Portfolio': pt.portfolio_value,
    ...(benchmarkData?.[i * step] ? { 'S&P 500': benchmarkData[i * step].value } : {}),
  }))

  const allVals = data.map(d => d.portfolio_value)
  const minY = Math.min(...allVals, startingCapital) * 0.94
  const maxY = Math.max(...allVals, startingCapital) * 1.06

  return (
    <ResponsiveContainer width="100%" height="100%">
      <AreaChart data={chartData} margin={{ top: 10, right: 10, bottom: 0, left: 10 }}>
        <defs>
          <linearGradient id="portGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%"  stopColor="#3b82f6" stopOpacity={0.25} />
            <stop offset="95%" stopColor="#3b82f6" stopOpacity={0} />
          </linearGradient>
          <linearGradient id="benchGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%"  stopColor="#f59e0b" stopOpacity={0.15} />
            <stop offset="95%" stopColor="#f59e0b" stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid strokeDasharray="3 3" stroke="#334155" vertical={false} />
        <XAxis dataKey="date" tickLine={false} axisLine={false}
               tick={{ fill: '#94a3b8', fontSize: 10 }}
               tickFormatter={v => v.slice(0, 7)} interval="preserveStartEnd" />
        <YAxis domain={[minY, maxY]} tickLine={false} axisLine={false}
               tick={{ fill: '#94a3b8', fontSize: 10 }}
               tickFormatter={v => typeof v === 'number' ? `$${(v / 1000).toFixed(0)}k` : ''} width={55} />
        <Tooltip content={<Tip />} />
        <Legend wrapperStyle={{ fontSize: 12, color: '#94a3b8', paddingTop: 10 }} />
        <ReferenceLine y={startingCapital} stroke="#475569" strokeDasharray="4 3"
                       label={{ value: 'Start', fill: '#64748b', fontSize: 10, position: 'right' }} />
        <Area type="monotone" dataKey="Portfolio" stroke="#3b82f6" strokeWidth={2}
              fill="url(#portGrad)" dot={false} activeDot={{ r: 4 }} />
        {benchmarkData && (
          <Area type="monotone" dataKey="S&P 500" stroke="#f59e0b" strokeWidth={1.5}
                fill="url(#benchGrad)" dot={false} strokeDasharray="5 3" />
        )}
      </AreaChart>
    </ResponsiveContainer>
  )
}
