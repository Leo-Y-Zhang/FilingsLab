import { useState } from 'react'
import { FlaskConical, CheckCircle, XCircle, Loader2, AlertTriangle } from 'lucide-react'
import { useExperiments, useHypothesisH1, useHypothesisH2, useTraders, useAlphaDecay } from '@/hooks/useApi'
import AlphaDecayChart from '@/components/Charts/AlphaDecayChart'
import { pct, fmt2 } from '@/utils/format'
import clsx from 'clsx'
import {
  ResponsiveContainer, BarChart, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip, Cell, Legend, ReferenceLine,
} from 'recharts'

function HypothesisCard({ title, data, isLoading }: {
  title: string
  data?: { reject_null: boolean; p_value: number; test_statistic: number; interpretation: string;
           null_hypothesis: string; hypothesis: string; bootstrap_ci_lower?: number; bootstrap_ci_upper?: number }
  isLoading: boolean
}) {
  return (
    <div className="rounded-xl border border-surface-border bg-surface-card p-5">
      <h3 className="font-semibold text-white mb-1">{title}</h3>
      {isLoading ? (
        <div className="flex items-center gap-2 text-sm text-slate-400 py-4">
          <Loader2 className="h-4 w-4 animate-spin" />Running statistical test…
        </div>
      ) : data ? (
        <>
          <p className="text-xs text-slate-500 mb-3">{data.hypothesis}</p>
          <div className="flex items-center gap-2 mb-3">
            {data.reject_null
              ? <CheckCircle className="h-5 w-5 text-emerald-400 shrink-0" />
              : <XCircle className="h-5 w-5 text-red-400 shrink-0" />
            }
            <span className={clsx('text-sm font-medium', data.reject_null ? 'text-emerald-400' : 'text-red-400')}>
              {data.reject_null ? 'Reject H₀' : 'Fail to Reject H₀'}
            </span>
            <span className="text-xs text-slate-500">(p = {data.p_value.toFixed(4)})</span>
          </div>
          <p className="text-xs text-slate-400 leading-relaxed border-t border-surface-border pt-3">
            {data.interpretation}
          </p>
          {data.bootstrap_ci_lower !== undefined && (
            <p className="text-xs text-slate-500 mt-2">
              Bootstrap 95% CI: [{data.bootstrap_ci_lower?.toFixed(4)}%, {data.bootstrap_ci_upper?.toFixed(4)}%]
            </p>
          )}
        </>
      ) : (
        <p className="text-sm text-slate-500 py-4">No data</p>
      )}
    </div>
  )
}

