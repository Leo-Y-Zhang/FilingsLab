import { Component, type ReactNode } from 'react'
import { QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router'
import Navbar from '@/components/Layout/Navbar'
import Disclaimer from '@/components/Disclaimer'
import Feed from '@/pages/Feed'
import Forecast from '@/pages/Forecast'
import Simulation from '@/pages/Simulation'   // kept — accessible via /simulation
// The retry policy is a rate-limit control, so it lives in a testable module.
import { queryClient } from '@/services/queryClient'


class ErrorBoundary extends Component<{ children: ReactNode }, { error: Error | null }> {
  state = { error: null }
  static getDerivedStateFromError(error: Error) { return { error } }
  render() {
    if (this.state.error) {
      return (
        <div className="flex flex-col items-center justify-center gap-4 py-24 text-center">
          <p className="text-lg font-semibold text-red-400">Something went wrong on this page.</p>
          <p className="text-sm text-slate-500 font-mono max-w-lg break-all">
            {(this.state.error as Error).message}
          </p>
          <button
            onClick={() => this.setState({ error: null })}
            className="mt-2 rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-500"
          >
            Try again
          </button>
        </div>
      )
    }
    return this.props.children
  }
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <div className="flex min-h-screen flex-col bg-surface">
          <Navbar />
          <main className="mx-auto w-full max-w-7xl flex-1 px-4 py-8 sm:px-6 lg:px-8">
            <ErrorBoundary>
              <Routes>
                <Route path="/"           element={<Navigate to="/feed" replace />} />
                <Route path="/feed"       element={<Feed />} />
                <Route path="/forecast"   element={<Forecast />} />
                <Route path="/simulation" element={<Simulation />} />
                <Route path="*"           element={<Navigate to="/feed" replace />} />
              </Routes>
            </ErrorBoundary>
          </main>
          <Disclaimer />
        </div>
      </BrowserRouter>
    </QueryClientProvider>
  )
}
