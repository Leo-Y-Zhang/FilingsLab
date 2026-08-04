import { useState, useRef } from 'react'
import {
  Sparkles, AlertTriangle, CheckCircle, XCircle, Loader2, RefreshCw, Info, Search,
} from 'lucide-react'
import {
  ResponsiveContainer, ComposedChart, Area, Line,
  XAxis, YAxis, Tooltip, CartesianGrid, ReferenceLine,
} from 'recharts'
import clsx from 'clsx'
import { useKronosStatus, useForecastHistory, useForecast } from '@/hooks/useApi'
import type { ForecastPoint } from '@/types'

const PRED_DAY_OPTIONS = [5, 10, 15, 20, 30]

const QUICK_PICKS = ['AAPL', 'MSFT', 'NVDA', 'GOOGL', 'TSLA', 'SPY', 'AMZN', 'META']

const SYMBOL_RE = /^[A-Z0-9.\-]{1,12}$/

// ── Custom tooltip ─────────────────────────────────────────────────────────────
function ChartTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null
  const close = payload.find((p: any) => p.dataKey === 'close' || p.dataKey === 'fClose')
  const high  = payload.find((p: any) => p.dataKey === 'fHigh')
  const low   = payload.find((p: any) => p.dataKey === 'fLow')
  const isForecast = !!high

  return (
    <div className="rounded-lg border border-surface-border bg-surface-card px-3 py-2 text-xs shadow-xl">
      <p className="mb-1 font-medium text-slate-300">
        {new Date(label).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })}
        {isForecast && (
          <span className="ml-2 rounded bg-violet-500/20 px-1 py-0.5 text-violet-400">AI</span>
        )}
      </p>
      {close && (
        <p className={clsx('font-mono', isForecast ? 'text-violet-300' : 'text-slate-200')}>
          Close: ${close.value?.toFixed(2)}
        </p>
      )}
      {high && <p className="font-mono text-emerald-400">High:  ${high.value?.toFixed(2)}</p>}
      {low  && <p className="font-mono text-red-400">Low:   ${low.value?.toFixed(2)}</p>}
    </div>
  )
}

// ── Kronos status badge ────────────────────────────────────────────────────────
function StatusBadge({ available, device }: { available: boolean; device: string }) {
  return (
    <div className={clsx(
      'flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-medium',
      available
        ? 'border-violet-700/50 bg-violet-950/50 text-violet-400'
        : 'border-amber-800/50 bg-amber-950/50 text-amber-400',
    )}>
      {available
        ? <CheckCircle className="h-3 w-3" />
        : <XCircle className="h-3 w-3" />}
      {available ? `Kronos-mini · ${device}` : 'Kronos not set up'}
    </div>
  )
}

