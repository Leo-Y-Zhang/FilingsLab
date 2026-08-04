import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Rss, TrendingUp, TrendingDown, Loader2, ShoppingCart, X,
  RefreshCw, Briefcase, Bot, Settings, Play, Clock, CheckCircle, KeyRound,
} from 'lucide-react'
import clsx from 'clsx'
import axios from 'axios'

import { getOperatorToken, setOperatorToken, useOperatorToken } from '@/services/operatorToken'
import { feedPollIntervalMs, statusOf } from '@/services/queryClient'

// ── API helpers ───────────────────────────────────────────────────────────────

const api = axios.create({ baseURL: '/api', timeout: 30_000 })

// ── Operator token ────────────────────────────────────────────────────────────
// Held in sessionStorage for this tab only, never in the bundle. See
// services/operatorToken.ts. Every gated query below is disabled while it is
// empty: an anonymous visitor must not call a route that can only answer 401,
// because those 401s still consume that visitor's rate-limit budget and the
// first thing they break is the public feed they ARE allowed to read.
api.interceptors.request.use(cfg => {
  const token = getOperatorToken()
  if (token) cfg.headers.Authorization = `Bearer ${token}`
  return cfg
})

const AUTO_TRADER_POLL_MS = 15_000

const fetchDisclosures  = (limit = 50) => api.get(`/feed/disclosures?limit=${limit}`).then(r => r.data)
const fetchPortfolio    = ()           => api.get('/feed/portfolio').then(r => r.data)
const fetchATConfig     = ()           => api.get('/feed/auto-trader/config').then(r => r.data)
const fetchATLog        = ()           => api.get('/feed/auto-trader/log?limit=30').then(r => r.data)
const executeOrder      = (body: any)  => api.post('/feed/execute', body).then(r => r.data)
const closePosition     = (t: string)  => api.delete(`/feed/position/${t}`).then(r => r.data)
const saveATConfig      = (body: any)  => api.post('/feed/auto-trader/config', body).then(r => r.data)
const runATNow          = ()           => api.post('/feed/auto-trader/run').then(r => r.data)

// ── Badges ────────────────────────────────────────────────────────────────────

function ScoreBadge({ score, action }: { score: number; action: string }) {
  const color =
    action === 'strong_buy'  ? 'bg-emerald-500/20 text-emerald-300 border-emerald-700/50' :
    action === 'buy'         ? 'bg-blue-500/20 text-blue-300 border-blue-700/50' :
    action === 'strong_sell' ? 'bg-red-500/20 text-red-300 border-red-700/50' :
    action === 'sell'        ? 'bg-orange-500/20 text-orange-300 border-orange-700/50' :
    action === 'watch'       ? 'bg-amber-500/20 text-amber-300 border-amber-700/50' :
                               'bg-slate-800 text-slate-500 border-slate-700'
  return (
    <span className={clsx('rounded-full border px-2 py-0.5 text-xs font-mono font-semibold', color)}>
      {score.toFixed(0)}
    </span>
  )
}

function ActionBadge({ action }: { action: string }) {
  const map: Record<string, string> = {
    strong_buy:  'bg-emerald-900/40 text-emerald-300 border-emerald-700/40',
    buy:         'bg-blue-900/40 text-blue-300 border-blue-700/40',
    strong_sell: 'bg-red-900/40 text-red-300 border-red-700/40',
    sell:        'bg-orange-900/40 text-orange-300 border-orange-700/40',
    watch:       'bg-amber-900/40 text-amber-300 border-amber-700/40',
    skip:        'bg-slate-800/60 text-slate-500 border-slate-700/40',
  }
  const label: Record<string, string> = {
    strong_buy: 'Strong Buy', buy: 'Buy',
    strong_sell: 'Strong Sell', sell: 'Sell',
    watch: 'Watch', skip: 'Skip',
  }
  return (
    <span className={clsx('rounded border px-2 py-0.5 text-xs font-semibold', map[action] ?? map.skip)}>
      {label[action] ?? action}
    </span>
  )
}