function Exp1Chart({ data }: { data?: import('@/types').Experiment1Result }) {
  if (!data) return null
  const chartData = data.rows.slice(0, 12).map(r => ({
    name: r.name.split(' ').slice(-1)[0],
    'Excess Return': Number(r.excess_return_pct.toFixed(2)),
    sig: r.statistically_significant,
  }))
  return (
    <ResponsiveContainer width="100%" height={220}>
      <BarChart data={chartData} margin={{ top: 5, right: 5, bottom: 5, left: 5 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#334155" vertical={false} />
        <XAxis dataKey="name" tick={{ fill: '#94a3b8', fontSize: 10 }} tickLine={false} axisLine={false} />
        <YAxis tick={{ fill: '#94a3b8', fontSize: 10 }} tickLine={false} axisLine={false}
               tickFormatter={v => typeof v === 'number' ? `${v.toFixed(0)}%` : ''} width={45} />
        <Tooltip formatter={(v: number) => [`${v.toFixed(2)}%`, 'Excess Return']}
                 contentStyle={{ background: '#1e293b', border: '1px solid #475569', borderRadius: 8, fontSize: 12 }} />
        <ReferenceLine y={0} stroke="#475569" strokeDasharray="3 3" />
        <Bar dataKey="Excess Return" radius={[4, 4, 0, 0]}>
          {chartData.map((e, i) => (
            <Cell key={i} fill={e['Excess Return'] >= 0 ? '#3b82f6' : '#ef4444'} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  )
}

function Exp2Chart({ data }: { data?: import('@/types').Experiment2Result }) {
  if (!data) return null
  const chartData = data.rows.map(r => ({
    delay: `${r.delay_days}d`,
    'Mean Return': Number(r.mean_total_return_pct.toFixed(2)),
    'Excess Return': Number(r.mean_excess_return_pct.toFixed(2)),
    'Mean Sortino': Number(r.mean_sortino.toFixed(3)),
  }))
  return (
    <ResponsiveContainer width="100%" height={220}>
      <BarChart data={chartData} margin={{ top: 5, right: 5, bottom: 5, left: 5 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#334155" vertical={false} />
        <XAxis dataKey="delay" tick={{ fill: '#94a3b8', fontSize: 10 }} tickLine={false} axisLine={false} />
        <YAxis tick={{ fill: '#94a3b8', fontSize: 10 }} tickLine={false} axisLine={false}
               tickFormatter={v => typeof v === 'number' ? `${v.toFixed(1)}%` : ''} width={45} />
        <Tooltip contentStyle={{ background: '#1e293b', border: '1px solid #475569', borderRadius: 8, fontSize: 12 }} />
        <Legend wrapperStyle={{ fontSize: 11, color: '#94a3b8' }} />
        <ReferenceLine y={0} stroke="#475569" strokeDasharray="3 3" />
        <Bar dataKey="Mean Return"   fill="#3b82f6" radius={[4, 4, 0, 0]} />
        <Bar dataKey="Excess Return" fill="#10b981" radius={[4, 4, 0, 0]} />
      </BarChart>
    </ResponsiveContainer>
  )
}

function Exp3Chart({ data }: { data?: import('@/types').Experiment3Result }) {
  if (!data) return null
  const chartData = data.rows.slice(0, 8).map(r => ({
    name: r.name.split(' ').slice(-1)[0],
    'Proportional': Number(r.proportional_return_pct.toFixed(2)),
    'Equal Weight': Number(r.equal_weight_return_pct.toFixed(2)),
  }))
  return (
    <ResponsiveContainer width="100%" height={220}>
      <BarChart data={chartData} margin={{ top: 5, right: 5, bottom: 5, left: 5 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#334155" vertical={false} />
        <XAxis dataKey="name" tick={{ fill: '#94a3b8', fontSize: 10 }} tickLine={false} axisLine={false} />
        <YAxis tick={{ fill: '#94a3b8', fontSize: 10 }} tickLine={false} axisLine={false}
               tickFormatter={v => typeof v === 'number' ? `${v.toFixed(0)}%` : ''} width={45} />
        <Tooltip contentStyle={{ background: '#1e293b', border: '1px solid #475569', borderRadius: 8, fontSize: 12 }}
                 formatter={(v: number, n: string) => [`${v.toFixed(2)}%`, n]} />
        <Legend wrapperStyle={{ fontSize: 11, color: '#94a3b8' }} />
        <Bar dataKey="Proportional"  fill="#3b82f6" radius={[4, 4, 0, 0]} />
        <Bar dataKey="Equal Weight"  fill="#8b5cf6" radius={[4, 4, 0, 0]} />
      </BarChart>
    </ResponsiveContainer>
  )
}

export default function Research() {
  const { data: experiments, isLoading: expLoading, error: expError } = useExperiments()
  const { data: h1, isLoading: h1Loading } = useHypothesisH1()
  const { data: h2, isLoading: h2Loading } = useHypothesisH2()
  const { data: traders } = useTraders()

  const [selectedTrader, setSelectedTrader] = useState(0)
  const actualTrader = selectedTrader || traders?.[0]?.id || 0
  const { data: alphaDecay, isLoading: decayLoading } = useAlphaDecay(actualTrader, actualTrader > 0)

  const [activeTab, setActiveTab] = useState<1 | 2 | 3>(1)

  return (
    <div className="space-y-8 animate-fade-in">
      <div>
        <h1 className="flex items-center gap-2 text-2xl font-bold text-white sm:text-3xl">
          <FlaskConical className="h-7 w-7 text-brand-400" />
          Research Laboratory
        </h1>
        <p className="mt-1 text-slate-400 max-w-2xl">
          Structured experiments investigating whether public trading disclosures contain
          statistically exploitable signals. All results are educational simulations.
        </p>
      </div>

      <div className="rounded-xl border border-brand-800/40 bg-brand-950/20 p-5">
        <p className="text-xs font-medium uppercase tracking-wider text-brand-400 mb-1">Core Research Question</p>
        <p className="text-base font-semibold text-white">
          "Do publicly disclosed trades generate statistically significant excess returns after
          accounting for disclosure delays, transaction costs, and market frictions?"
        </p>
        <p className="mt-2 text-xs text-slate-500">
          Execution model: trades simulated at <code className="text-brand-300">disclosure_date + delay_days</code>, not at trade_date.
        </p>
      </div>

      {/* Hypothesis tests */}
      <div>
        <h2 className="text-lg font-semibold text-white mb-3">Statistical Hypothesis Tests</h2>
        <div className="grid gap-4 md:grid-cols-2">
          <HypothesisCard title="H₁: Politician Excess Returns" data={h1} isLoading={h1Loading} />
          <HypothesisCard title="H₂: Early vs Late Action (3d vs 14d)" data={h2} isLoading={h2Loading} />
        </div>
      </div>

      {/* Experiments */}
      <div>
        <h2 className="text-lg font-semibold text-white mb-4">Structured Experiments</h2>

        {expError ? (
          <div className="flex items-center gap-2 rounded-xl border border-red-900/40 bg-red-950/20 p-4 text-sm text-red-400">
            <AlertTriangle className="h-4 w-4" />
            Failed to load experiments. Ensure the backend is running.
          </div>
        ) : (
          <>
            <div className="flex gap-1 mb-4">
              {([
                [1, 'Exp 1: vs Benchmark'],
                [2, 'Exp 2: Delay Impact'],
                [3, 'Exp 3: Strategy'],
              ] as const).map(([tab, label]) => (
                <button key={tab} onClick={() => setActiveTab(tab as 1|2|3)}
                        className={clsx('rounded-lg px-3 py-1.5 text-xs font-medium transition-colors',
                          activeTab === tab ? 'bg-brand-600 text-white' : 'bg-surface-card text-slate-400 hover:text-white')}>
                  {label}
                </button>
              ))}
            </div>

            {expLoading ? (
              <div className="grid gap-4 md:grid-cols-2">
                {[1,2].map(i => <div key={i} className="h-64 animate-pulse rounded-xl bg-surface-card" />)}
              </div>
            ) : experiments && (
              <div className="grid gap-4 md:grid-cols-2">
                {activeTab === 1 && (
                  <>
                    <div className="rounded-xl border border-surface-border bg-surface-card p-5">
                      <h3 className="font-semibold text-white mb-1">{experiments.experiment_1.experiment_name}</h3>
                      <p className="text-xs text-slate-500 mb-3">{experiments.experiment_1.description}</p>
                      <div className="flex gap-4 text-sm mb-3">
                        <div><span className="text-emerald-400 font-bold">{experiments.experiment_1.n_outperforming}</span> <span className="text-slate-500">outperform</span></div>
                        <div><span className="text-red-400 font-bold">{experiments.experiment_1.n_underperforming}</span> <span className="text-slate-500">underperform</span></div>
                        <div><span className={clsx('font-bold', experiments.experiment_1.mean_excess_return_pct >= 0 ? 'text-emerald-400' : 'text-red-400')}>
                          {pct(experiments.experiment_1.mean_excess_return_pct)}</span> <span className="text-slate-500">avg excess</span></div>
                      </div>
                      <Exp1Chart data={experiments.experiment_1} />
                    </div>

                    <div className="rounded-xl border border-surface-border bg-surface-card p-5">
                      <h3 className="font-semibold text-white mb-3">Trader Benchmark Table</h3>
                      <div className="overflow-y-auto max-h-64">
                        <table className="w-full text-xs">
                          <thead><tr className="text-slate-500 border-b border-surface-border">
                            <th className="pb-2 text-left">Trader</th>
                            <th className="pb-2 text-right">Return</th>
                            <th className="pb-2 text-right">Excess</th>
                            <th className="pb-2 text-right">Sortino</th>
                            <th className="pb-2 text-right">p-val</th>
                          </tr></thead>
                          <tbody className="divide-y divide-surface-border/40">
                            {experiments.experiment_1.rows.map(r => (
                              <tr key={r.trader_id}>
                                <td className="py-1.5 text-slate-300">{r.name.split(' ').slice(-1)[0]}</td>
                                <td className={clsx('py-1.5 text-right font-mono', r.total_return_pct >= 0 ? 'text-emerald-400' : 'text-red-400')}>
                                  {pct(r.total_return_pct)}</td>
                                <td className={clsx('py-1.5 text-right font-mono', r.excess_return_pct >= 0 ? 'text-emerald-400' : 'text-red-400')}>
                                  {pct(r.excess_return_pct)}</td>
                                <td className="py-1.5 text-right font-mono text-slate-300">{fmt2(r.sortino_ratio)}</td>
                                <td className={clsx('py-1.5 text-right font-mono', r.statistically_significant ? 'text-emerald-400' : 'text-slate-500')}>
                                  {r.p_value?.toFixed(3)}{r.statistically_significant && ' *'}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  </>
                )}

                {activeTab === 2 && (
                  <>
                    <div className="rounded-xl border border-surface-border bg-surface-card p-5">
                      <h3 className="font-semibold text-white mb-1">{experiments.experiment_2.experiment_name}</h3>
                      <p className="text-xs text-slate-500 mb-2">{experiments.experiment_2.description}</p>
                      <p className="text-xs text-slate-400 mb-3">
                        Optimal delay: <span className="font-mono text-amber-400">{experiments.experiment_2.optimal_delay_days}d</span>
                      </p>
                      <Exp2Chart data={experiments.experiment_2} />
                    </div>

                    <div className="rounded-xl border border-surface-border bg-surface-card p-5">
                      <h3 className="font-semibold text-white mb-3">Delay Impact Table</h3>
                      <table className="w-full text-sm">
                        <thead><tr className="text-slate-500 border-b border-surface-border text-xs">
                          <th className="pb-2 text-left">Delay</th>
                          <th className="pb-2 text-right">Avg Return</th>
                          <th className="pb-2 text-right">Avg Excess</th>
                          <th className="pb-2 text-right">Avg Sortino</th>
                        </tr></thead>
                        <tbody className="divide-y divide-surface-border/40">
                          {experiments.experiment_2.rows.map(r => (
                            <tr key={r.delay_days} className={r.delay_days === experiments.experiment_2.optimal_delay_days ? 'bg-amber-950/20' : ''}>
                              <td className="py-2 text-slate-300 font-mono">{r.delay_days}d
                                {r.delay_days === experiments.experiment_2.optimal_delay_days && <span className="ml-1 text-xs text-amber-400">★</span>}
                              </td>
                              <td className={clsx('py-2 text-right font-mono', r.mean_total_return_pct >= 0 ? 'text-emerald-400' : 'text-red-400')}>
                                {pct(r.mean_total_return_pct)}</td>
                              <td className={clsx('py-2 text-right font-mono', r.mean_excess_return_pct >= 0 ? 'text-emerald-400' : 'text-red-400')}>
                                {pct(r.mean_excess_return_pct)}</td>
                              <td className="py-2 text-right font-mono text-slate-300">{fmt2(r.mean_sortino)}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </>
                )}

                {activeTab === 3 && (
                  <>
                    <div className="rounded-xl border border-surface-border bg-surface-card p-5">
                      <h3 className="font-semibold text-white mb-1">{experiments.experiment_3.experiment_name}</h3>
                      <p className="text-xs text-slate-500 mb-2">{experiments.experiment_3.description}</p>
                      <div className="flex gap-4 text-sm mb-3">
                        <div><span className="text-blue-400 font-bold">{experiments.experiment_3.proportional_wins}</span> <span className="text-slate-500">prop wins</span></div>
                        <div><span className="text-purple-400 font-bold">{experiments.experiment_3.equal_weight_wins}</span> <span className="text-slate-500">eq-wt wins</span></div>
                        <div><span className="text-slate-400 font-bold">{experiments.experiment_3.ties}</span> <span className="text-slate-500">ties</span></div>
                      </div>
                      <Exp3Chart data={experiments.experiment_3} />
                    </div>

                    <div className="rounded-xl border border-surface-border bg-surface-card p-5 space-y-3">
                      <h3 className="font-semibold text-white">Summary Statistics</h3>
                      {[
                        ['Mean Proportional Return', pct(experiments.experiment_3.mean_proportional_return_pct)],
                        ['Mean Equal-Weight Return',  pct(experiments.experiment_3.mean_equal_weight_return_pct)],
                        ['Proportional Wins', String(experiments.experiment_3.proportional_wins)],
                        ['Equal-Weight Wins', String(experiments.experiment_3.equal_weight_wins)],
                        ['Ties', String(experiments.experiment_3.ties)],
                      ].map(([k, v]) => (
                        <div key={k} className="flex justify-between text-sm">
                          <span className="text-slate-500">{k}</span>
                          <span className="font-mono text-slate-200">{v}</span>
                        </div>
                      ))}
                    </div>
                  </>
                )}
              </div>
            )}
          </>
        )}
      </div>

      {/* Alpha decay */}
      <div>
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-lg font-semibold text-white">Alpha Decay — Per-Trader Analysis</h2>
          <select
            value={selectedTrader || traders?.[0]?.id || 0}
            onChange={e => setSelectedTrader(Number(e.target.value))}
            className="rounded-lg border border-surface-border bg-surface-card px-3 py-1.5 text-sm text-white focus:border-brand-500 focus:outline-none"
          >
            {traders?.map(t => <option key={t.id} value={t.id}>{t.name}</option>)}
          </select>
        </div>

        <div className="rounded-xl border border-surface-border bg-surface-card p-5">
          {alphaDecay && (
            <div className="mb-3 flex flex-wrap gap-4 text-sm">
              {alphaDecay.half_life_days && (
                <div><span className="text-slate-500">Signal half-life: </span>
                  <span className="font-mono text-amber-400">~{alphaDecay.half_life_days}d</span></div>
              )}
              {alphaDecay.signal_duration_days && (
                <div><span className="text-slate-500">Signal duration: </span>
                  <span className="font-mono text-slate-300">~{alphaDecay.signal_duration_days}d</span></div>
              )}
              {alphaDecay.benchmark_return_pct !== undefined && (
                <div><span className="text-slate-500">Benchmark return: </span>
                  <span className="font-mono text-slate-300">{pct(alphaDecay.benchmark_return_pct)}</span></div>
              )}
            </div>
          )}
          <div className="h-64">
            {decayLoading ? (
              <div className="h-full animate-pulse rounded-lg bg-surface-elevated" />
            ) : alphaDecay ? (
              <AlphaDecayChart result={alphaDecay} />
            ) : (
              <div className="flex h-full items-center justify-center text-sm text-slate-500">Select a trader</div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
