import { Link } from 'react-router'
import { ArrowRight, TrendingUp, FlaskConical, GitCompare, AlertTriangle, BarChart2, Zap } from 'lucide-react'
import { useRankings } from '@/hooks/useApi'
import MetricCard from '@/components/Cards/MetricCard'
import { pct, pctRaw, fmt2 } from '@/utils/format'
import clsx from 'clsx'

const CATEGORY_BADGE: Record<string, string> = {
  politician: 'bg-purple-900/40 text-purple-300 border-purple-800/40',
  executive:  'bg-blue-900/40 text-blue-300 border-blue-800/40',
  insider:    'bg-orange-900/40 text-orange-300 border-orange-800/40',
}

const STAT_CARDS = [
  { icon: TrendingUp, label: 'Methodology', value: 'Excess Return', sub: 'vs S&P 500 benchmark', color: 'text-brand-400' },
  { icon: BarChart2,  label: 'Risk Model',  value: 'Sharpe + Sortino', sub: 'risk-adjusted metrics', color: 'text-emerald-400' },
  { icon: Zap,        label: 'Alpha Signal', value: 'Disclosure Lag', sub: 'days post-filing', color: 'text-amber-400' },
  { icon: AlertTriangle, label: 'Disclaimer', value: 'Research Only', sub: 'not financial advice', color: 'text-red-400' },
]

