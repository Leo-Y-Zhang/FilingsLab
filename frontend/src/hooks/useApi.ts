import { useQuery, useMutation } from '@tanstack/react-query'
import * as api from '@/services/api'
import type { SimulationConfig, MonteCarloConfig, ComparisonRequest } from '@/types'

export type { SimulationConfig, MonteCarloConfig, ComparisonRequest }

const STALE = 5 * 60_000

export const useTraders = (category?: string) =>
  useQuery({ queryKey: ['traders', category], queryFn: () => api.fetchTraders(category), staleTime: STALE })

export const useTrader = (id: number) =>
  useQuery({ queryKey: ['trader', id], queryFn: () => api.fetchTrader(id), enabled: id > 0, staleTime: STALE })

export const useTraderTrades = (id: number) =>
  useQuery({ queryKey: ['traderTrades', id], queryFn: () => api.fetchTraderTrades(id), enabled: id > 0, staleTime: STALE })

export const useRankings = (category?: string, limit?: number) =>
  useQuery({ queryKey: ['rankings', category, limit], queryFn: () => api.fetchRankings(category, limit), staleTime: STALE })

export const useSimulation  = () => useMutation({ mutationFn: (cfg: SimulationConfig) => api.runSimulation(cfg) })
export const useMonteCarlo  = () => useMutation({ mutationFn: (cfg: MonteCarloConfig) => api.runMonteCarlo(cfg) })

export const useExperiments = () =>
  useQuery({ queryKey: ['experiments'], queryFn: api.fetchExperiments, staleTime: 10 * 60_000 })

export const useAlphaDecay = (traderId: number, enabled = true) =>
  useQuery({
    queryKey: ['alphaDecay', traderId],
    queryFn: () => api.fetchAlphaDecay(traderId),
    enabled: enabled && traderId > 0,
    staleTime: 10 * 60_000,
  })

export const useHypothesisH1 = (category = 'politician') =>
  useQuery({ queryKey: ['h1', category], queryFn: () => api.fetchHypothesisH1(category), staleTime: 10 * 60_000 })

export const useHypothesisH2 = () =>
  useQuery({ queryKey: ['h2'], queryFn: api.fetchHypothesisH2, staleTime: 10 * 60_000 })

export const useComparison = () =>
  useMutation({ mutationFn: (req: ComparisonRequest) => api.runComparison(req) })

// ── Kronos Forecast ───────────────────────────────────────────────────────────
export const useKronosStatus = () =>
  useQuery({ queryKey: ['kronosStatus'], queryFn: api.fetchKronosStatus, staleTime: 60_000 })

export const useForecastHistory = (symbol: string, days = 60, enabled = true) =>
  useQuery({
    queryKey: ['forecastHistory', symbol, days],
    queryFn: () => api.fetchForecastHistory(symbol, days),
    enabled: enabled && symbol.length > 0,
    staleTime: 5 * 60_000,
  })

export const useForecast = () =>
  useMutation({
    mutationFn: ({ symbol, predDays }: { symbol: string; predDays: number }) =>
      api.runForecast(symbol, predDays),
  })
