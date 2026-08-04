// ── Traders ───────────────────────────────────────────────────────────────────

export interface Performance {
  trader_id: number
  total_return?: number
  annualized_return?: number
  benchmark_return?: number
  sharpe_ratio?: number
  sortino_ratio?: number
  volatility?: number
  max_drawdown?: number
  win_rate?: number
  trade_count?: number
  ranking_score?: number
  delay_days_used?: number
  period_start?: string
  period_end?: string
}

export interface Trade {
  id: number
  trader_id: number
  trader_name?: string
  asset_symbol: string
  asset_name?: string
  transaction_type: 'buy' | 'sell'
  trade_date: string
  disclosure_date: string
  disclosure_delay_days?: number
  value_range_label?: string
  value_range_low?: number
  value_range_high?: number
  value_estimate?: number
}

export interface Trader {
  id: number
  name: string
  category: 'politician' | 'executive' | 'insider'
  party?: string
  state?: string
  bio?: string
  created_at: string
  trade_count?: number
}

export interface TraderDetail extends Trader {
  performance?: Performance
}

export interface RankedTrader {
  rank: number
  trader_id: number
  name: string
  category: string
  party?: string
  state?: string
  ranking_score?: number
  total_return?: number
  annualized_return?: number
  sharpe_ratio?: number
  sortino_ratio?: number
  max_drawdown?: number
  volatility?: number
  win_rate?: number
  trade_count?: number
  benchmark_return?: number
  excess_return?: number
}

// ── Simulation ────────────────────────────────────────────────────────────────

export type AllocationStrategy = 'proportional' | 'equal_weight'
export type ValueEstimationMethod = 'midpoint' | 'probabilistic'

export interface SimulationConfig {
  trader_id: number
  initial_capital: number
  delay_days: number
  allocation_strategy: AllocationStrategy
  transaction_cost: number
  slippage: number
  value_estimation_method: ValueEstimationMethod
  max_position_pct: number
  start_date?: string
  end_date?: string
}

export interface MonteCarloConfig extends SimulationConfig {
  n_runs: number
  delay_noise_days: number
  random_seed?: number
}

export interface PortfolioPoint {
  date: string
  portfolio_value: number
  cash: number
  invested: number
  cumulative_return: number
}

export interface SimulationResult {
  trader_id: number
  trader_name: string
  config: SimulationConfig
  starting_capital: number
  final_value: number
  total_return_pct: number
  annualized_return_pct: number
  sharpe_ratio: number
  sortino_ratio: number
  max_drawdown_pct: number
  volatility_pct: number
  win_rate: number
  trade_count: number
  executed_trade_count: number
  simulation_start: string
  simulation_end: string
  portfolio_history: PortfolioPoint[]
  benchmark_return_pct?: number
  excess_return_pct?: number
}

export interface MonteCarloRunSummary {
  run_id: number
  total_return_pct: number
  final_value: number
  sharpe_ratio: number
  max_drawdown_pct: number
}

export interface MonteCarloResult {
  trader_id: number
  trader_name: string
  n_runs: number
  config: MonteCarloConfig
  mean_return_pct: number
  median_return_pct: number
  std_return_pct: number
  ci_lower_95: number
  ci_upper_95: number
  ci_lower_68: number
  ci_upper_68: number
  prob_positive: number
  prob_beat_benchmark?: number
  benchmark_return_pct?: number
  runs: MonteCarloRunSummary[]
  best_history: PortfolioPoint[]
  median_history: PortfolioPoint[]
  worst_history: PortfolioPoint[]
}

// ── Research ──────────────────────────────────────────────────────────────────

export interface AlphaDecayPoint {
  delay_days: number
  total_return_pct: number
  annualized_return_pct: number
  sharpe_ratio: number
  sortino_ratio: number
  excess_return_pct?: number
  ci_lower_95?: number
  ci_upper_95?: number
}

export interface AlphaDecayResult {
  trader_id: number
  trader_name: string
  benchmark_return_pct?: number
  data_points: AlphaDecayPoint[]
  half_life_days?: number
  signal_duration_days?: number
}

export interface BenchmarkComparisonRow {
  trader_id: number
  name: string
  category: string
  total_return_pct: number
  benchmark_return_pct: number
  excess_return_pct: number
  annualized_return_pct: number
  sharpe_ratio: number
  sortino_ratio: number
  t_statistic?: number
  p_value?: number
  statistically_significant?: boolean
}

export interface DelayComparisonRow {
  delay_days: number
  mean_total_return_pct: number
  mean_excess_return_pct: number
  mean_sharpe: number
  mean_sortino: number
  n_traders: number
}

export interface StrategyComparisonRow {
  trader_id: number
  name: string
  proportional_return_pct: number
  equal_weight_return_pct: number
  proportional_sharpe: number
  equal_weight_sharpe: number
  winner: 'proportional' | 'equal_weight' | 'tie'
}

export interface Experiment1Result {
  experiment_name: string
  description: string
  delay_days: number
  rows: BenchmarkComparisonRow[]
  n_outperforming: number
  n_underperforming: number
  mean_excess_return_pct: number
  benchmark_return_pct: number
}

export interface Experiment2Result {
  experiment_name: string
  description: string
  delays_tested: number[]
  rows: DelayComparisonRow[]
  optimal_delay_days: number
}

export interface Experiment3Result {
  experiment_name: string
  description: string
  delay_days: number
  rows: StrategyComparisonRow[]
  proportional_wins: number
  equal_weight_wins: number
  ties: number
  mean_proportional_return_pct: number
  mean_equal_weight_return_pct: number
}

export interface ExperimentsBundle {
  experiment_1: Experiment1Result
  experiment_2: Experiment2Result
  experiment_3: Experiment3Result
}

export interface HypothesisTestResult {
  hypothesis: string
  null_hypothesis: string
  test_name: string
  test_statistic: number
  p_value: number
  alpha: number
  reject_null: boolean
  interpretation: string
  bootstrap_ci_lower?: number
  bootstrap_ci_upper?: number
}

// ── Comparison ────────────────────────────────────────────────────────────────

export interface ComparisonRequest {
  trader_ids: number[]
  delay_days: number
  initial_capital: number
  start_date?: string
  end_date?: string
}

export interface ComparisonEntry {
  trader_id: number
  name: string
  category: string
  total_return_pct: number
  annualized_return_pct: number
  sharpe_ratio: number
  sortino_ratio: number
  max_drawdown_pct: number
  volatility_pct: number
  win_rate: number
  excess_return_pct?: number
  benchmark_return_pct?: number
  trade_count: number
  executed_trade_count: number
  portfolio_history: PortfolioPoint[]
}

export interface ComparisonResult {
  delay_days: number
  initial_capital: number
  benchmark_return_pct?: number
  entries: ComparisonEntry[]
  best_trader_id?: number
  best_sharpe_trader_id?: number
  best_sortino_trader_id?: number
}

// ── Kronos Forecast ───────────────────────────────────────────────────────────

export interface ForecastPoint {
  date: string
  open: number
  high: number
  low: number
  close: number
}

export interface ForecastResult {
  source: 'kronos' | 'cache'
  model: string
  device: string
  symbol: string
  predictions: ForecastPoint[]
}

export interface KronosStatus {
  available: boolean
  model: string
  device: string
  gpu: string | null
  kronos_lib_path: string
  setup_required: boolean
  setup_instructions: string | null
}
