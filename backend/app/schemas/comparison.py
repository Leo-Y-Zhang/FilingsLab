"""
Comparison schemas — multi-trader side-by-side analysis.
"""

from pydantic import BaseModel, Field
from datetime import date
from typing import Optional
from app.schemas.simulation import PortfolioPoint


class ComparisonRequest(BaseModel):
    trader_ids: list[int] = Field(..., min_length=2, max_length=6)
    delay_days: int = Field(default=1, ge=0, le=365)
    initial_capital: float = Field(default=100_000.0, gt=0)
    start_date: Optional[date] = None
    end_date: Optional[date] = None


class ComparisonEntry(BaseModel):
    trader_id: int
    name: str
    category: str
    total_return_pct: float
    annualized_return_pct: float
    sharpe_ratio: float
    sortino_ratio: float
    max_drawdown_pct: float
    volatility_pct: float
    win_rate: float
    excess_return_pct: Optional[float] = None
    benchmark_return_pct: Optional[float] = None
    trade_count: int
    executed_trade_count: int
    portfolio_history: list[PortfolioPoint]


class ComparisonResult(BaseModel):
    delay_days: int
    initial_capital: float
    benchmark_return_pct: Optional[float] = None
    entries: list[ComparisonEntry]
    best_trader_id: Optional[int] = None      # by total return
    best_sharpe_trader_id: Optional[int] = None   # by Sharpe ratio
    best_sortino_trader_id: Optional[int] = None  # by Sortino ratio