function fmtAmount(est?: number, str?: string) {
  if (str) return str
  if (!est) return '—'
  return est >= 1_000_000 ? `$${(est/1_000_000).toFixed(1)}M`
       : est >= 1_000     ? `$${(est/1_000).toFixed(0)}k`
       : `$${est}`
}

// ── Manual trade panel ────────────────────────────────────────────────────────

function ExecutePanel({ ticker, onClose, onDone }: {
  ticker: string; onClose: () => void; onDone: () => void
}) {
  const [notional, setNotional] = useState('1000')
  const exec = useMutation({ mutationFn: executeOrder, onSuccess: onDone })

  const submit = (side: 'buy' | 'sell') => {
    const n = parseFloat(notional)
    if (!n || n <= 0) return
    exec.mutate({ ticker, side, notional: n })
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="w-full max-w-sm rounded-2xl border border-surface-border bg-surface-card p-6 shadow-2xl">
        <div className="mb-4 flex items-center justify-between">
          <h3 className="text-lg font-bold text-white">Paper Trade — {ticker}</h3>
          <button onClick={onClose}><X className="h-5 w-5 text-slate-400 hover:text-white" /></button>
        </div>
        <div className="mb-4 rounded-lg border border-brand-800/40 bg-brand-950/30 p-2.5 text-xs text-brand-300">
          Virtual paper trade — no real money involved.
        </div>
        <label className="mb-1 block text-xs uppercase tracking-wider text-slate-500">Amount (USD)</label>
        <input
          type="number" min="1" value={notional}
          onChange={e => setNotional(e.target.value)}
          className="mb-4 w-full rounded-lg border border-surface-border bg-surface px-3 py-2 text-sm text-white focus:border-brand-600 focus:outline-none"
        />
        {exec.isSuccess && (
          <p className="mb-3 text-xs text-emerald-400">
            Order filled at ${(exec.data?.order?.price ?? 0).toFixed(2)} ✓
          </p>
        )}
        {exec.isError && (
          <p className="mb-3 text-xs text-red-400">
            {(exec.error as any)?.response?.data?.detail ?? 'Order failed'}
          </p>
        )}
        <div className="flex gap-2">
          <button onClick={() => submit('buy')} disabled={exec.isPending}
            className="flex flex-1 items-center justify-center gap-2 rounded-lg bg-emerald-600 py-2.5 text-sm font-semibold text-white hover:bg-emerald-500 disabled:opacity-50">
            {exec.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <TrendingUp className="h-4 w-4" />}
            Buy
          </button>
          <button onClick={() => submit('sell')} disabled={exec.isPending}
            className="flex flex-1 items-center justify-center gap-2 rounded-lg bg-red-700 py-2.5 text-sm font-semibold text-white hover:bg-red-600 disabled:opacity-50">
            {exec.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <TrendingDown className="h-4 w-4" />}
            Sell
          </button>
        </div>
      </div>
    </div>
  )
}

// ── Auto-trader panel ─────────────────────────────────────────────────────────