// ── Main page ──────────────────────────────────────────────────────────────────
export default function Forecast() {
  const [selectedSym, setSelectedSym] = useState('AAPL')
  const [inputVal, setInputVal]       = useState('AAPL')
  const [inputError, setInputError]   = useState('')
  const [predDays, setPredDays]       = useState(10)
  const inputRef = useRef<HTMLInputElement>(null)

  const submitSymbol = (raw: string) => {
    const sym = raw.trim().toUpperCase()
    if (!sym) return
    if (!SYMBOL_RE.test(sym)) {
      setInputError('Invalid symbol — use letters, digits, dots or hyphens (max 12 chars)')
      return
    }
    setInputError('')
    setSelectedSym(sym)
    setInputVal(sym)
    reset()
  }

  const { data: status, isLoading: statusLoading } = useKronosStatus()
  const { data: history, isLoading: histLoading }  = useForecastHistory(selectedSym, 60, true)
  const { mutate: forecast, data: result, isPending: forecasting, error: forecastError, reset } = useForecast()

  const currentPrice = history && history.length > 0 ? history[history.length - 1].close : null

  // ── Merge history + forecast for the chart ────────────────────────────────
  const chartData: Array<{
    date: string
    close?: number | null
    fClose?: number | null
    fHigh?: number | null
    fLow?: number | null
  }> = []

  if (history) {
    history.forEach(p => chartData.push({ date: p.date, close: p.close }))
  }
  if (result) {
    // Bridge: repeat the last historical close as the forecast start point
    if (history?.length) {
      const last = history[history.length - 1]
      chartData.push({ date: last.date, fClose: last.close, fHigh: last.close, fLow: last.close })
    }
    result.predictions.forEach(p =>
      chartData.push({ date: p.date, fClose: p.close, fHigh: p.high, fLow: p.low })
    )
  }

  const runForecast = () => {
    reset()
    forecast({ symbol: selectedSym, predDays })
  }

  const errMsg = forecastError
    ? (forecastError as any)?.response?.data?.detail ?? (forecastError as Error).message
    : null

  // ── Y-axis domain across both series ──────────────────────────────────────
  const allCloses = chartData.flatMap(d => [d.close, d.fClose, d.fHigh, d.fLow].filter(Boolean) as number[])
  const yMin = allCloses.length ? Math.min(...allCloses) * 0.97 : 'auto'
  const yMax = allCloses.length ? Math.max(...allCloses) * 1.03 : 'auto'

  return (
    <div className="space-y-6 animate-fade-in">
      {/* ── Header ─────────────────────────────────────────────────────────── */}
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-violet-600 to-violet-800 shadow-lg shadow-violet-900/40">
              <Sparkles className="h-5 w-5 text-white" />
            </div>
            <div>
              <h1 className="text-2xl font-bold text-white tracking-tight">
                Kronos AI Forecast
              </h1>
              <p className="text-sm text-slate-400">
                Foundation model · trained on 45 global exchanges · AAAI 2026
              </p>
            </div>
          </div>
        </div>

        {statusLoading ? (
          <div className="h-7 w-48 animate-pulse rounded-full bg-surface-elevated" />
        ) : status ? (
          <StatusBadge available={status.available} device={status.device} />
        ) : null}
      </div>

      {/* ── Setup notice ───────────────────────────────────────────────────── */}
      {status && !status.available && (
        <div className="rounded-xl border border-amber-800/40 bg-amber-950/30 p-4">
          <div className="flex items-start gap-3">
            <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-amber-400" />
            <div className="text-sm">
              <p className="font-semibold text-amber-300">Kronos not set up</p>
              <p className="mt-1 text-amber-400/80">
                Run the one-time setup from the project root, then rebuild Docker:
              </p>
              <div className="mt-2 space-y-1 font-mono text-xs">
                <div className="rounded bg-surface-card px-3 py-1.5 text-slate-300">
                  python setup_kronos.py
                </div>
                <div className="rounded bg-surface-card px-3 py-1.5 text-slate-300">
                  docker compose up --build
                </div>
              </div>
              <p className="mt-2 text-amber-500/70 text-xs">
                Model weights (~50 MB) download from HuggingFace on the first forecast click.
                GPU (8 GB+ VRAM) gives ~3 s per run; CPU also works.
              </p>
            </div>
          </div>
        </div>
      )}

      {/* ── Controls ───────────────────────────────────────────────────────── */}
      <div className="rounded-xl border border-surface-border bg-surface-card p-5 space-y-4">
        {/* Symbol search */}
        <div>
          <label className="mb-2 block text-xs font-medium uppercase tracking-wider text-slate-500">
            Symbol
          </label>
          <div className="flex gap-2">
            <div className="relative flex-1 max-w-xs">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-500 pointer-events-none" />
              <input
                ref={inputRef}
                type="text"
                value={inputVal}
                onChange={e => setInputVal(e.target.value.toUpperCase())}
                onKeyDown={e => e.key === 'Enter' && submitSymbol(inputVal)}
                placeholder="e.g. AAPL, TSLA, NVDA…"
                maxLength={12}
                className="w-full rounded-lg border border-surface-border bg-surface pl-9 pr-3 py-2 text-sm font-mono text-white placeholder-slate-600 focus:border-violet-600 focus:outline-none focus:ring-1 focus:ring-violet-600/40"
              />
            </div>
            <button
              onClick={() => submitSymbol(inputVal)}
              className="rounded-lg border border-violet-700/50 bg-violet-600/20 px-4 py-2 text-sm font-medium text-violet-300 hover:bg-violet-600/30 transition-colors"
            >
              Load
            </button>
          </div>
          {inputError && <p className="mt-1.5 text-xs text-red-400">{inputError}</p>}
          {/* Quick picks */}
          <div className="mt-2 flex flex-wrap gap-1.5">
            {QUICK_PICKS.map(sym => (
              <button
                key={sym}
                onClick={() => { setInputVal(sym); submitSymbol(sym) }}
                className={clsx(
                  'rounded border px-2 py-0.5 text-xs font-mono transition-all',
                  selectedSym === sym
                    ? 'border-violet-600 bg-violet-600/20 text-violet-300'
                    : 'border-surface-border text-slate-500 hover:border-slate-600 hover:text-slate-300',
                )}
              >
                {sym}
              </button>
            ))}
          </div>
        </div>

        <div className="flex flex-wrap items-end gap-6">
          {/* Prediction days */}
          <div className="shrink-0">
            <label className="mb-2 block text-xs font-medium uppercase tracking-wider text-slate-500">
              Days ahead
            </label>
            <div className="flex gap-1">
              {PRED_DAY_OPTIONS.map(d => (
                <button
                  key={d}
                  onClick={() => { setPredDays(d); reset() }}
                  className={clsx(
                    'rounded-lg border px-3 py-1.5 text-xs font-medium transition-all',
                    predDays === d
                      ? 'border-violet-600 bg-violet-600/20 text-violet-300'
                      : 'border-surface-border bg-surface text-slate-400 hover:border-slate-600 hover:text-slate-200',
                  )}
                >
                  {d}
                </button>
              ))}
            </div>
          </div>

          {/* Run button */}
          <button
            onClick={runForecast}
            disabled={forecasting || (status !== undefined && !status?.available)}
            className={clsx(
              'flex shrink-0 items-center gap-2 rounded-xl px-5 py-2.5 text-sm font-semibold transition-all',
              forecasting || (status !== undefined && !status?.available)
                ? 'cursor-not-allowed bg-surface-elevated text-slate-500'
                : 'bg-gradient-to-r from-violet-600 to-violet-700 text-white shadow-lg shadow-violet-900/40 hover:from-violet-500 hover:to-violet-600',
            )}
          >
            {forecasting
              ? <><Loader2 className="h-4 w-4 animate-spin" /> Forecasting…</>
              : result
              ? <><RefreshCw className="h-4 w-4" /> Re-run</>
              : <><Sparkles className="h-4 w-4" /> Run Forecast</>
            }
          </button>
        </div>
      </div>

      {/* ── Error ──────────────────────────────────────────────────────────── */}
      {errMsg && (
        <div className="rounded-xl border border-red-800/40 bg-red-950/30 p-4 text-sm text-red-400">
          <strong>Forecast error:</strong> {errMsg}
        </div>
      )}

      {/* ── Chart ──────────────────────────────────────────────────────────── */}
      <div className="rounded-xl border border-surface-border bg-surface-card p-5">
        <div className="mb-4 flex items-center justify-between">
          <div>
            <span className="text-base font-semibold text-white">
              {selectedSym}
              {currentPrice != null && (
                <span className="ml-2 font-mono text-slate-400 text-sm">${currentPrice.toFixed(2)}</span>
              )}
            </span>
            <p className="text-xs text-slate-500 mt-0.5">Last 60 trading days · historical + AI forecast</p>
          </div>
          {result && (
            <div className="flex items-center gap-4 text-xs text-slate-500">
              <span className="flex items-center gap-1.5">
                <span className="inline-block h-0.5 w-5 rounded bg-emerald-500" />
                Historical
              </span>
              <span className="flex items-center gap-1.5">
                <span className="inline-block h-0.5 w-5 rounded border-t-2 border-dashed border-violet-400" style={{ background: 'none' }} />
                AI Forecast
              </span>
              <span className="text-slate-600">
                {result.model} · {result.device} · {result.source === 'cache' ? 'cached' : 'live'}
              </span>
            </div>
          )}
        </div>

        {histLoading ? (
          <div className="flex h-64 items-center justify-center text-slate-500">
            <Loader2 className="mr-2 h-5 w-5 animate-spin" /> Loading market data…
          </div>
        ) : chartData.length > 0 ? (
          <ResponsiveContainer width="100%" height={280}>
            <ComposedChart data={chartData} margin={{ top: 4, right: 4, bottom: 0, left: 0 }}>
              <defs>
                <linearGradient id="histGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%"  stopColor="#10b981" stopOpacity={0.25} />
                  <stop offset="95%" stopColor="#10b981" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
              <XAxis
                dataKey="date"
                tick={{ fontSize: 10, fill: '#64748b' }}
                tickLine={false}
                tickFormatter={d => new Date(d).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })}
                interval="preserveStartEnd"
              />
              <YAxis
                tick={{ fontSize: 10, fill: '#64748b' }}
                tickLine={false}
                axisLine={false}
                tickFormatter={v => typeof v === 'number' ? `$${v.toFixed(0)}` : ''}
                domain={[yMin, yMax]}
                width={56}
              />
              <Tooltip content={<ChartTooltip />} />

              {/* Historical close area */}
              <Area
                type="monotone"
                dataKey="close"
                stroke="#10b981"
                strokeWidth={2}
                fill="url(#histGrad)"
                dot={false}
                connectNulls={false}
              />

              {/* AI forecast high/low range */}
              {result && (
                <>
                  <Line type="monotone" dataKey="fHigh"  stroke="#7c3aed" strokeWidth={1}
                    strokeDasharray="3 3" dot={false} connectNulls={false} />
                  <Line type="monotone" dataKey="fLow"   stroke="#7c3aed" strokeWidth={1}
                    strokeDasharray="3 3" dot={false} connectNulls={false} />
                  <Line type="monotone" dataKey="fClose" stroke="#a78bfa" strokeWidth={2.5}
                    strokeDasharray="6 3" dot={false} connectNulls={false} />

                  {/* Vertical divider at forecast start */}
                  {history?.length && (
                    <ReferenceLine
                      x={history[history.length - 1].date}
                      stroke="#475569"
                      strokeDasharray="4 4"
                      label={{ value: 'Today', position: 'insideTopRight', fontSize: 10, fill: '#64748b' }}
                    />
                  )}
                </>
              )}
            </ComposedChart>
          </ResponsiveContainer>
        ) : (
          <div className="flex h-64 items-center justify-center text-slate-500 text-sm">
            No market data available
          </div>
        )}
      </div>

      {/* ── Forecast table ─────────────────────────────────────────────────── */}
      {result && (
        <div className="rounded-xl border border-surface-border bg-surface-card overflow-hidden">
          <div className="border-b border-surface-border px-5 py-3 flex items-center justify-between">
            <span className="text-sm font-semibold text-white">
              AI Price Predictions · {selectedSym} · Next {result.predictions.length} trading days
            </span>
            <span className="text-xs text-slate-500">{result.model}</span>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-surface-border text-slate-500">
                  <th className="px-4 py-2.5 text-left font-medium uppercase tracking-wider">Date</th>
                  <th className="px-4 py-2.5 text-right font-medium uppercase tracking-wider">Open</th>
                  <th className="px-4 py-2.5 text-right font-medium uppercase tracking-wider">High</th>
                  <th className="px-4 py-2.5 text-right font-medium uppercase tracking-wider">Low</th>
                  <th className="px-4 py-2.5 text-right font-medium uppercase tracking-wider">Close</th>
                  <th className="px-4 py-2.5 text-right font-medium uppercase tracking-wider">vs Today</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-surface-border/50">
                {result.predictions.map((p: ForecastPoint) => {
                  const vsToday = currentPrice != null
                    ? ((p.close - currentPrice) / currentPrice) * 100
                    : null
                  const isUp = vsToday != null && vsToday >= 0
                  return (
                    <tr key={p.date} className="hover:bg-surface-elevated/40 transition-colors">
                      <td className="px-4 py-2.5 font-medium text-slate-300">
                        {new Date(p.date).toLocaleDateString('en-GB', { weekday: 'short', day: 'numeric', month: 'short' })}
                      </td>
                      <td className="px-4 py-2.5 text-right font-mono tabular-nums text-slate-300">
                        ${p.open.toFixed(2)}
                      </td>
                      <td className="px-4 py-2.5 text-right font-mono tabular-nums text-emerald-400">
                        ${p.high.toFixed(2)}
                      </td>
                      <td className="px-4 py-2.5 text-right font-mono tabular-nums text-red-400">
                        ${p.low.toFixed(2)}
                      </td>
                      <td className="px-4 py-2.5 text-right font-mono tabular-nums font-semibold text-violet-300">
                        ${p.close.toFixed(2)}
                      </td>
                      <td className={clsx(
                        'px-4 py-2.5 text-right font-mono tabular-nums font-semibold',
                        vsToday == null ? 'text-slate-600'
                          : isUp ? 'text-emerald-400' : 'text-red-400',
                      )}>
                        {vsToday != null
                          ? `${vsToday >= 0 ? '+' : ''}${vsToday.toFixed(2)}%`
                          : '—'}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* ── Disclaimer ─────────────────────────────────────────────────────── */}
      <div className="flex items-start gap-2 rounded-xl border border-slate-800/60 bg-slate-900/40 p-4 text-xs text-slate-500">
        <Info className="mt-0.5 h-4 w-4 shrink-0 text-slate-600" />
        <p>
          Kronos (Tsinghua University, AAAI 2026) is an experimental AI model trained on
          candlestick patterns. Predictions are statistical in nature, do not constitute
          financial advice, and carry no guarantee of accuracy. This feature is for
          research and educational use only.
        </p>
      </div>
    </div>
  )
}
