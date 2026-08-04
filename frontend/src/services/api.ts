import axios from 'axios'
import type {
  Trader, TraderDetail, Trade, RankedTrader,
  SimulationConfig, SimulationResult,
  MonteCarloConfig, MonteCarloResult,
  AlphaDecayResult, ExperimentsBundle, HypothesisTestResult,
  ComparisonRequest, ComparisonResult,
  ForecastResult, ForecastPoint, KronosStatus,
} from '@/types'

const client = axios.create({
  baseURL: import.meta.env.VITE_API_URL ?? '/api',
  timeout: 120_000,
  headers: { 'Content-Type': 'application/json' },
})

// ── Traders ───────────────────────────────────────────────────────────────────
export const fetchTraders = (category?: string) =>
  client.get<Trader[]>('/traders', { params: category ? { category } : {} }).then(r => r.data)
export const fetchTrader = (id: number) =>
  client.get<TraderDetail>(`/traders/${id}`).then(r => r.data)
export const fetchTraderTrades = (id: number, limit = 200) =>
  client.get<Trade[]>(`/traders/${id}/trades`, { params: { limit } }).then(r => r.data)

// ── Rankings ──────────────────────────────────────────────────────────────────
export const fetchRankings = (category?: string, limit = 20) =>
  client.get<RankedTrader[]>('/rankings', { params: { limit, ...(category ? { category } : {}) } })
        .then(r => r.data)

// ── Simulation ────────────────────────────────────────────────────────────────
export const runSimulation = (cfg: SimulationConfig) =>
  client.post<SimulationResult>('/simulate', cfg).then(r => r.data)
export const runMonteCarlo = (cfg: MonteCarloConfig) =>
  client.post<MonteCarloResult>('/simulate/monte-carlo', cfg).then(r => r.data)

// ── Research ──────────────────────────────────────────────────────────────────
export const fetchExperiments = () =>
  client.get<ExperimentsBundle>('/research/experiments').then(r => r.data)
export const fetchAlphaDecay = (traderId: number, delays?: number[]) =>
  client.get<AlphaDecayResult>(`/research/alpha-decay/${traderId}`, {
    params: delays ? { delays: delays.join(',') } : {},
  }).then(r => r.data)
export const fetchHypothesisH1 = (category = 'politician') =>
  client.get<HypothesisTestResult>('/research/hypothesis/h1', { params: { category } }).then(r => r.data)
export const fetchHypothesisH2 = () =>
  client.get<HypothesisTestResult>('/research/hypothesis/h2').then(r => r.data)

// ── Comparison ────────────────────────────────────────────────────────────────
export const runComparison = (req: ComparisonRequest) =>
  client.post<ComparisonResult>('/compare', req).then(r => r.data)

// ── Kronos Forecast ───────────────────────────────────────────────────────────
export const fetchKronosStatus = () =>
  client.get<KronosStatus>('/forecast/status').then(r => r.data)

export const fetchForecastHistory = (symbol: string, days = 60) =>
  client.get<ForecastPoint[]>(`/forecast/history/${symbol}`, { params: { days } }).then(r => r.data)

export const runForecast = (symbol: string, predDays = 10) =>
  client.get<ForecastResult>(`/forecast/${symbol}`, { params: { pred_days: predDays } }).then(r => r.data)
