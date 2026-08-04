from pydantic import BaseModel, ConfigDict
from datetime import date, datetime
from typing import Optional


class PerformanceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    trader_id: int
    total_return: Optional[float] = None
    annualized_return: Optional[float] = None
    benchmark_return: Optional[float] = None
    sharpe_ratio: Optional[float] = None
    sortino_ratio: Optional[float] = None
    volatility: Optional[float] = None
    max_drawdown: Optional[float] = None
    win_rate: Optional[float] = None
    trade_count: Optional[int] = None
    ranking_score: Optional[float] = None
    delay_days_used: Optional[int] = None
    period_start: Optional[date] = None
    period_end: Optional[date] = None
    computed_at: Optional[datetime] = None


class TradeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    trader_id: int
    trader_name: Optional[str] = None
    asset_symbol: str
    asset_name: Optional[str] = None
    transaction_type: str
    trade_date: date
    disclosure_date: date
    disclosure_delay_days: Optional[int] = None
    value_range_label: Optional[str] = None
    value_range_low: Optional[float] = None
    value_range_high: Optional[float] = None
    value_estimate: Optional[float] = None


class TraderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    category: str
    party: Optional[str] = None
    state: Optional[str] = None
    bio: Optional[str] = None
    created_at: datetime
    trade_count: Optional[int] = None


class TraderDetailOut(TraderOut):
    performance: Optional[PerformanceOut] = None


class RankedTraderOut(BaseModel):
    rank: int
    trader_id: int
    name: str
    category: str
    party: Optional[str] = None
    state: Optional[str] = None
    ranking_score: Optional[float] = None
    total_return: Optional[float] = None
    annualized_return: Optional[float] = None
    sharpe_ratio: Optional[float] = None
    sortino_ratio: Optional[float] = None
    max_drawdown: Optional[float] = None
    volatility: Optional[float] = None
    win_rate: Optional[float] = None
    trade_count: Optional[int] = None
    benchmark_return: Optional[float] = None
    excess_return: Optional[float] = None
