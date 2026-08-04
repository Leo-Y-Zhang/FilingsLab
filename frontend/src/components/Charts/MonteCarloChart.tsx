import {
  ResponsiveContainer, LineChart, Line, BarChart, Bar,
  XAxis, YAxis, CartesianGrid, Tooltip, Legend, ReferenceLine, Cell,
} from 'recharts'
import type { MonteCarloResult } from '@/types'
import { currency } from '@/utils/format'

interface Props {
  result: MonteCarloResult
  view: 'paths' | 'distribution'
}

function buildHistogramData(runs: MonteCarloResult['runs'], bins = 25) {
  const values = runs.map(r => r.total_return_pct)
  const min = Math.min(...values)
  const max = Math.max(...values)
  const binWidth = (max - min) / bins

  return Array.from({ length: bins }, (_, i) => {
    const lo = min + i * binWidth
    const hi = lo + binWidth
    const count = values.filter(v => v >= lo && (i === bins - 1 ? v <= hi : v < hi)).length
    return { label: `${lo.toFixed(1)}%`, count, midpoint: (lo + hi) / 2 }
  })
}

function PathsChart({ result }: { result: MonteCarloResult }) {
  const MAX_POINTS = 300
  const step = Math.max(1, Math.floor(result.best_history.length / MAX_POINTS))

  const data = result.median_history
    .filter((_, i) => i % step === 0)
    .map((pt, idx) => {
      const bidx = idx * step
      return {
        date: pt.date,
        'Median': pt.portfolio_value,
        'Best':   result.best_history[Math.min(bidx, result.best_history.length - 1)]?.portfolio_value ?? pt.portfolio_value,
        'Worst':  result.worst_history[Math.min(bidx, result.worst_history.length - 1)]?.portfolio_value ?? pt.portfolio_value,
      }
    })

  return (
    <ResponsiveContainer width="100%" height="100%">
      <LineChart data={data} margin={{ top: 10, right: 10, bottom: 0, left: 10 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#334155" vertical={false} />
        <XAxis dataKey="date" tick={{ fill: '#94a3b8', fontSize: 10 }} tickLine={false} axisLine={false}
               tickFormatter={v => v.slice(0, 7)} interval="preserveStartEnd" />
        <YAxis tick={{ fill: '#94a3b8', fontSize: 10 }} tickLine={false} axisLine={false}
               tickFormatter={v => typeof v === 'number' ? `$${(v / 1000).toFixed(0)}k` : ''} width={55} />
        <Tooltip formatter={(v: number) => currency(v)} labelFormatter={l => `Date: ${l}`}
                 contentStyle={{ background: '#1e293b', border: '1px solid #475569', borderRadius: 8, fontSize: 12 }} />
        <Legend wrapperStyle={{ fontSize: 12, color: '#94a3b8', paddingTop: 8 }} />
        <ReferenceLine y={result.config.initial_capital} stroke="#475569" strokeDasharray="4 4" />
        <Line type="monotone" dataKey="Best"   stroke="#10b981" strokeWidth={1.5} dot={false} />
        <Line type="monotone" dataKey="Median" stroke="#3b82f6" strokeWidth={2}   dot={false} />
        <Line type="monotone" dataKey="Worst"  stroke="#ef4444" strokeWidth={1.5} dot={false} />
      </LineChart>
    </ResponsiveContainer>
  )
}

function DistributionChart({ result }: { result: MonteCarloResult }) {
  const histData = buildHistogramData(result.runs)
  return (
    <ResponsiveContainer width="100%" height="100%">
      <BarChart data={histData} margin={{ top: 10, right: 10, bottom: 20, left: 10 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#334155" vertical={false} />
        <XAxis dataKey="label" tick={{ fill: '#94a3b8', fontSize: 9 }} tickLine={false} axisLine={false}
               interval={Math.floor(histData.length / 8)} />
        <YAxis tick={{ fill: '#94a3b8', fontSize: 10 }} tickLine={false} axisLine={false} width={40} />
        <Tooltip formatter={(v: number, _: string, props: any) => [`${v} runs`, `~${props.payload.midpoint.toFixed(1)}%`]}
                 contentStyle={{ background: '#1e293b', border: '1px solid #475569', borderRadius: 8, fontSize: 12 }} />
        <Bar dataKey="count" radius={[3, 3, 0, 0]}>
          {histData.map((entry, i) => (
            <Cell key={i} fill={entry.midpoint >= 0 ? '#3b82f6' : '#ef4444'} fillOpacity={0.8} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  )
}

export default function MonteCarloChart({ result, view }: Props) {
  return view === 'paths' ? <PathsChart result={result} /> : <DistributionChart result={result} />
}
