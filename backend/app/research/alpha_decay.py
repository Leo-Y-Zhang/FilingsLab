"""
Alpha Decay Analysis
====================
Tests how simulated excess returns degrade as a function of execution delay.

The central research question:
"If a follower acts D days after a disclosure is published, how does return
 compare to acting immediately? Does the signal decay — and how fast?"

Methodology:
1. For each delay D in settings.alpha_decay_delays:
   - Run the simulation engine with delay_days = D
   - Record return, Sharpe, Sortino, and excess return vs benchmark

2. Estimate the "half-life" day where excess return halves and
   the "signal duration" day where excess return crosses zero.
"""

import logging
from typing import Optional

from sqlalchemy.orm import Session

from app.simulation.config import EngineConfig
from app.simulation.engine import run as sim_run
from app.schemas.research import AlphaDecayResult, AlphaDecayPoint
from app.analytics.statistics import bootstrap_mean_ci
from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


def compute_alpha_decay(
    db: Session,
    trader_id: int,
    delays: Optional[list[int]] = None,
    n_bootstrap: int = 500,
    initial_capital: float = 100_000.0,
) -> AlphaDecayResult:
    from app.models.trader import Trader
    trader = db.query(Trader).filter(Trader.id == trader_id).first()
    if not trader:
        raise ValueError(f"Trader {trader_id} not found")

    test_delays = delays or settings.alpha_decay_delays
    data_points: list[AlphaDecayPoint] = []
    bench_ret: Optional[float] = None

    for delay in sorted(test_delays):
        cfg = EngineConfig(
            trader_id=trader_id,
            initial_capital=initial_capital,
            delay_days=delay,
            allocation_strategy="proportional",
            transaction_cost=0.001,
            slippage=0.0005,
            value_estimation_method="midpoint",
        )

        try:
            result = sim_run(db, cfg)
        except Exception as exc:
            logger.warning("Alpha decay: delay=%d failed: %s", delay, exc)
            continue

        if bench_ret is None and result.benchmark_return_pct is not None:
            bench_ret = result.benchmark_return_pct

        excess = result.excess_return_pct
        boot_returns: list[float] = [result.total_return_pct]
        ci_lo = ci_hi = None
        if len(boot_returns) >= 2:
            _, ci_lo, ci_hi = bootstrap_mean_ci(boot_returns, n_bootstrap=min(n_bootstrap, 200))

        data_points.append(
            AlphaDecayPoint(
                delay_days=delay,
                total_return_pct=result.total_return_pct,
                annualized_return_pct=result.annualized_return_pct,
                sharpe_ratio=result.sharpe_ratio,
                sortino_ratio=result.sortino_ratio,
                excess_return_pct=excess,
                ci_lower_95=round(ci_lo, 4) if ci_lo is not None else None,
                ci_upper_95=round(ci_hi, 4) if ci_hi is not None else None,
            )
        )

    half_life = _interpolate_half_life(data_points)
    signal_dur = _interpolate_zero_crossing(data_points)

    return AlphaDecayResult(
        trader_id=trader_id,
        trader_name=trader.name,
        benchmark_return_pct=bench_ret,
        data_points=data_points,
        half_life_days=half_life,
        signal_duration_days=signal_dur,
    )


def _interpolate_half_life(points: list[AlphaDecayPoint]) -> Optional[float]:
    valid = [(p.delay_days, p.excess_return_pct) for p in points if p.excess_return_pct is not None]
    if len(valid) < 2:
        return None
    baseline = valid[0][1]
    if baseline <= 0:
        return None
    target = baseline / 2.0
    for i in range(1, len(valid)):
        d0, r0 = valid[i - 1]
        d1, r1 = valid[i]
        if r1 <= target <= r0:
            if r0 - r1 == 0:
                return float(d0)
            frac = (r0 - target) / (r0 - r1)
            return round(d0 + frac * (d1 - d0), 1)
    return None


def _interpolate_zero_crossing(points: list[AlphaDecayPoint]) -> Optional[float]:
    valid = [(p.delay_days, p.excess_return_pct) for p in points if p.excess_return_pct is not None]
    if len(valid) < 2:
        return None
    for i in range(1, len(valid)):
        d0, r0 = valid[i - 1]
        d1, r1 = valid[i]
        if r0 > 0 and r1 <= 0:
            if r0 - r1 == 0:
                return float(d0)
            frac = r0 / (r0 - r1)
            return round(d0 + frac * (d1 - d0), 1)
    return None
