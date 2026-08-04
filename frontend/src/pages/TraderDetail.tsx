import { useParams, Link } from 'react-router'
import { ArrowLeft, Calendar, Clock } from 'lucide-react'
import { useTrader, useTraderTrades, useAlphaDecay } from '@/hooks/useApi'
import MetricCard from '@/components/Cards/MetricCard'
import AlphaDecayChart from '@/components/Charts/AlphaDecayChart'
import Disclaimer from '@/components/Disclaimer'
import { pctRaw, fmt2, fmtDate, currency } from '@/utils/format'
import clsx from 'clsx'

export default function TraderDetail() {
  const { id } = useParams<{ id: string }>()
  const traderId = Number(id)

  const { data: trader, isLoading } = useTrader(traderId)
  const { data: trades } = useTraderTrades(traderId)
  const { data: alphaDecay, isLoading: decayLoading } = useAlphaDecay(traderId)

  if (isLoading) {
    return <div className="space-y-4 animate-pulse">{[1,2,3].map(i => <div key={i} className="h-32 rounded-xl bg-surface-card" />)}</div>
  }
  if (!trader) {
    return <div className="text-red-400 p-6">Trader not found. <Link to="/" className="underline">Home</Link></div>
  }

  const perf = trader.performance
  const returnPos = (Number(perf?.total_return ?? 0)) >= 0
  const excessPos = (Number(perf?.total_return ?? 0) - Number(perf?.benchmark_return ?? 0)) >= 0

  return (
    <div className="space-y-6 animate-fade-in">
      <Link to="/traders" className="flex items-center gap-1.5 text-sm text-slate-400 hover:text-white transition-colors">
        <ArrowLeft className="h-4 w-4" /> All Traders
      </Link>

      {/* Header */}
      <div className="rounded-xl border border-surface-border bg-surface-card p-6">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <h1 className="text-2xl font-bold text-white sm:text-3xl">{trader.name}</h1>
            <div className="mt-1.5 flex flex-wrap items-center gap-2 text-sm text-slate-400">
              <span className="capitalize rounded-full border border-slate-700 bg-slate-800 px-2.5 py-0.5 text-xs">{trader.category}</span>
              {trader.party && <span>{trader.party}</span>}
              {trader.state && <span>· {trader.state}</span>}
            </div>
            {trader.bio && <p className="mt-2 text-sm text-slate-400 leading-relaxed max-w-xl">{trader.bio}</p>}
          </div>
          <div className="text-right shrink-0">
            <div className={clsx('text-3xl font-bold font-mono', returnPos ? 'text-emerald-400' : 'text-red-400')}>
              {pctRaw(perf?.total_return)}
            </div>
            <p className="text-xs text-slate-500">Total Simulated Return</p>
            <div className={clsx('mt-1 text-sm font-mono', excessPos ? 'text-emerald-500' : 'text-red-500')}>
              {pctRaw(perf?.total_return && perf?.benchmark_return
                ? Number(perf.total_return) - Number(perf.benchmark_return) : null)} vs benchmark
            </div>
          </div>
        </div>
      </div>

      {/* Performance metrics */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-7">
        <MetricCard label="Ann. Return"   value={pctRaw(perf?.annualized_return)} trend={returnPos ? 'up' : 'down'} />
        <MetricCard label="Sharpe Ratio"  value={fmt2(perf?.sharpe_ratio)} subtitle="risk-adj" />
        <MetricCard label="Sortino Ratio" value={fmt2(perf?.sortino_ratio)} subtitle="downside-adj" />
        <MetricCard label="Max Drawdown"  value={pctRaw(perf?.max_drawdown)} trend="down" />
        <MetricCard label="Volatility"    value={pctRaw(perf?.volatility)} subtitle="annualised" />
        <MetricCard label="Win Rate"      value={perf?.win_rate ? `${(Number(perf.win_rate)*100).toFixed(1)}%` : '—'}
                    trend={(Number(perf?.win_rate ?? 0)) > 0.5 ? 'up' : 'down'} />
        <MetricCard label="Trades Filed"  value={perf?.trade_count ?? trader.trade_count ?? '—'} subtitle={`delay: ${perf?.delay_days_used ?? 1}d`} />
      </div>

      <Disclaimer compact />

      {/* Alpha decay */}
      <div className="rounded-xl border border-surface-border bg-surface-card p-5">
        <div className="mb-4 flex items-center justify-between">
          <div>
            <h2 className="font-semibold text-white">Alpha Decay Analysis</h2>
            <p className="text-xs text-slate-500 mt-0.5">Simulated excess return as a function of execution delay</p>
          </div>
          {alphaDecay?.half_life_days && (
            <div className="text-right">
              <span className="text-xs text-slate-500">Est. half-life</span>
              <p className="font-mono font-semibold text-amber-400">{alphaDecay.half_life_days}d</p>
            </div>
          )}
        </div>
        <div className="h-52">
          {decayLoading ? (
            <div className="h-full animate-pulse rounded-lg bg-surface-elevated" />
          ) : alphaDecay ? (
            <AlphaDecayChart result={alphaDecay} />
          ) : (
            <div className="flex h-full items-center justify-center text-sm text-slate-500">
              No alpha decay data available
            </div>
          )}
        </div>
      </div>

      {/* CTAs */}
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="rounded-xl border border-brand-700/40 bg-brand-950/20 p-4 flex items-center justify-between gap-4">
          <div>
            <p className="font-semibold text-white">Run a Portfolio Simulation</p>
            <p className="text-xs text-slate-400">Configure delay, costs, and allocation strategy</p>
          </div>
          <Link to={`/simulate?trader=${traderId}`}
                className="shrink-0 rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-500 transition-colors">
            Simulate →
          </Link>
        </div>
        <div className="rounded-xl border border-surface-border bg-surface-card p-4 flex items-center justify-between gap-4">
          <div>
            <p className="font-semibold text-white">Compare with Others</p>
            <p className="text-xs text-slate-400">Side-by-side metrics and portfolio overlay</p>
          </div>
          <Link to={`/compare?preselect=${traderId}`}
                className="shrink-0 rounded-lg border border-surface-border bg-surface-elevated px-4 py-2 text-sm font-medium text-slate-300 hover:text-white transition-colors">
            Compare →
          </Link>
        </div>
      </div>

      {/* Trade table */}
      <div>
        <h2 className="mb-3 text-lg font-semibold text-white">Disclosure History</h2>
        <div className="overflow-x-auto rounded-xl border border-surface-border bg-surface-card">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-surface-border text-slate-500 font-medium uppercase tracking-wider">
                {['Symbol','Asset','Type','Trade Date','Disclosed','Delay','Est. Value','Range'].map(h => (
                  <th key={h} className={clsx('p-3', h === 'Est. Value' ? 'text-right' : 'text-left')}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-surface-border/40">
              {trades?.map(t => (
                <tr key={t.id} className="hover:bg-surface-elevated/20">
                  <td className="p-3 font-mono font-semibold text-brand-300">{t.asset_symbol}</td>
                  <td className="p-3 text-slate-300 max-w-[140px] truncate">{t.asset_name || '—'}</td>
                  <td className="p-3">
                    <span className={clsx('rounded-full px-2 py-0.5 font-medium capitalize',
                      t.transaction_type === 'buy' ? 'bg-emerald-900/40 text-emerald-400' : 'bg-red-900/40 text-red-400')}>
                      {t.transaction_type}
                    </span>
                  </td>
                  <td className="p-3 text-slate-400 whitespace-nowrap">
                    <span className="flex items-center gap-1"><Calendar className="h-3 w-3 text-slate-600" />{fmtDate(t.trade_date)}</span>
                  </td>
                  <td className="p-3 text-slate-400 whitespace-nowrap">{fmtDate(t.disclosure_date)}</td>
                  <td className="p-3">
                    <span className="flex items-center gap-1 text-slate-500">
                      <Clock className="h-3 w-3" />{t.disclosure_delay_days ?? '—'}d
                    </span>
                  </td>
                  <td className="p-3 text-right font-mono text-slate-300">
                    {t.value_estimate ? currency(Number(t.value_estimate)) : '—'}
                  </td>
                  <td className="p-3 text-slate-500 max-w-[130px] truncate">{t.value_range_label || '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
