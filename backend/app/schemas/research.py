"""
Research layer schemas — experiments, alpha decay, hypothesis tests.
"""

from pydantic import BaseModel
from typing import Optional


# ── Alpha decay ────────────────────────────────────────────────────────────────

class AlphaDecayPoint(BaseModel):
    delay_days: int
    total_return_pct: float
    annualized_return_pct: float
    sharpe_ratio: float
    sortino_ratio: float
    excess_return_pct: Optional[float] = None
    ci_lower_95: Optional[float] = None
    ci_upper_95: Optional[float] = None


class AlphaDecayResult(BaseModel):
    trader_id: int
    trader_name: str
    benchmark_return_pct: Optional[float] = None
    data_points: list[AlphaDecayPoint]
    half_life_days: Optional[float] = None
    signal_duration_days: Optional[float] = None


# ── Experiments ───────────────────────────────────────────────────────────────

class BenchmarkComparisonRow(BaseModel):
    trader_id: int
    name: str
    category: str
    total_return_pct: float
    benchmark_return_pct: float
    excess_return_pct: float
    annualized_return_pct: float
    sharpe_ratio: float
    sortino_ratio: float
    t_statistic: Optional[float] = None
    p_value: Optional[float] = None
    statistically_significant: Optional[bool] = None


class Experiment1Result(BaseModel):
    experiment_name: str = "Trader vs Benchmark"
    description: str = (
        "Compares each trader's simulated portfolio return against the S&P 500 proxy "
        "(SPY) over the same period, using disclosure-date execution with a 1-day delay."
    )
    delay_days: int
    rows: list[BenchmarkComparisonRow]
    n_outperforming: int
    n_underperforming: int
    mean_excess_return_pct: float
    benchmark_return_pct: float


class DelayComparisonRow(BaseModel):
    delay_days: int
    mean_total_return_pct: float
    mean_excess_return_pct: float
    mean_sharpe: float
    mean_sortino: float
    n_traders: int


class Experiment2Result(BaseModel):
    experiment_name: str = "Disclosure Delay Impact"
    description: str = (
        "Tests how returns decay as we increase the lag between disclosure date and "
        "execution date. Delays tested: 0, 3, 7, 14 days."
    )
    delays_tested: list[int]
    rows: list[DelayComparisonRow]
    optimal_delay_days: int


class StrategyComparisonRow(BaseModel):
    trader_id: int
    name: str
    proportional_return_pct: float
    equal_weight_return_pct: float
    proportional_sharpe: float
    equal_weight_sharpe: float
    winner: str


class Experiment3Result(BaseModel):
    experiment_name: str = "Allocation Strategy Comparison"
    description: str = (
        "Compares proportional capital allocation (sized by disclosed value range) "
        "against equal-weight allocation (1/N of available cash per trade)."
    )
    delay_days: int
    rows: list[StrategyComparisonRow]
    proportional_wins: int
    equal_weight_wins: int
    ties: int
    mean_proportional_return_pct: float
    mean_equal_weight_return_pct: float


class ExperimentsBundle(BaseModel):
    experiment_1: Experiment1Result
    experiment_2: Experiment2Result
    experiment_3: Experiment3Result


# ── Hypothesis testing ────────────────────────────────────────────────────────

class HypothesisTestResult(BaseModel):
    hypothesis: str
    null_hypothesis: str
    test_name: str
    test_statistic: float
    p_value: float
    alpha: float = 0.05
    reject_null: bool
    interpretation: str
    bootstrap_ci_lower: Optional[float] = None
    bootstrap_ci_upper: Optional[float] = None
