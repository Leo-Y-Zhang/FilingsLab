import clsx from 'clsx'
import type { ReactNode } from 'react'

export default function MetricCard({
  label, value, subtitle, trend, highlight, className,
}: {
  label: string; value: ReactNode; subtitle?: string
  trend?: 'up' | 'down' | 'neutral'; highlight?: boolean; className?: string
}) {
  return (
    <div className={clsx(
      'rounded-xl border p-4 transition-all group relative overflow-hidden',
      highlight
        ? 'border-brand-600/50 bg-brand-950/30 shadow-lg shadow-brand-900/20'
        : 'border-surface-border bg-surface-card hover:border-brand-600/30',
      className,
    )}>
      {/* Accent bar at top */}
      <div className={clsx(
        'absolute inset-x-0 top-0 h-px',
        highlight ? 'bg-gradient-to-r from-brand-600 to-brand-400' : 'bg-surface-elevated',
      )} />

      <p className="text-xs font-semibold uppercase tracking-widest text-slate-500">{label}</p>

      <div className="mt-2 flex items-end gap-2">
        <div className={clsx(
          'text-2xl font-bold tabular-nums font-mono leading-none',
          trend === 'up'   && 'text-emerald-400',
          trend === 'down' && 'text-red-400',
          (!trend || trend === 'neutral') && 'text-white',
        )}>{value}</div>

        {trend && trend !== 'neutral' && (
          <span className={clsx(
            'mb-0.5 flex items-center text-xs font-bold',
            trend === 'up' ? 'text-emerald-500' : 'text-red-500',
          )}>
            {trend === 'up' ? '▲' : '▼'}
          </span>
        )}
      </div>

      {subtitle && (
        <p className="mt-1 text-xs text-slate-500 leading-snug">{subtitle}</p>
      )}
    </div>
  )
}
