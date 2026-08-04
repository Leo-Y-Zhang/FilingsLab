"""
Simulation schemas — request/response models for the simulation and Monte Carlo APIs.
"""

from pydantic import BaseModel, Field
from datetime import date
from typing import Optional
from enum import Enum


class AllocationStrategy(str, Enum):
    proportional = "proportional"
    equal_weight = "equal_weight"


class ValueEstimationMethod(str, Enum):
    midpoint = "midpoint"
    probabilistic = "probabilistic"


class SimulationConfig(BaseModel):
    """
    Full configuration for a portfolio simulation run.

    Execution model: trades are executed at disclosure_date + delay_days,
    NOT at trade_date. This reflects the realistic constraint that an
    observer can only act once a disclosure enters the public record.
    """
    trader_id: int
    initial_capital: float = Field(default=100_000.0, gt=0, le=10_000_000)
    delay_days: int = Field(
        default=1, ge=0, le=365,
        description="Days after disclosure date to execute. 0 = execute on disclosure day.",
    )
    allocation_strategy: AllocationStrategy = AllocationStrategy.proportional
    transaction_cost: float = Field(
        default=0.001, ge=0, le=0.05,
        description="Fraction of trade value charged as transaction cost (e.g. 0.001 = 0.1%).",
    )
    slippage: float = Field(
        default=0.0005, ge=0, le=0.02,
        description="Fraction of price lost to market impact / bid-ask spread.",
    )
    value_estimation_method: ValueEstimationMethod = ValueEstimationMethod.midpoint
    max_position_pct: float = Field(
        default=0.20, gt=0, le=1.0,
        description="Maximum fraction of portfolio allocated to a single position.",
    )
    start_date: Optional[date] = None
    end_date: Optional[date] = None


class MonteCarloConfig(SimulationConfig):
    """
    Extends SimulationConfig with Monte Carlo parameters.
    Each run independently samples value ranges and (optionally) delay noise.
    """
    n_runs: int = Field(default=500, ge=10, le=2000)
    delay_noise_days: int = Field(
        default=0, ge=0, le=5,
        description="±N days of uniform random noise added to delay_days per run.",
    )
    random_seed: Optional[int] = None


# ── Response schemas ─────────────────────────────────────────────────────────

class PortfolioPoint(BaseModel):
    date: date
    portfolio_value: float
    cash: float
    invested: float
    cumulative_return: float


class SimulationResult(BaseModel):
    trader_id: int
    trader_name: str
    config: SimulationConfig
    starting_capital: float
    final_value: float
    total_return_pct: float
    annualized_return_pct: float
    sharpe_ratio: float
    sortino_ratio: float
    max_drawdown_pct: float
    volatility_pct: float
    trade_count: int
    executed_trade_count: int
    simulation_start: date
    simulation_end: date
    portfolio_history: list[PortfolioPoint]
    win_rate: float = 0.0
    benchmark_return_pct: Optional[float] = None
    excess_return_pct: Optional[float] = None


class MonteCarloRunSummary(BaseModel):
    run_id: int
    total_return_pct: float
    final_value: float
    sharpe_ratio: float
    max_drawdown_pct: float


class MonteCarloResult(BaseModel):
    trader_id: int
    trader_name: str
    n_runs: int
    config: MonteCarloConfig
    mean_return_pct: float
    median_return_pct: float
    std_return_pct: float
    ci_lower_95: float
    ci_upper_95: float
    ci_lower_68: float
    ci_upper_68: float
    prob_positive: float
    prob_beat_benchmark: Optional[float] = None
    benchmark_return_pct: Optional[float] = None
    runs: list[MonteCarloRunSummary]
    best_history: list[PortfolioPoint]
    median_history: list[PortfolioPoint]
    worst_history: list[PortfolioPoint]
