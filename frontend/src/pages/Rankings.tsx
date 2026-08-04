import { useState } from 'react'
import { Trophy } from 'lucide-react'
import { useRankings } from '@/hooks/useApi'
import { Link } from 'react-router'
import { pctRaw, fmt2 } from '@/utils/format'
import clsx from 'clsx'

const CATS = ['all', 'politician', 'executive', 'insider']

export default function Rankings() {
  const [category, setCategory] = useState<string | undefined>()
  const { data: rankings, isLoading } = useRankings(category, 50)

  return (
    <div className="space-y-6 animate-fade-in">
      <div>
        <h1 className="flex items-center gap-2 text-2xl font-bold text-white sm:text-3xl">
          <Trophy className="h-7 w-7 text-amber-400" />
          Trader Rankings
        </h1>
        <p className="mt-1 text-slate-400">
          Composite score = 0.35 × return + 0.30 × sharpe − 0.20 × drawdown + 0.15 × win_rate.
          All metrics normalised across the trader population.
        </p>
      </div>

      <div className="flex flex-wrap gap-2">
        {CATS.map(cat => (
          <button key={cat} onClick={() => setCategory(cat === 'all' ? undefined : cat)}
                  className={clsx('rounded-full px-3 py-1.5 text-xs font-medium capitalize transition-colors',
                    (category === cat || (cat === 'all' && !category))
                      ? 'bg-brand-600 text-white'
                      : 'bg-surface-card text-slate-400 hover:bg-surface-elevated hover:text-white')}>
            {cat}
          </button>
        ))}
      </div>

      <div className="overflow-x-auto rounded-xl border border-surface-border bg-surface-card">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-surface-border text-xs font-medium uppercase tracking-wider text-slate-500">
              {['#','Trader','Category','Score','Return','Excess','Sharpe','Sortino','Drawdown','Win Rate'].map(h => (
                <th key={h} className={clsx('p-4', h === '#' || h === 'Trader' || h === 'Category' ? 'text-left' : 'text-right')}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-surface-border/40">
            {isLoading
              ? [1,2,3,4,5].map(i => <tr key={i}><td colSpan={10} className="p-4"><div className="h-4 animate-pulse rounded bg-surface-elevated" /></td></tr>)
              : rankings?.map(r => (
                  <tr key={r.trader_id} className="hover:bg-surface-elevated/20 transition-colors">
                    <td className="p-4">
                      <span className={clsx('flex h-6 w-6 items-center justify-center rounded-full text-xs font-bold',
                        r.rank <= 3 ? 'bg-brand-600 text-white' : 'bg-surface-elevated text-slate-400')}>{r.rank}</span>
                    </td>
                    <td className="p-4">
                      <Link to={`/traders/${r.trader_id}`} className="font-medium text-white hover:text-brand-300 transition-colors">
                        {r.name}
                      </Link>
                    </td>
                    <td className="p-4"><span className="capitalize text-xs text-slate-400">{r.category}</span></td>
                    <td className="p-4 text-right font-mono text-brand-400 text-xs">
                      {r.ranking_score ? (Number(r.ranking_score) * 100).toFixed(1) : '—'}
                    </td>
                    <td className={clsx('p-4 text-right font-mono', (r.total_return ?? 0) >= 0 ? 'text-emerald-400' : 'text-red-400')}>
                      {pctRaw(r.total_return)}
                    </td>
                    <td className={clsx('p-4 text-right font-mono text-xs', (r.excess_return ?? 0) >= 0 ? 'text-emerald-500' : 'text-red-500')}>
                      {pctRaw(r.excess_return)}
                    </td>
                    <td className="p-4 text-right font-mono text-slate-300">{fmt2(r.sharpe_ratio)}</td>
                    <td className="p-4 text-right font-mono text-slate-300">{fmt2(r.sortino_ratio)}</td>
                    <td className="p-4 text-right font-mono text-red-400">{pctRaw(r.max_drawdown)}</td>
                    <td className="p-4 text-right font-mono text-slate-300">
                      {r.win_rate ? `${(Number(r.win_rate) * 100).toFixed(1)}%` : '—'}
                    </td>
                  </tr>
                ))
            }
          </tbody>
        </table>
      </div>
    </div>
  )
}
