import { Link, useLocation } from 'react-router'
import { Rss, Sparkles, FlaskConical } from 'lucide-react'
import clsx from 'clsx'

const NAV = [
  { to: '/feed',     label: 'Live Feed', icon: Rss },
  { to: '/forecast', label: 'Forecast',  icon: Sparkles },
]

export default function Navbar() {
  const { pathname } = useLocation()

  return (
    <header className="sticky top-0 z-50 border-b border-surface-border bg-surface/95 backdrop-blur-md">
      <div className="h-px bg-gradient-to-r from-transparent via-brand-600/50 to-transparent" />
      <div className="mx-auto max-w-7xl px-4 sm:px-6">
        <div className="flex h-14 items-center justify-between">
          <Link to="/feed" className="flex items-center gap-2.5 group shrink-0">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-br from-brand-600 to-brand-700 shadow-lg shadow-brand-900/40 group-hover:from-brand-500 group-hover:to-brand-600 transition-all">
              <FlaskConical className="h-4 w-4 text-white" />
            </div>
            <div className="hidden sm:flex items-center gap-2">
              <span className="text-sm font-bold text-white tracking-tight">FilingsLab</span>
              <span className="rounded-md bg-brand-950 border border-brand-800/60 px-1.5 py-0.5 text-xs font-bold text-brand-400 font-mono">α</span>
            </div>
          </Link>

          <nav className="flex items-center gap-0.5">
            {NAV.map(({ to, label, icon: Icon }) => {
              const active = pathname.startsWith(to)
              return (
                <Link key={to} to={to}
                  className={clsx(
                    'flex items-center gap-1.5 rounded-lg px-3 py-2 text-xs font-medium transition-all duration-150',
                    active
                      ? 'bg-brand-600/15 text-brand-400 shadow-inner'
                      : 'text-slate-400 hover:bg-slate-800/60 hover:text-slate-200',
                  )}
                >
                  <Icon className="h-3.5 w-3.5 shrink-0" />
                  <span className="hidden sm:inline">{label}</span>
                </Link>
              )
            })}
          </nav>

          <div className="flex items-center gap-2 shrink-0">
            <div className="hidden sm:flex items-center gap-1.5 rounded-full border border-emerald-800/40 bg-emerald-950/40 px-2.5 py-1">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-pulse" />
              <span className="text-xs font-medium text-emerald-400">Live</span>
            </div>
          </div>
        </div>
      </div>
      <div className="border-t border-surface-border/30 px-4 py-0.5">
        <p className="text-center text-xs text-slate-700">
          Paper trading only — not financial advice
        </p>
      </div>
    </header>
  )
}