function AutoTraderPanel() {
  const qc = useQueryClient()
  // The auto-trader IS the control surface. With no token these two polls are
  // two 401s every 15 seconds, forever, from a visitor who cannot use the
  // panel at all — so they do not run.
  const signedIn = useOperatorToken().length > 0
  const { data: cfg, isLoading } = useQuery({
    queryKey: ['at-config'],
    queryFn: fetchATConfig,
    enabled: signedIn,
    staleTime: 0,
    refetchInterval: signedIn ? AUTO_TRADER_POLL_MS : false,
  })
  const { data: logData } = useQuery({
    queryKey: ['at-log'],
    queryFn: fetchATLog,
    enabled: signedIn,
    staleTime: 0,
    refetchInterval: signedIn ? AUTO_TRADER_POLL_MS : false,
  })

  const [form, setForm] = useState<any>(null)
  const current = { ...(cfg ?? {}), ...(form ?? {}) }

  const save = useMutation({
    mutationFn: saveATConfig,
    onSuccess: (_, vars) => {
      // Merge saved values into server cache immediately
      qc.setQueryData(['at-config'], (old: any) => ({ ...old, ...vars }))
      setForm(null)
    },
  })
  const run = useMutation({
    mutationFn: runATNow,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['at-config'] })
      qc.invalidateQueries({ queryKey: ['at-log'] })
      qc.invalidateQueries({ queryKey: ['portfolio'] })
    },
  })

  const f = (key: string) => (e: React.ChangeEvent<HTMLInputElement>) => {
    const v = e.target.type === 'checkbox' ? e.target.checked : Number(e.target.value)
    setForm((prev: any) => ({ ...(prev ?? {}), [key]: v }))
  }

  const actionColorLog = (a: string) =>
    a === 'buy'          ? 'text-emerald-400' :
    a === 'sell'         ? 'text-orange-400' :
    a === 'take_profit'  ? 'text-blue-400' :
    a === 'stop_loss'    ? 'text-red-400' :
                           'text-slate-500'

  if (!signedIn) {
    return (
      <div className="rounded-xl border border-surface-border bg-surface-card p-5">
        <div className="flex items-center gap-2">
          <Bot className="h-5 w-5 text-brand-400" />
          <span className="font-semibold text-white">Auto-Trader</span>
        </div>
        <p className="mt-2 text-xs text-slate-400">
          Sign in with the operator token to view or change the auto-trader. Nothing is
          requested from the server until you do.
        </p>
      </div>
    )
  }

  if (isLoading) return <div className="text-slate-500 text-xs p-4">Loading…</div>

  return (
    <div className="rounded-xl border border-surface-border bg-surface-card p-5 space-y-5">
      {/* Header + toggle */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Bot className="h-5 w-5 text-brand-400" />
          <span className="font-semibold text-white">Auto-Trader</span>
          <span className="rounded-full px-2 py-0.5 text-xs bg-slate-800 text-slate-400">Paper only</span>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-xs text-slate-500">
            {current.enabled ? <span className="text-emerald-400 font-medium">Active</span> : 'Disabled'}
          </span>
          <button
            onClick={() => {
              const next = !current.enabled
              setForm((prev: any) => ({ ...(prev ?? {}), enabled: next }))
              save.mutate({ enabled: next })
            }}
            className={clsx(
              'relative h-6 w-11 rounded-full transition-colors',
              current.enabled ? 'bg-emerald-600' : 'bg-slate-700',
            )}
          >
            <span className={clsx(
              'absolute top-0.5 h-5 w-5 rounded-full bg-white shadow transition-transform',
              current.enabled ? 'translate-x-5' : 'translate-x-0.5',
            )} />
          </button>
        </div>
      </div>

      {/* Settings grid */}
      <div className="grid grid-cols-2 gap-x-6 gap-y-3 sm:grid-cols-3">
        {[
          { label: 'Min Signal Score', key: 'min_score', min: 30, max: 95, step: 5 },
          { label: 'Max Position %', key: 'max_position_pct', min: 2, max: 25, step: 1 },
          { label: 'Max Positions', key: 'max_positions', min: 1, max: 20, step: 1 },
          { label: 'Take Profit %', key: 'take_profit_pct', min: 5, max: 50, step: 1 },
          { label: 'Stop Loss %', key: 'stop_loss_pct', min: 2, max: 20, step: 1 },
          { label: 'Run Every (mins)', key: 'run_interval_mins', min: 15, max: 240, step: 15 },
        ].map(({ label, key, min, max, step }) => (
          <div key={key}>
            <label className="text-xs text-slate-500">{label}</label>
            <div className="flex items-center gap-2 mt-0.5">
              <input
                type="range" min={min} max={max} step={step}
                value={current[key] ?? 0}
                onChange={f(key)}
                className="w-full accent-brand-500"
              />
              <span className="w-10 text-right text-xs text-white font-mono">
                {current[key] ?? '—'}
              </span>
            </div>
          </div>
        ))}
      </div>

      {/* Checkboxes */}
      <div className="flex flex-wrap gap-4">
        {[
          { label: 'Auto-buy on buy signals', key: 'trade_buys' },
          { label: 'Close positions on insider sell signals', key: 'trade_sell_signals' },
        ].map(({ label, key }) => (
          <label key={key} className="flex items-center gap-2 text-xs text-slate-300 cursor-pointer">
            <input
              type="checkbox"
              checked={Boolean(current[key])}
              onChange={f(key)}
              className="rounded accent-brand-500"
            />
            {label}
          </label>
        ))}
      </div>

      {/* Save + Run buttons */}
      <div className="flex items-center gap-3 flex-wrap">
        <button
          onClick={() => save.mutate(current)}
          disabled={!form || save.isPending}
          className="flex items-center gap-1.5 rounded-lg bg-brand-600 px-4 py-2 text-xs font-semibold text-white hover:bg-brand-500 disabled:opacity-40"
        >
          <Settings className="h-3.5 w-3.5" />
          {save.isPending ? 'Saving…' : 'Save Settings'}
        </button>
        <button
          onClick={() => run.mutate()}
          disabled={run.isPending}
          className="flex items-center gap-1.5 rounded-lg border border-emerald-700/50 bg-emerald-900/30 px-4 py-2 text-xs font-semibold text-emerald-300 hover:bg-emerald-900/60 disabled:opacity-40"
        >
          {run.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Play className="h-3.5 w-3.5" />}
          Run Now
        </button>
        {current.last_run_at && (
          <span className="text-xs text-slate-500 flex items-center gap-1">
            <Clock className="h-3 w-3" />
            Last run: {new Date(current.last_run_at).toLocaleTimeString()}
            {current.last_run_summary && ` — ${current.last_run_summary}`}
          </span>
        )}
      </div>

      {/* Activity log */}
      {logData?.log?.length > 0 && (
        <div>
          <p className="mb-2 text-xs font-medium uppercase tracking-wider text-slate-500">
            Activity Log
          </p>
          <div className="max-h-40 overflow-y-auto space-y-1">
            {logData.log.map((row: any) => (
              <div key={row.id} className="flex items-center gap-2 text-xs font-mono">
                <CheckCircle className="h-3 w-3 flex-shrink-0 text-slate-600" />
                <span className={clsx('font-semibold uppercase w-20 flex-shrink-0', actionColorLog(row.action))}>
                  {row.action}
                </span>
                <span className="text-white">{row.ticker}</span>
                {row.notional && <span className="text-slate-400">${row.notional.toLocaleString('en-US', {maximumFractionDigits:0})}</span>}
                {row.score && <span className="text-slate-600">score {row.score.toFixed(0)}</span>}
                <span className="ml-auto text-slate-700 flex-shrink-0">
                  {row.created_at ? new Date(row.created_at).toLocaleTimeString() : ''}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

// ── Operator token control ────────────────────────────────────────────────────

function OperatorTokenControl() {
  const qc = useQueryClient()
  const stored = useOperatorToken()
  const [open, setOpen]   = useState(false)
  const [value, setValue] = useState(stored)
  const active = stored.length > 0 && value === stored

  const apply = (next: string) => {
    setValue(next)
    setOperatorToken(next)
    qc.invalidateQueries()
    setOpen(false)
  }

  return (
    <div className="relative">
      <button
        onClick={() => setOpen(o => !o)}
        className={clsx(
          'flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-xs font-medium transition-colors',
          active
            ? 'border-emerald-700/60 bg-emerald-600/15 text-emerald-300'
            : 'border-surface-border bg-surface-card text-slate-400 hover:text-white',
        )}
      >
        <KeyRound className="h-3.5 w-3.5" />
        {active ? 'Operator' : 'Sign in'}
      </button>
      {open && (
        <div className="absolute right-0 z-20 mt-2 w-72 rounded-lg border border-surface-border bg-surface-card p-3 shadow-xl">
          <p className="mb-2 text-xs text-slate-400">
            Operator token (<code>API_TOKEN</code>). Needed for the paper portfolio and
            the auto-trader. Held in this browser tab only, never in the bundle.
          </p>
          <input
            type="password"
            autoComplete="off"
            value={value}
            onChange={e => setValue(e.target.value)}
            placeholder="paste token"
            className="w-full rounded-lg border border-surface-border bg-surface-elevated px-2 py-1.5 text-xs text-white"
          />
          <div className="mt-2 flex gap-2">
            <button
              onClick={() => apply(value)}
              className="flex-1 rounded-lg bg-brand-600 py-1.5 text-xs font-semibold text-white hover:bg-brand-500"
            >
              Save
            </button>
            <button
              onClick={() => apply('')}
              className="rounded-lg border border-surface-border px-3 py-1.5 text-xs text-slate-400 hover:text-white"
            >
              Clear
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function Feed() {
  const qc = useQueryClient()
  const [limit, setLimit] = useState(50)
  const [filterAction, setFilterAction] = useState<string>('all')
  const [executing, setExecuting] = useState<string | null>(null)
  const [showAT, setShowAT] = useState(false)
  const signedIn = useOperatorToken().length > 0

  const { data: feed, isLoading, refetch, isFetching, error: feedError } = useQuery({
    queryKey: ['feed', limit],
    queryFn: () => fetchDisclosures(limit),
    staleTime: 60_000,
    // Paused while rate limited, fast while the server says it is warming, and
    // slow once there is data. See services/queryClient.ts — leaving this at the
    // steady-state five minutes is what turned a sub-minute cold start into a
    // ten-minute wait for a lone visitor.
    refetchInterval: q => feedPollIntervalMs(q.state.data, q.state.error),
  })

  // A 429 on the open feed means we are already asking too often. Say so, and
  // stop the background poll until the user asks again — polling through a
  // rate limit is how a limit becomes permanent.
  const rateLimited = statusOf(feedError) === 429

  // The paper portfolio needs the operator token. Without one this query would
  // 401 on every mount and every invalidation, for every anonymous visitor.
  const { data: portfolio } = useQuery({
    queryKey: ['portfolio'],
    queryFn: fetchPortfolio,
    enabled: signedIn,
    staleTime: 30_000,
  })

  const closePos = useMutation({
    mutationFn: closePosition,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['portfolio'] }),
  })

  // The interval the page is actually on, so the banner cannot promise one
  // cadence while the query runs on another.
  const warmingPollMs = feedPollIntervalMs(feed, null)
  const warmingRetrySeconds = Math.round((warmingPollMs === false ? 0 : warmingPollMs) / 1000)

  const disclosures: any[] = feed?.disclosures ?? []
  const filtered = filterAction === 'all'
    ? disclosures
    : disclosures.filter((d: any) => d.action === filterAction)

  const account         = portfolio?.account ?? {}
  const positions: any[] = portfolio?.positions ?? []
  const portfolioValue  = parseFloat(account.portfolio_value || '100000')
  const buyingPower     = parseFloat(account.buying_power    || '100000')
  const totalReturnPct  = parseFloat(account.total_return_pct ?? '0')

  const buyCnt       = disclosures.filter(d => d.action === 'buy').length
  const strongBuyCnt = disclosures.filter(d => d.action === 'strong_buy').length
  const sellCnt      = disclosures.filter(d => d.action === 'sell').length
  const strongSellCnt= disclosures.filter(d => d.action === 'strong_sell').length

  return (
    <div className="space-y-6 animate-fade-in">

      {/* Header */}
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-bold text-white">
            <Rss className="h-6 w-6 text-brand-400" />
            Insider Trading Feed
          </h1>
          <p className="mt-1 text-sm text-slate-400">
            SEC Form 4 filings · directors &amp; officers buying/selling their own stock · paper trade to follow
          </p>
        </div>
        <div className="flex items-center gap-2">
          <OperatorTokenControl />
          <button
            onClick={() => setShowAT(v => !v)}
            className={clsx(
              'flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-xs font-medium transition-colors',
              showAT
                ? 'border-brand-600/60 bg-brand-600/20 text-brand-300'
                : 'border-surface-border bg-surface-card text-slate-400 hover:text-white',
            )}
          >
            <Bot className="h-3.5 w-3.5" />
            Auto-Trader
          </button>
          <button
            onClick={() => refetch()}
            disabled={isFetching}
            className="flex items-center gap-1.5 rounded-lg border border-surface-border bg-surface-card px-3 py-1.5 text-xs text-slate-400 hover:text-white transition-colors"
          >
            <RefreshCw className={clsx('h-3.5 w-3.5', isFetching && 'animate-spin')} />
            Refresh
          </button>
        </div>
      </div>

      {/* Rate-limit / warm-up notices */}
      {rateLimited && (
        <div className="rounded-xl border border-amber-700/50 bg-amber-950/30 p-4 text-sm text-amber-300">
          <p className="font-semibold">Rate limited</p>
          <p className="mt-1 text-xs text-amber-200/80">
            The public disclosure feed allows 10 requests a minute per client. Automatic
            refreshing is paused; use Refresh in a moment to try again.
          </p>
        </div>
      )}
      {!rateLimited && feed?.warming && (
        <div
          role="status"
          aria-live="polite"
          className="rounded-xl border border-brand-800/40 bg-brand-950/30 p-4 text-sm text-brand-300"
        >
          <p className="font-semibold">Fetching filings from SEC EDGAR</p>
          <p className="mt-1 text-xs text-brand-200/80">
            {/* The server states the wait, because the server is the only thing
                that knows which of the two background stages is running. The
                fallback is what it says when it cannot reach us at all — it must
                not be more optimistic than the truth either. */}
            {feed.message ??
              'The first load after a restart usually takes under a minute, and a few minutes when EDGAR is slow.'}
          </p>
          <p className="mt-1 text-xs text-brand-200/60">
            Checking again every {warmingRetrySeconds} seconds — no need to refresh.
          </p>
        </div>
      )}

      {/* Auto-trader panel (collapsible) */}
      {showAT && <AutoTraderPanel />}

      {!signedIn && (
        <p className="text-xs text-slate-500">
          Paper-portfolio figures are the starting balance until you sign in with the
          operator token — the account routes are not requested while signed out.
        </p>
      )}

      {/* Portfolio summary cards */}
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <div className="rounded-xl border border-surface-border bg-surface-card p-4">
          <p className="text-xs font-medium uppercase tracking-wider text-slate-500">Portfolio Value</p>
          <p className="mt-1 text-xl font-bold text-white">
            ${portfolioValue.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
          </p>
          <p className={clsx('mt-0.5 text-xs font-medium', totalReturnPct >= 0 ? 'text-emerald-400' : 'text-red-400')}>
            {totalReturnPct >= 0 ? '+' : ''}{totalReturnPct.toFixed(2)}% return
          </p>
        </div>
        <div className="rounded-xl border border-surface-border bg-surface-card p-4">
          <p className="text-xs font-medium uppercase tracking-wider text-slate-500">Cash Available</p>
          <p className="mt-1 text-xl font-bold text-white">
            ${buyingPower.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
          </p>
          <p className="mt-0.5 text-xs text-slate-500">Paper · no real money</p>
        </div>
        <div className="rounded-xl border border-surface-border bg-surface-card p-4">
          <p className="text-xs font-medium uppercase tracking-wider text-slate-500">Open Positions</p>
          <p className="mt-1 text-xl font-bold text-white">{positions.length}</p>
          <p className="mt-0.5 text-xs text-slate-500 truncate">
            {positions.length === 0 ? 'No positions' : positions.map((p: any) => p.symbol).join(', ')}
          </p>
        </div>
        <div className="rounded-xl border border-surface-border bg-surface-card p-4">
          <p className="text-xs font-medium uppercase tracking-wider text-slate-500">Signal Mix</p>
          <div className="mt-1 flex flex-wrap gap-1 text-xs">
            {strongBuyCnt > 0 && <span className="text-emerald-400 font-semibold">{strongBuyCnt} ▲▲</span>}
            {buyCnt > 0       && <span className="text-blue-400 font-semibold">{buyCnt} ▲</span>}
            {sellCnt > 0      && <span className="text-orange-400 font-semibold">{sellCnt} ▼</span>}
            {strongSellCnt > 0 && <span className="text-red-400 font-semibold">{strongSellCnt} ▼▼</span>}
            {buyCnt + strongBuyCnt + sellCnt + strongSellCnt === 0 && <span className="text-slate-500">—</span>}
          </div>
        </div>
      </div>

      {/* Open positions strip */}
      {positions.length > 0 && (
        <div className="rounded-xl border border-surface-border bg-surface-card p-4">
          <p className="mb-3 text-xs font-semibold uppercase tracking-wider text-slate-500">
            <Briefcase className="inline h-3.5 w-3.5 mr-1" />Open Positions
          </p>
          <div className="flex flex-wrap gap-2">
            {positions.map((p: any) => {
              const pnlPct = (Number(p.unrealized_plpc) ?? 0) * 100
              return (
                <div key={p.symbol} className="flex items-center gap-2 rounded-lg border border-surface-border bg-surface px-3 py-2 text-xs">
                  <span className="font-mono font-semibold text-white">{p.symbol}</span>
                  <span className="text-slate-400">{Number(p.qty).toFixed(2)} sh @ ${Number(p.avg_entry_price).toFixed(2)}</span>
                  <span className={clsx('font-medium', pnlPct >= 0 ? 'text-emerald-400' : 'text-red-400')}>
                    {pnlPct >= 0 ? '+' : ''}{pnlPct.toFixed(2)}%
                  </span>
                  <button
                    onClick={() => closePos.mutate(p.symbol)}
                    disabled={closePos.isPending}
                    className="ml-1 rounded border border-red-800/40 bg-red-950/30 px-1.5 py-0.5 text-red-400 hover:bg-red-900/40 disabled:opacity-50"
                  >
                    Close
                  </button>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-2">
        {([
          { key: 'all',        label: `All (${disclosures.length})` },
          { key: 'strong_buy', label: `Strong Buy (${strongBuyCnt})` },
          { key: 'buy',        label: `Buy (${buyCnt})` },
          { key: 'sell',       label: `Sell (${sellCnt})` },
          { key: 'strong_sell',label: `Strong Sell (${strongSellCnt})` },
          { key: 'watch',      label: `Watch` },
          { key: 'skip',       label: `Skip` },
        ] as const).map(f => (
          <button
            key={f.key}
            onClick={() => setFilterAction(f.key)}
            className={clsx(
              'rounded-full px-3 py-1 text-xs font-medium capitalize transition-colors',
              filterAction === f.key
                ? 'bg-brand-600 text-white'
                : 'bg-surface-card text-slate-400 hover:bg-surface-elevated hover:text-white',
            )}
          >
            {f.label}
          </button>
        ))}
        <select
          value={limit}
          onChange={e => setLimit(Number(e.target.value))}
          className="ml-auto rounded-lg border border-surface-border bg-surface-card px-2 py-1 text-xs text-slate-400"
        >
          <option value={25}>25</option>
          <option value={50}>50</option>
          <option value={100}>100</option>
        </select>
      </div>

      {/* Table */}
      {isLoading ? (
        <div className="flex h-40 items-center justify-center gap-2 text-slate-500">
          <Loader2 className="h-5 w-5 animate-spin" />
          Fetching insider trades from SEC EDGAR — the first load after a restart
          usually takes under a minute…
        </div>
      ) : (
        <div className="overflow-x-auto rounded-xl border border-surface-border bg-surface-card">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-surface-border text-xs font-medium uppercase tracking-wider text-slate-500">
                <th className="p-4 text-left">Score</th>
                <th className="p-4 text-left">Insider</th>
                <th className="p-4 text-left">Ticker</th>
                <th className="p-4 text-left">Type</th>
                <th className="p-4 text-right">Amount</th>
                <th className="p-4 text-right">Price</th>
                <th className="p-4 text-right">Kronos</th>
                <th className="p-4 text-left">Filed</th>
                <th className="p-4 text-left">Signal</th>
                <th className="p-4 text-center">Act</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-surface-border/40">
              {filtered.length === 0 && (
                <tr>
                  <td colSpan={10} className="p-8 text-center text-slate-500 text-sm">
                    No insider trades found for this filter. SEC EDGAR updates daily — try refreshing.
                  </td>
                </tr>
              )}
              {filtered.map((d: any, i: number) => (
                <tr key={i} className="hover:bg-surface-elevated/20 transition-colors">
                  <td className="p-4"><ScoreBadge score={d.score} action={d.action} /></td>
                  <td className="p-4">
                    <p className="font-medium text-white text-sm">{d.trader_name}</p>
                    <p className="text-xs text-slate-500">{d.trader_role}{d.company ? ` · ${d.company}` : ''}</p>
                  </td>
                  <td className="p-4">
                    <span className="font-mono font-semibold text-brand-300">{d.ticker || '—'}</span>
                  </td>
                  <td className="p-4">
                    <span className={clsx(
                      'rounded-full px-2 py-0.5 text-xs font-medium capitalize',
                      d.transaction_type === 'buy' ? 'bg-emerald-900/40 text-emerald-400' : 'bg-red-900/40 text-red-400',
                    )}>
                      {d.transaction_type}
                    </span>
                  </td>
                  <td className="p-4 text-right font-mono text-xs text-slate-300">
                    {fmtAmount(d.amount_est, d.amount_str)}
                  </td>
                  <td className="p-4 text-right font-mono text-xs text-slate-300">
                    {d.price_now ? `$${Number(d.price_now).toFixed(2)}` : '—'}
                  </td>
                  <td className="p-4 text-right font-mono text-xs">
                    {d.kronos_pct != null ? (
                      <span className={d.kronos_pct >= 0 ? 'text-emerald-400' : 'text-red-400'}>
                        {d.kronos_pct >= 0 ? '+' : ''}{d.kronos_pct.toFixed(1)}%
                      </span>
                    ) : <span className="text-slate-600">—</span>}
                    {d.cluster > 1 && (
                      <span className="ml-1 text-amber-400 text-xs" title={`${d.cluster} insiders`}>×{d.cluster}</span>
                    )}
                  </td>
                  <td className="p-4 text-xs text-slate-400">{d.disclosure_date || '—'}</td>
                  <td className="p-4">
                    <ActionBadge action={d.action} />
                    {d.score_reason && (
                      <p className="mt-0.5 max-w-[160px] truncate text-xs text-slate-600" title={d.score_reason}>
                        {d.score_reason}
                      </p>
                    )}
                  </td>
                  <td className="p-4 text-center">
                    {d.ticker && d.action !== 'skip' ? (
                      <button
                        onClick={() => setExecuting(d.ticker)}
                        className={clsx(
                          'rounded-lg border px-3 py-1.5 text-xs font-medium transition-colors',
                          d.action === 'strong_sell' || d.action === 'sell'
                            ? 'border-red-700/50 bg-red-600/20 text-red-300 hover:bg-red-600/40'
                            : 'border-brand-700/50 bg-brand-600/20 text-brand-300 hover:bg-brand-600/40',
                        )}
                      >
                        <ShoppingCart className="inline h-3 w-3 mr-1" />Trade
                      </button>
                    ) : <span className="text-slate-700">—</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {executing && (
        <ExecutePanel
          ticker={executing}
          onClose={() => setExecuting(null)}
          onDone={() => {
            setExecuting(null)
            qc.invalidateQueries({ queryKey: ['portfolio'] })
          }}
        />
      )}
    </div>
  )
}
