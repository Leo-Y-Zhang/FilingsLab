"""
Simulation configuration dataclass.
Separated from the Pydantic schema so the engine can be called without HTTP context.
"""

from dataclasses import dataclass
from datetime import date
from typing import Optional, Literal


@dataclass
class EngineConfig:
    """
    Immutable configuration for one simulation run.

    Execution model
    ---------------
    Trades are executed at  disclosure_date + delay_days,  NOT at trade_date.
    This is the fundamental research constraint: a follower can only act
    on information once it appears in the public record.

    delay_days = 0  → execute on the disclosure date itself
    delay_days = 1  → execute the next business day (default, most realistic)
    delay_days = 7  → execute one week after disclosure

    Allocation
    ----------
    proportional  : allocate proportional to the disclosed value_estimate,
                    capped at max_position_pct of current portfolio value.
    equal_weight  : allocate 1/N of available cash, where N is the number
                    of actionable buys on this day.

    Value estimation
    ----------------
    midpoint      : use pre-computed value_estimate = (lo + hi) / 2
    probabilistic : sample uniformly from [value_range_low, value_range_high]
                    (requires an external RNG — used by Monte Carlo)
    """
    trader_id: int
    initial_capital: float = 100_000.0
    delay_days: int = 1
    allocation_strategy: Literal["proportional", "equal_weight"] = "proportional"
    transaction_cost: float = 0.001    # fraction of trade value
    slippage: float = 0.0005           # fraction of price
    value_estimation_method: Literal["midpoint", "probabilistic"] = "midpoint"
    max_position_pct: float = 0.20     # maximum single-position weight
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    random_seed: Optional[int] = None
