import { useState, useEffect } from 'react'
import { useSearchParams } from 'react-router'
import { Activity, Play, Shuffle, AlertCircle, ChevronDown, ChevronUp } from 'lucide-react'
import { useTraders, useSimulation, useMonteCarlo } from '@/hooks/useApi'
import PortfolioChart from '@/components/Charts/PortfolioChart'
import MonteCarloChart from '@/components/Charts/MonteCarloChart'
import MetricCard from '@/components/Cards/MetricCard'
import Disclaimer from '@/components/Disclaimer'
import { pct, currency, fmt2 } from '@/utils/format'
import type { SimulationConfig, MonteCarloConfig } from '@/types'
import clsx from 'clsx'

type Mode = 'single' | 'montecarlo'
type MCView = 'paths' | 'distribution'

export default function Simulation() {
  const [params] = useSearchParams()
  const { data: traders } = useTraders()

  const [mode, setMode] = useState<Mode>('single')
  const [mcView, setMcView] = useState<MCView>('paths')
  const [showAdvanced, setShowAdvanced] = useState(false)

  const [traderId, setTraderId] = useState(0)
  const [capital, setCapital] = useState(100_000)
  const [delay, setDelay] = useState(1)
  const [strategy, setStrategy] = useState<'proportional' | 'equal_weight'>('proportional')
  const [txCost, setTxCost] = useState(0.001)
  const [slippage, setSlippage] = useState(0.0005)
  const [nRuns, setNRuns] = useState(300)
  const [valueMethod, setValueMethod] = useState<'midpoint' | 'probabilistic'>('probabilistic')

  const { mutate: runSim,  isPending: simPending,  error: simError,  data: simResult } = useSimulation()
  const { mutate: runMC,   isPending: mcPending,   error: mcError,   data: mcResult  } = useMonteCarlo()

  useEffect(() => {
    const pre = params.get('trader')
    if (pre) setTraderId(Number(pre))
    else if (traders?.length) setTraderId(traders[0].id)
  }, [traders, params])

  const handleRun = () => {
    if (!traderId) return
    const base: SimulationConfig = {
      trader_id: traderId,
      initial_capital: capital,
      delay_days: delay,
      allocation_strategy: strategy,
      transaction_cost: txCost,
      slippage,
      value_estimation_method: mode === 'single' ? 'midpoint' : valueMethod,
      max_position_pct: 0.20,
    }
    if (mode === 'single') runSim(base)
    else runMC({ ...base, n_runs: nRuns, delay_noise_days: 0 } as MonteCarloConfig)
  }

  const result = mode === 'single' ? simResult : null
  const mc     = mode === 'montecarlo' ? mcResult : null
  const isPending = simPending || mcPending
  const error = simError || mcError

  return (
    <div className="space-y-6 animate-fade-in">
      <div>
        <h1 className="flex items-center gap-2 text-2xl font-bold text-white sm:text-3xl">
          <Activity className="h-7 w-7 text-brand-400" />
          Portfolio Simulation
        </h1>
        <p className="mt-1 text-slate-400">
          Replay historical disclosures with configurable execution assumptions.
          Trades execute at <code className="text-brand-300">disclosure_date + delay_days</code>.
        </p>
      </div>

      <Disclaimer compact />

      <div className="grid gap-6 lg:grid-cols-3">
        {/* Config panel */}
        <div className="space-y-4">
          <div className="rounded-xl border border-surface-border bg-surface-card p-5">
            <p className="text-xs font-medium uppercase tracking-wider text-slate-500 mb-3">Simulation Mode</p>
            <div className="grid grid-cols-2 gap-2">
              {(['single', 'montecarlo'] as const).map(m => (
                <button key={m} onClick={() => setMode(m)}
                        className={clsx('rounded-lg px-3 py-2 text-xs font-medium capitalize transition-colors',
                          mode === m ? 'bg-brand-600 text-white' : 'bg-surface-elevated text-slate-400 hover:text-white')}>
                  {m === 'single' ? 'Single Run' : 'Monte Carlo'}
                </button>
              ))}
            </div>

            <div className="mt-4 space-y-3">
              <div>
                <label className="block text-xs text-slate-500 mb-1">Trader</label>
                <select value={traderId} onChange={e => setTraderId(Number(e.target.value))}
                        className="w-full rounded-lg border border-surface-border bg-surface-elevated px-3 py-2 text-sm text-white focus:border-brand-500 focus:outline-none">
                  <option value={0} disabled>Select…</option>
                  {traders?.map(t => <option key={t.id} value={t.id}>{t.name}</option>)}
                </select>
              </div>

              <div>
                <label className="block text-xs text-slate-500 mb-1">Starting Capital</label>
                <div className="relative">
                  <span className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400 text-sm">$</span>
                  <input type="number" value={capital} onChange={e => setCapital(Number(e.target.value))}
                         min={1000} max={10_000_000} step={1000}
                         className="w-full rounded-lg border border-surface-border bg-surface-elevated pl-7 pr-3 py-2 text-sm font-mono text-white focus:border-brand-500 focus:outline-none" />
                </div>
                <div className="mt-1.5 flex gap-1">
                  {[10_000, 100_000, 500_000].map(v => (
                    <button key={v} onClick={() => setCapital(v)}
                            className={clsx('rounded px-2 py-0.5 text-xs transition-colors',
                              capital === v ? 'bg-brand-600 text-white' : 'bg-surface-elevated text-slate-400 hover:text-white')}>
                      {currency(v, 0)}
                    </button>
                  ))}
                </div>
              </div>

              <div>
                <label className="block text-xs text-slate-500 mb-1">
                  Execution Delay: <span className="text-brand-400 font-mono">{delay}d</span> after disclosure
                </label>
                <input type="range" min={0} max={30} step={1} value={delay}
                       onChange={e => setDelay(Number(e.target.value))} className="w-full accent-brand-500" />
                <div className="flex justify-between text-xs text-slate-600">
                  <span>0d (immediate)</span><span>30d</span>
                </div>
              </div>

              <div>
                <label className="block text-xs text-slate-500 mb-1">Allocation Strategy</label>
                <select value={strategy} onChange={e => setStrategy(e.target.value as any)}
                        className="w-full rounded-lg border border-surface-border bg-surface-elevated px-3 py-2 text-sm text-white focus:border-brand-500 focus:outline-none">
                  <option value="proportional">Proportional (by disclosed value)</option>
                  <option value="equal_weight">Equal Weight</option>
                </select>
              </div>

              {mode === 'montecarlo' && (
                <div>
                  <label className="block text-xs text-slate-500 mb-1">
                    MC Runs: <span className="text-brand-400 font-mono">{nRuns}</span>
                  </label>
                  <input type="range" min={50} max={1000} step={50} value={nRuns}
                         onChange={e => setNRuns(Number(e.target.value))} className="w-full accent-brand-500" />
                </div>
              )}

              <button onClick={() => setShowAdvanced(!showAdvanced)}
                      className="flex items-center gap-1 text-xs text-slate-500 hover:text-slate-300 transition-colors">
                {showAdvanced ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
                Advanced (costs & slippage)
              </button>

              {showAdvanced && (
                <div className="space-y-2 border-t border-surface-border pt-3">
                  <div>
                    <label className="block text-xs text-slate-500 mb-1">
                      Transaction Cost: <span className="font-mono text-slate-300">{(txCost*100).toFixed(2)}%</span>
                    </label>
                    <input type="range" min={0} max={0.02} step={0.0001} value={txCost}
                           onChange={e => setTxCost(Number(e.target.value))} className="w-full accent-brand-500" />
                  </div>
                  <div>
                    <label className="block text-xs text-slate-500 mb-1">
                      Slippage: <span className="font-mono text-slate-300">{(slippage*100).toFixed(2)}%</span>
                    </label>
                    <input type="range" min={0} max={0.01} step={0.0001} value={slippage}
                           onChange={e => setSlippage(Number(e.target.value))} className="w-full accent-brand-500" />
                  </div>
                  {mode === 'montecarlo' && (
                    <div>
                      <label className="block text-xs text-slate-500 mb-1">Value Estimation</label>
                      <select value={valueMethod} onChange={e => setValueMethod(e.target.value as any)}
                              className="w-full rounded-lg border border-surface-border bg-surface-elevated px-3 py-2 text-xs text-white focus:border-brand-500 focus:outline-none">
                        <option value="probabilistic">Probabilistic (sample from range)</option>
                        <option value="midpoint">Midpoint (deterministic)</option>
                      </select>
                    </div>
                  )}
                </div>
              )}
            </div>

            <button onClick={handleRun} disabled={isPending || !traderId}
                    className={clsx('mt-4 flex w-full items-center justify-center gap-2 rounded-lg px-4 py-2.5 text-sm font-semibold transition-all',
                      isPending || !traderId
                        ? 'cursor-not-allowed bg-slate-700 text-slate-400'
                        : 'bg-brand-600 text-white hover:bg-brand-500 active:scale-95')}>
              {isPending ? (
                <><span className="h-4 w-4 animate-spin rounded-full border-2 border-white/30 border-t-white" />Running…</>
              ) : mode === 'single' ? (
                <><Play className="h-4 w-4" />Run Simulation</>
              ) : (
                <><Shuffle className="h-4 w-4" />Run Monte Carlo</>
              )}
            </button>
          </div>

          {error && (
            <div className="flex items-start gap-2 rounded-xl border border-red-900/40 bg-red-950/20 p-4 text-sm text-red-400">
              <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
              {(error as any)?.response?.data?.detail || 'Simulation failed.'}
            </div>
          )}

          {result && (
            <div className="rounded-xl border border-surface-border bg-surface-card p-4 space-y-2 text-sm">
              <p className="text-xs font-medium uppercase tracking-wider text-slate-500">Result Summary</p>
              {[
                ['Starting', currency(result.starting_capital)],
                ['Final Value', currency(result.final_value)],
                ['Total Return', pct(result.total_return_pct)],
                ['Excess vs Benchmark', pct(result.excess_return_pct ?? null)],
                ['Sharpe', fmt2(result.sharpe_ratio)],
                ['Sortino', fmt2(result.sortino_ratio)],
                ['Max Drawdown', pct(result.max_drawdown_pct)],
                ['Trades Executed', String(result.executed_trade_count)],
              ].map(([k, v]) => (
                <div key={k} className="flex justify-between gap-2">
                  <span className="text-slate-500">{k}</span>
                  <span className="font-mono text-slate-200">{v}</span>
                </div>
              ))}
            </div>
          )}

          {mc && (
            <div className="rounded-xl border border-surface-border bg-surface-card p-4 space-y-2 text-sm">
              <p className="text-xs font-medium uppercase tracking-wider text-slate-500">MC Summary ({mc.n_runs} runs)</p>
              {[
                ['Mean Return', pct(mc.mean_return_pct)],
                ['Median Return', pct(mc.median_return_pct)],
                ['Std Dev', pct(mc.std_return_pct)],
                ['95% CI', `${pct(mc.ci_lower_95)} — ${pct(mc.ci_upper_95)}`],
                ['P(Positive)', `${(mc.prob_positive * 100).toFixed(1)}%`],
                ['P(Beat Benchmark)', mc.prob_beat_benchmark ? `${(mc.prob_beat_benchmark*100).toFixed(1)}%` : '—'],
              ].map(([k, v]) => (
                <div key={k} className="flex justify-between gap-2">
                  <span className="text-slate-500">{k}</span>
                  <span className="font-mono text-slate-200 text-right">{v}</span>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Chart panel */}
        <div className="lg:col-span-2 space-y-4">
          {result && (
            <>
              <div className="grid grid-cols-4 gap-3">
                <MetricCard label="Total Return"  value={pct(result.total_return_pct)}
                            trend={result.total_return_pct >= 0 ? 'up' : 'down'} highlight />
                <MetricCard label="Ann. Return"   value={pct(result.annualized_return_pct)}
                            trend={result.annualized_return_pct >= 0 ? 'up' : 'down'} />
                <MetricCard label="Sharpe"        value={fmt2(result.sharpe_ratio)} />
                <MetricCard label="Sortino"       value={fmt2(result.sortino_ratio)} subtitle="downside-adj" />
              </div>
              <div className="rounded-xl border border-surface-border bg-surface-card p-5">
                <p className="font-semibold text-white mb-3">Portfolio Value — {result.trader_name}</p>
                <div className="h-72">
                  <PortfolioChart
                    data={result.portfolio_history}
                    startingCapital={result.starting_capital}
                    benchmarkData={result.benchmark_return_pct !== undefined
                      ? result.portfolio_history.map((pt, i) => ({
                          date: pt.date,
                          value: result.starting_capital * (1 + (result.benchmark_return_pct! / 100) * (i / Math.max(result.portfolio_history.length - 1, 1))),
                        }))
                      : undefined}
                  />
                </div>
              </div>
            </>
          )}

          {mc && (
            <>
              <div className="grid grid-cols-4 gap-3">
                <MetricCard label="Mean Return"  value={pct(mc.mean_return_pct)}
                            trend={mc.mean_return_pct >= 0 ? 'up' : 'down'} highlight />
                <MetricCard label="95% CI"       value={`${mc.ci_lower_95.toFixed(1)} — ${mc.ci_upper_95.toFixed(1)}%`} />
                <MetricCard label="P(Positive)"  value={`${(mc.prob_positive*100).toFixed(0)}%`}
                            trend={mc.prob_positive > 0.5 ? 'up' : 'down'} />
                <MetricCard label="Std Dev"      value={pct(mc.std_return_pct)} />
              </div>

              <div className="rounded-xl border border-surface-border bg-surface-card p-5">
                <div className="mb-3 flex items-center justify-between">
                  <p className="font-semibold text-white">Monte Carlo — {mc.trader_name} ({mc.n_runs} runs)</p>
                  <div className="flex gap-1">
                    {(['paths', 'distribution'] as const).map(v => (
                      <button key={v} onClick={() => setMcView(v)}
                              className={clsx('rounded px-2 py-1 text-xs capitalize transition-colors',
                                mcView === v ? 'bg-brand-600 text-white' : 'text-slate-400 hover:text-white')}>
                        {v === 'paths' ? 'Portfolio Paths' : 'Return Dist.'}
                      </button>
                    ))}
                  </div>
                </div>
                <div className="h-72">
                  <MonteCarloChart result={mc} view={mcView} />
                </div>
              </div>
            </>
          )}

          {!result && !mc && (
            <div className="flex h-80 items-center justify-center rounded-xl border border-dashed border-surface-border">
              <div className="text-center">
                <Activity className="mx-auto h-10 w-10 text-slate-600" />
                <p className="mt-2 font-medium text-slate-400">Configure and run a simulation</p>
                <p className="text-sm text-slate-600 mt-1">Results will appear here</p>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