export default function Dashboard() {
  const { data: rankings, isLoading } = useRankings(undefined, 10)
  const top = rankings?.[0]

  const avgExcess = rankings?.length
    ? rankings.reduce((s, r) => s + (Number(r.excess_return ?? 0) * 100), 0) / rankings.length
    : null

  const outperformers = rankings?.filter(r => (r.excess_return ?? 0) > 0).length ?? 0

  return (
    <div className="space-y-8 animate-fade-in">

      {/* Research context strip */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {STAT_CARDS.map(({ icon: Icon, label, value, sub, color }) => (
          <div key={label} className="flex items-start gap-3 rounded-xl border border-surface-border bg-surface-card px-4 py-3">
            <Icon className={clsx('mt-0.5 h-4 w-4 shrink-0', color)} />
            <div className="min-w-0">
              <p className="text-xs font-semibold uppercase tracking-widest text-slate-500">{label}</p>
              <p className="mt-0.5 text-sm font-bold text-white truncate">{value}</p>
              <p className="text-xs text-slate-500">{sub}</p>
            </div>
          </div>
        ))}
      </div>

      {/* Hero */}
      <div className="rounded-2xl border border-surface-border bg-gradient-to-br from-surface-card via-surface-card to-brand-950/20 p-6 sm:p-8 relative overflow-hidden">
        {/* Background accent */}
        <div className="absolute inset-0 bg-gradient-to-r from-transparent to-brand-900/10 pointer-events-none" />
        <div className="relative flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <div className="flex items-center gap-2 mb-2">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-pulse" />
              <span className="text-xs font-mono text-emerald-400 uppercase tracking-widest">Live Research</span>
            </div>
            <h1 className="text-2xl font-bold text-white sm:text-3xl tracking-tight">FilingsLab</h1>
            <p className="mt-2 text-slate-400 max-w-xl text-sm leading-relaxed">
              Investigating whether publicly disclosed trades by politicians, executives, and
              insiders contain statistically significant excess returns — accounting for
              disclosure delays and market frictions.
            </p>
          </div>
          <div className="flex gap-2">
            <Link to="/research"
                  className="flex items-center gap-2 rounded-xl bg-brand-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-brand-500 transition-colors shrink-0">
              <FlaskConical className="h-4 w-4" />
              Research Lab
            </Link>
            <Link to="/compare"
                  className="flex items-center gap-2 rounded-xl border border-surface-border bg-surface-card px-4 py-2.5 text-sm font-semibold text-slate-300 hover:border-brand-600/50 hover:text-white transition-all shrink-0">
              <GitCompare className="h-4 w-4" />
              Compare
            </Link>
          </div>
        </div>

        <div className="mt-6 grid grid-cols-2 gap-3 sm:grid-cols-4">
          <MetricCard
            label="Top Ranked Return"
            value={isLoading ? '…' : pctRaw(top?.total_return)}
            subtitle={top?.name ?? ''}
            trend={(Number(top?.total_return ?? 0)) > 0 ? 'up' : 'down'}
            highlight
          />
          <MetricCard
            label="Avg Excess Return"
            value={isLoading ? '…' : pct(avgExcess)}
            subtitle="vs S&P 500 benchmark"
            trend={(avgExcess ?? 0) > 0 ? 'up' : 'down'}
          />
          <MetricCard
            label="Outperformers"
            value={isLoading ? '…' : `${outperformers} / ${rankings?.length ?? 0}`}
            subtitle="beat benchmark"
          />
          <MetricCard
            label="Top Sharpe"
            value={isLoading ? '…' : fmt2(rankings?.[0]?.sharpe_ratio)}
            subtitle="risk-adjusted return"
          />
        </div>
      </div>

      {/* Rankings table */}
      <div>
        <div className="mb-4 flex items-center justify-between">
          <h2 className="flex items-center gap-2 text-lg font-semibold text-white">
            <TrendingUp className="h-5 w-5 text-brand-400" />
            Leaderboard
          </h2>
          <Link to="/rankings" className="flex items-center gap-1 text-sm text-brand-400 hover:text-brand-300 transition-colors">
            Full rankings <ArrowRight className="h-3.5 w-3.5" />
          </Link>
        </div>

        <div className="overflow-x-auto rounded-xl border border-surface-border bg-surface-card">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-surface-border text-xs font-medium uppercase tracking-wider text-slate-500">
                <th className="p-4 text-left">#</th>
                <th className="p-4 text-left">Trader</th>
                <th className="p-4 text-right">Total Return</th>
                <th className="p-4 text-right">Excess</th>
                <th className="p-4 text-right">Sharpe</th>
                <th className="p-4 text-right">Sortino</th>
                <th className="p-4 text-right">Score</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-surface-border/40">
              {isLoading
                ? [1,2,3,4,5].map(i => (
                    <tr key={i}><td colSpan={7} className="p-4"><div className="h-4 animate-pulse rounded bg-surface-elevated" /></td></tr>
                  ))
                : rankings?.map(r => (
                    <tr key={r.trader_id} className="hover:bg-surface-elevated/20 transition-colors">
                      <td className="p-4">
                        <span className={clsx(
                          'flex h-6 w-6 items-center justify-center rounded-full text-xs font-bold',
                          r.rank <= 3 ? 'bg-brand-600 text-white' : 'bg-surface-elevated text-slate-400',
                        )}>{r.rank}</span>
                      </td>
                      <td className="p-4">
                        <Link to={`/traders/${r.trader_id}`} className="font-medium text-white hover:text-brand-300 transition-colors">
                          {r.name}
                        </Link>
                        <div className="mt-0.5 flex items-center gap-1.5">
                          <span className={clsx(
                            'rounded-full border px-1.5 py-0 text-xs capitalize',
                            CATEGORY_BADGE[r.category] ?? 'bg-slate-800 text-slate-400',
                          )}>{r.category}</span>
                          {r.state && <span className="text-xs text-slate-500">{r.state}</span>}
                        </div>
                      </td>
                      <td className={clsx('p-4 text-right font-mono font-semibold',
                        (r.total_return ?? 0) >= 0 ? 'text-emerald-400' : 'text-red-400')}>
                        {pctRaw(r.total_return)}
                      </td>
                      <td className={clsx('p-4 text-right font-mono text-sm',
                        (r.excess_return ?? 0) >= 0 ? 'text-emerald-400' : 'text-red-400')}>
                        {pctRaw(r.excess_return)}
                      </td>
                      <td className="p-4 text-right font-mono text-slate-300">{fmt2(r.sharpe_ratio)}</td>
                      <td className="p-4 text-right font-mono text-slate-300">{fmt2(r.sortino_ratio)}</td>
                      <td className="p-4 text-right font-mono text-brand-400 text-sm">
                        {r.ranking_score ? (Number(r.ranking_score) * 100).toFixed(1) : '—'}
                      </td>
                    </tr>
                  ))
              }
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
