import { AlertTriangle } from 'lucide-react'

export default function Disclaimer({ compact = false }: { compact?: boolean }) {
  if (compact) {
    return (
      <div className="flex items-center gap-2 rounded-lg border border-amber-800/40 bg-amber-950/30 px-3 py-2 text-xs text-amber-400/90">
        <AlertTriangle className="h-3.5 w-3.5 shrink-0" />
        Simulations are historical reconstructions for educational research only and do not constitute financial advice.
      </div>
    )
  }
  return (
    <div className="px-4 py-2 text-center">
      <p className="text-xs text-slate-700">
        Historical simulation using synthetic price data · not financial advice · for personal research use
      </p>
    </div>
  )
}
