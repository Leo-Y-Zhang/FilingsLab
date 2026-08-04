import { useState } from 'react'
import { GitCompare, Play, Trophy, TrendingUp, Shield, BarChart2 } from 'lucide-react'
import { useTraders, useComparison } from '@/hooks/useApi'
import ComparisonChart from '@/components/Charts/ComparisonChart'
import { pct, currency, num } from '@/utils/format'
import clsx from 'clsx'
import type { ComparisonEntry } from '@/types'

const TRADER_COLOURS = ['#3b82f6', '#10b981', '#f59e0b', '#8b5cf6', '#ef4444', '#06b6d4']

const CATEGORY_STYLES: Record<string, string> = {
  politician: 'bg-purple-900/40 text-purple-300 border-purple-800/50',
  executive:  'bg-blue-900/40 text-blue-300 border-blue-800/50',
  insider:    'bg-orange-900/40 text-orange-300 border-orange-800/50',
}

function BadgeWinner({ label }: { label: string }) {
  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-amber-900/40 border border-amber-700/50 px-2 py-0.5 text-xs text-amber-300">
      <Trophy className="h-3 w-3" /> {label}
    </span>
  )
}

export default function Comparison() {
  const { data: traders, isLoading: loadingTraders } = useTraders()
  const { mutate: runComparison, data: result, isPending, reset } = useComparison()

  const [selected, setSelected] = useState<number[]>([])
  const [delayDays, setDelayDays] = useState(1)
  const [capital, setCapital] = useState(100_000)
  const [startDate, setStartDate] = useState('')
  const [endDate, setEndDate] = useState('')

  const toggleTrader = (id: number) => {
    setSelected(prev =>
      prev.includes(id)
        ? prev.filter(x => x !== id)
        : prev.length < 6
          ? [...prev, id]
          : prev
    )
    reset()
  }

  const canRun = selected.length >= 2 && !isPending

  const handleRun = () => {
    runComparison({
      trader_ids: selected,
      delay_days: delayDays,
      initial_capital: capital,
      start_date: startDate || undefined,
      end_date: endDate || undefined,
    })
  }

  // Assign colours consistently by position in selected array
  const colourMap = Object.fromEntries(selected.map((id, i) => [id, TRADER_COLOURS[i]]))

  return (
    <div className="space-y-8 animate-fade-in">
      {/* Header */}
      <div>
        <h1 className="flex items-center gap-2 text-2xl font-bold text-white sm:text-3xl">
          <GitCompare className="h-7 w-7 text-brand-400" />
          Multi-Trader Comparison
        </h1>
        <p className="mt-1 text-slate-400">
          Select 2–6 traders to run identical simulations side-by-side and compare portfolio growth,
          risk-adjusted returns, and signal quality.
        </p>
      </div>

      <div className="grid gap-8 lg:grid-cols-[1fr_320px]">
        {/* Left: trader selector + results */}
        <div className="space-y-6">

          {/* Trader checkboxes */}
          <div className="rounded-xl border border-surface-border bg-surface-card p-5">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-sm font-semibold text-slate-300">Select Traders</h2>
              <span className="text-xs text-slate-500">{selected.length}/6 selected</span>
            </div>

            {loadingTraders ? (
              <div className="grid gap-2 sm:grid-cols-2">
                {[1,2,3,4,5,6].map(i => (
                  <div key={i} className="h-12 animate-pulse rounded-lg bg-surface-elevated" />
                ))}
              </div>
            ) : (
              <div className="grid gap-2 sm:grid-cols-2">
                {traders?.map((trader) => {
                  const isSelected = selected.includes(trader.id)
                  const colour = colourMap[trader.id]
                  return (
                    <button
                      key={trader.id}
                      onClick={() => toggleTrader(trader.id)}
                      disabled={!isSelected && selected.length >= 6}
                      className={clsx(
                        'flex items-center gap-3 rounded-lg border px-3 py-2.5 text-left transition-all',
                        isSelected
                          ? 'border-transparent bg-surface-elevated shadow-inner'
                          : 'border-surface-border bg-transparent hover:border-slate-600 hover:bg-surface-elevated/50',
                        !isSelected && selected.length >= 6 && 'cursor-not-allowed opacity-40'
                      )}
                    >
                      {/* Colour swatch / checkbox */}
                      <span
                        className="flex h-4 w-4 shrink-0 items-center justify-center rounded border-2 transition-colors"
                        style={isSelected
                          ? { backgroundColor: colour, borderColor: colour }
                          : { borderColor: '#475569' }
                        }
                      >
                        {isSelected && (
                          <svg className="h-2.5 w-2.5 text-white" viewBox="0 0 10 8" fill="currentColor">
                            <path d="M1 4l3 3 5-6" stroke="currentColor" strokeWidth="1.5" fill="none" strokeLinecap="round" strokeLinejoin="round"/>
                          </svg>
                        )}
                      </span>

                      <div className="min-w-0">
                        <p className="truncate text-sm font-medium text-slate-200">{trader.name}</p>
                        <div className="flex items-center gap-1.5 mt-0.5">
                          <span className={clsx(
                            'rounded-full border px-1.5 py-px text-xs capitalize',
                            CATEGORY_STYLES[trader.category] ?? 'bg-slate-800 text-slate-300 border-slate-700'
                          )}>
                            {trader.category}
                          </span>
                          {trader.party && (
                            <span className="text-xs text-slate-600">{trader.party}</span>
                          )}
                        </div>
                      </div>

                      <span className="ml-auto shrink-0 font-mono text-xs text-slate-500">
                        {trader.trade_count ?? 0}
                      </span>
                    </button>
                  )
                })}
              </div>
            )}
          </div>

          {/* Chart */}
          {result && (
            <div className="rounded-xl border border-surface-border bg-surface-card p-5 space-y-4">
              <h2 className="text-sm font-semibold text-slate-300">Portfolio Growth Overlay</h2>
              <div className="h-80">
                <ComparisonChart
                  entries={result.entries}
                  colours={colourMap}
                  bestTraderId={result.best_trader_id}
                  initialCapital={result.initial_capital}
                />
              </div>
              {result.benchmark_return_pct !== undefined && (
                <p className="text-xs text-slate-500 text-center">
                  Benchmark (S&amp;P 500 proxy): <span className="font-mono text-slate-300">{pct(result.benchmark_return_pct)}</span> over the period
                </p>
              )}
            </div>
          )}

          {/* Side-by-side metrics table */}
          {result && result.entries.length > 0 && (
            <div className="rounded-xl border border-surface-border bg-surface-card overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-surface-border">
                    <th className="px-4 py-3 text-left text-xs font-medium text-slate-400">Trader</th>
                    <th className="px-4 py-3 text-right text-xs font-medium text-slate-400">Total Ret.</th>
                    <th className="px-4 py-3 text-right text-xs font-medium text-slate-400">Ann. Ret.</th>
                    <th className="px-4 py-3 text-right text-xs font-medium text-slate-400">Sharpe</th>
                    <th className="px-4 py-3 text-right text-xs font-medium text-slate-400">Sortino</th>
                    <th className="px-4 py-3 text-right text-xs font-medium text-slate-400">Drawdown</th>
                    <th className="px-4 py-3 text-right text-xs font-medium text-slate-400">Win Rate</th>
                    <th className="px-4 py-3 text-right text-xs font-medium text-slate-400">Trades</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-surface-border">
                  {result.entries
                    .slice()
                    .sort((a, b) => b.total_return_pct - a.total_return_pct)
                    .map((entry: ComparisonEntry) => {
                      const colour = colourMap[entry.trader_id]
                      const isBestReturn  = entry.trader_id === result.best_trader_id
                      const isBestSharpe  = entry.trader_id === result.best_sharpe_trader_id
                      const isBestSortino = entry.trader_id === result.best_sortino_trader_id
                      return (
                        <tr key={entry.trader_id} className="hover:bg-surface-elevated/50 transition-colors">
                          <td className="px-4 py-3">
                            <div className="flex items-center gap-2">
                              <span
                                className="h-2.5 w-2.5 rounded-full shrink-0"
                                style={{ backgroundColor: colour }}
                              />
                              <div>
                                <p className="font-medium text-slate-200">{entry.name}</p>
                                <div className="flex flex-wrap gap-1 mt-0.5">
                                  {isBestReturn  && <BadgeWinner label="Best Return" />}
                                  {isBestSharpe  && <BadgeWinner label="Best Sharpe" />}
                                  {isBestSortino && <BadgeWinner label="Best Sortino" />}
                                </div>
                              </div>
                            </div>
                          </td>
                          <td className={clsx(
                            'px-4 py-3 text-right font-mono font-semibold',
                            entry.total_return_pct >= 0 ? 'text-emerald-400' : 'text-red-400'
                          )}>
                            {pct(entry.total_return_pct)}
                          </td>
                          <td className={clsx(
                            'px-4 py-3 text-right font-mono',
                            entry.annualized_return_pct >= 0 ? 'text-emerald-400' : 'text-red-400'
                          )}>
                            {pct(entry.annualized_return_pct)}
                          </td>
                          <td className="px-4 py-3 text-right font-mono text-slate-300">
                            {num(entry.sharpe_ratio)}
                          </td>
                          <td className="px-4 py-3 text-right font-mono text-slate-300">
                            {num(entry.sortino_ratio)}
                          </td>
                          <td className="px-4 py-3 text-right font-mono text-red-400">
                            {pct(entry.max_drawdown_pct)}
                          </td>
                          <td className="px-4 py-3 text-right font-mono text-slate-300">
                            {pct(entry.win_rate * 100)}
                          </td>
                          <td className="px-4 py-3 text-right font-mono text-slate-400">
                            {entry.executed_trade_count}/{entry.trade_count}
                          </td>
                        </tr>
                      )
                    })}
                </tbody>
              </table>
            </div>
          )}

          {/* Winner summary cards */}
          {result && (
            <div className="grid gap-4 sm:grid-cols-3">
              {[
                {
                  icon: TrendingUp,
                  label: 'Best Total Return',
                  entry: result.entries.find(e => e.trader_id === result.best_trader_id),
                  value: (e: ComparisonEntry) => pct(e.total_return_pct),
                  colour: 'text-emerald-400',
                },
                {
                  icon: BarChart2,
                  label: 'Best Sharpe Ratio',
                  entry: result.entries.find(e => e.trader_id === result.best_sharpe_trader_id),
                  value: (e: ComparisonEntry) => num(e.sharpe_ratio),
                  colour: 'text-blue-400',
                },
                {
                  icon: Shield,
                  label: 'Best Sortino Ratio',
                  entry: result.entries.find(e => e.trader_id === result.best_sortino_trader_id),
                  value: (e: ComparisonEntry) => num(e.sortino_ratio),
                  colour: 'text-purple-400',
                },
              ].map(({ icon: Icon, label, entry, value, colour }) => (
                <div key={label} className="rounded-xl border border-surface-border bg-surface-card p-4">
                  <div className="flex items-center gap-2 mb-2">
                    <Icon className={clsx('h-4 w-4', colour)} />
                    <p className="text-xs text-slate-400">{label}</p>
                  </div>
                  {entry ? (
                    <>
                      <div className="flex items-center gap-2">
                        <span
                          className="h-2 w-2 rounded-full"
                          style={{ backgroundColor: colourMap[entry.trader_id] }}
                        />
                        <p className="font-semibold text-white truncate">{entry.name}</p>
                      </div>
                      <p className={clsx('text-2xl font-bold font-mono mt-1', colour)}>
                        {value(entry)}
                      </p>
                    </>
                  ) : (
                    <p className="text-slate-500 text-sm">—</p>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Right: config panel */}
        <aside className="space-y-5">
          <div className="rounded-xl border border-surface-border bg-surface-card p-5 space-y-4">
            <h2 className="text-sm font-semibold text-slate-300">Simulation Config</h2>

            <div className="space-y-1">
              <label className="text-xs text-slate-400">Execution Delay (days)</label>
              <input
                type="number"
                min={0}
                max={365}
                value={delayDays}
                onChange={e => { setDelayDays(Number(e.target.value)); reset() }}
                className="w-full rounded-lg border border-surface-border bg-surface-elevated px-3 py-2 text-sm text-white outline-none focus:border-brand-500 focus:ring-1 focus:ring-brand-500/30"
              />
              <p className="text-xs text-slate-600">Days after disclosure before execution</p>
            </div>

            <div className="space-y-1">
              <label className="text-xs text-slate-400">Starting Capital</label>
              <div className="relative">
                <span className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500 text-sm">$</span>
                <input
                  type="number"
                  min={1000}
                  step={1000}
                  value={capital}
                  onChange={e => { setCapital(Number(e.target.value)); reset() }}
                  className="w-full rounded-lg border border-surface-border bg-surface-elevated pl-7 pr-3 py-2 text-sm text-white outline-none focus:border-brand-500 focus:ring-1 focus:ring-brand-500/30"
                />
              </div>
              <p className="text-xs text-slate-600">{currency(capital)} per trader</p>
            </div>

            <div className="space-y-1">
              <label className="text-xs text-slate-400">Start Date <span className="text-slate-600">(optional)</span></label>
              <input
                type="date"
                value={startDate}
                onChange={e => { setStartDate(e.target.value); reset() }}
                className="w-full rounded-lg border border-surface-border bg-surface-elevated px-3 py-2 text-sm text-white outline-none focus:border-brand-500 focus:ring-1 focus:ring-brand-500/30"
              />
            </div>

            <div className="space-y-1">
              <label className="text-xs text-slate-400">End Date <span className="text-slate-600">(optional)</span></label>
              <input
                type="date"
                value={endDate}
                onChange={e => { setEndDate(e.target.value); reset() }}
                className="w-full rounded-lg border border-surface-border bg-surface-elevated px-3 py-2 text-sm text-white outline-none focus:border-brand-500 focus:ring-1 focus:ring-brand-500/30"
              />
            </div>

            <button
              onClick={handleRun}
              disabled={!canRun}
              className={clsx(
                'flex w-full items-center justify-center gap-2 rounded-lg px-4 py-2.5 text-sm font-semibold transition-all',
                canRun
                  ? 'bg-brand-600 text-white hover:bg-brand-500 active:scale-[0.98]'
                  : 'bg-surface-elevated text-slate-600 cursor-not-allowed'
              )}
            >
              {isPending ? (
                <>
                  <span className="h-4 w-4 animate-spin rounded-full border-2 border-white/30 border-t-white" />
                  Running...
                </>
              ) : (
                <>
                  <Play className="h-4 w-4" />
                  {selected.length < 2 ? `Select ${2 - selected.length} more` : `Compare ${selected.length} Traders`}
                </>
              )}
            </button>

            {selected.length > 0 && (
              <div className="space-y-1.5 pt-1">
                <p className="text-xs text-slate-500">Selected:</p>
                {selected.map((id, i) => {
                  const trader = traders?.find(t => t.id === id)
                  return (
                    <div key={id} className="flex items-center gap-2">
                      <span
                        className="h-2 w-2 rounded-full shrink-0"
                        style={{ backgroundColor: TRADER_COLOURS[i] }}
                      />
                      <span className="text-xs text-slate-300 truncate">{trader?.name ?? `Trader #${id}`}</span>
                    </div>
                  )
                })}
              </div>
            )}
          </div>

          {/* Info box */}
          <div className="rounded-xl border border-surface-border bg-surface-card/50 p-4 space-y-2">
            <p className="text-xs font-semibold text-slate-400">How it works</p>
            <ul className="space-y-1.5 text-xs text-slate-500 list-disc list-inside">
              <li>Each trader runs an identical simulation with the same config</li>
              <li>Execution uses <span className="text-slate-400">disclosure date + delay</span>, not the trade date</li>
              <li>Portfolio histories are overlaid on the same chart for direct comparison</li>
              <li>Sortino ratio penalises downside volatility only — a fairer risk measure</li>
              <li>Winners are highlighted across return, Sharpe, and Sortino dimensions</li>
            </ul>
          </div>
        </aside>
      </div>
    </div>
  )
}
