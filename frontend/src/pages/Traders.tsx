import { useState } from 'react'
import { Users } from 'lucide-react'
import { useTraders } from '@/hooks/useApi'
import { Link } from 'react-router'
import clsx from 'clsx'

const CATEGORIES = ['all', 'politician', 'executive', 'insider']

const CATEGORY_STYLES: Record<string, string> = {
  politician: 'bg-purple-900/40 text-purple-300 border-purple-800/50',
  executive:  'bg-blue-900/40 text-blue-300 border-blue-800/50',
  insider:    'bg-orange-900/40 text-orange-300 border-orange-800/50',
}

export default function Traders() {
  const [category, setCategory] = useState<string | undefined>(undefined)
  const { data: traders, isLoading } = useTraders(category)

  return (
    <div className="space-y-6 animate-fade-in">
      <div>
        <h1 className="flex items-center gap-2 text-2xl font-bold text-white sm:text-3xl">
          <Users className="h-7 w-7 text-brand-400" />
          All Traders
        </h1>
        <p className="mt-1 text-slate-400">
          Browse all tracked traders and navigate to detailed disclosure histories, alpha decay
          analysis, and portfolio simulation.
        </p>
      </div>

      {/* Category filter */}
      <div className="flex flex-wrap gap-2">
        {CATEGORIES.map((cat) => (
          <button
            key={cat}
            onClick={() => setCategory(cat === 'all' ? undefined : cat)}
            className={clsx(
              'rounded-full px-4 py-1.5 text-sm font-medium capitalize transition-colors',
              (category === cat || (cat === 'all' && !category))
                ? 'bg-brand-600 text-white'
                : 'bg-surface-card text-slate-400 hover:bg-surface-elevated hover:text-white'
            )}
          >
            {cat}
          </button>
        ))}
      </div>

      {/* Trader grid */}
      {isLoading ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {[1, 2, 3, 4, 5, 6].map((i) => (
            <div key={i} className="h-36 animate-pulse rounded-xl bg-surface-card" />
          ))}
        </div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {traders?.map((trader) => (
            <Link
              key={trader.id}
              to={`/traders/${trader.id}`}
              className="group rounded-xl border border-surface-border bg-surface-card p-5 transition-all hover:border-brand-600/50 hover:shadow-lg hover:shadow-brand-900/20"
            >
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className="font-semibold text-white group-hover:text-brand-300 transition-colors">
                    {trader.name}
                  </p>
                  <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
                    <span className={clsx(
                      'rounded-full border px-2 py-0.5 text-xs font-medium capitalize',
                      CATEGORY_STYLES[trader.category] ?? 'bg-slate-800 text-slate-300'
                    )}>
                      {trader.category}
                    </span>
                    {trader.party && (
                      <span className="text-xs text-slate-500">{trader.party}</span>
                    )}
                    {trader.state && (
                      <span className="text-xs text-slate-500">· {trader.state}</span>
                    )}
                  </div>
                </div>
                <span className="shrink-0 rounded-full bg-surface-elevated px-2.5 py-1 text-xs font-mono text-slate-400">
                  {trader.trade_count ?? 0} trades
                </span>
              </div>
              {trader.bio && (
                <p className="mt-3 line-clamp-2 text-xs text-slate-500 leading-relaxed">
                  {trader.bio}
                </p>
              )}
            </Link>
          ))}
        </div>
      )}
    </div>
  )
}
