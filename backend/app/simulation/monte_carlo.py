"""
Monte Carlo Simulation Runner
===============================
Runs N independent simulation realisations, each with stochastic:
  - Value range sampling (uniform within [lo, hi])
  - Optional random delay noise

Aggregates results into a distribution-level summary with confidence
intervals, percentile bands, and probability estimates.

DISCLAIMER: Educational research only. Not financial advice.
"""

import random
import logging
from typing import Optional

from sqlalchemy.orm import Session

from app.simulation.config import EngineConfig
from app.simulation.engine import run as run_single, _benchmark_return
from app.schemas.simulation import (
    MonteCarloConfig, MonteCarloResult, MonteCarloRunSummary, PortfolioPoint
)
from app.analytics.statistics import bootstrap_percentile, distribution_stats

logger = logging.getLogger(__name__)


def run_monte_carlo(db: Session, mc_config: MonteCarloConfig) -> MonteCarloResult:
    """
    Run `mc_config.n_runs` independent simulations.

    Each run uses a unique RNG seed derived from the master seed (or random).
    Samples value ranges probabilistically when value_estimation_method = "probabilistic".
    Optionally adds uniform delay noise of ±delay_noise_days.
    """
    from app.models.trader import Trader
    trader = db.query(Trader).filter(Trader.id == mc_config.trader_id).first()
    if not trader:
        raise ValueError(f"Trader {mc_config.trader_id} not found")

    master_seed = mc_config.random_seed or random.randint(0, 2**31)
    seeder = random.Random(master_seed)

    run_returns: list[float] = []
    run_sharpes: list[float] = []
    run_drawdowns: list[float] = []
    run_finals: list[float] = []
    run_summaries: list[MonteCarloRunSummary] = []
    run_histories: list[list[PortfolioPoint]] = []

    for run_id in range(mc_config.n_runs):
        run_seed = seeder.randint(0, 2**31)
        rng = random.Random(run_seed)

        noise = rng.randint(-mc_config.delay_noise_days, mc_config.delay_noise_days)
        delay = max(0, mc_config.delay_days + noise)

        engine_cfg = EngineConfig(
            trader_id=mc_config.trader_id,
            initial_capital=mc_config.initial_capital,
            delay_days=delay,
            allocation_strategy=mc_config.allocation_strategy.value,
            transaction_cost=mc_config.transaction_cost,
            slippage=mc_config.slippage,
            value_estimation_method=mc_config.value_estimation_method.value,
            max_position_pct=mc_config.max_position_pct,
            start_date=mc_config.start_date,
            end_date=mc_config.end_date,
            random_seed=run_seed,
        )

        try:
            result = run_single(db, engine_cfg, rng=rng)
        except Exception as exc:
            logger.warning("MC run %d failed: %s", run_id, exc)
            continue

        run_returns.append(result.total_return_pct)
        run_sharpes.append(result.sharpe_ratio)
        run_drawdowns.append(result.max_drawdown_pct)
        run_finals.append(result.final_value)
        run_histories.append(result.portfolio_history)

        run_summaries.append(
            MonteCarloRunSummary(
                run_id=run_id,
                total_return_pct=result.total_return_pct,
                final_value=result.final_value,
                sharpe_ratio=result.sharpe_ratio,
                max_drawdown_pct=result.max_drawdown_pct,
            )
        )

    if not run_returns:
        raise ValueError("All Monte Carlo runs failed")

    n = len(run_returns)
    sorted_runs = sorted(zip(run_returns, range(n)), key=lambda x: x[0])

    worst_idx  = sorted_runs[0][1]
    median_idx = sorted_runs[n // 2][1]
    best_idx   = sorted_runs[-1][1]

    pcts = bootstrap_percentile(run_returns, [2.5, 16, 50, 84, 97.5])
    stats = distribution_stats(run_returns)

    start = mc_config.start_date or (run_histories[0][0].date if run_histories else None)
    end   = mc_config.end_date   or (run_histories[0][-1].date if run_histories else None)
    bench_ret = _benchmark_return(db, start, end)
    bench_ret_pct = bench_ret * 100 if bench_ret is not None else None

    prob_positive = sum(1 for r in run_returns if r > 0) / n
    prob_beat = (
        sum(1 for r in run_returns if r > bench_ret_pct) / n
        if bench_ret_pct is not None else None
    )

    return MonteCarloResult(
        trader_id=mc_config.trader_id,
        trader_name=trader.name,
        n_runs=n,
        config=mc_config,
        mean_return_pct=round(stats.get("mean", 0), 4),
        median_return_pct=round(pcts[2], 4),
        std_return_pct=round(stats.get("std", 0), 4),
        ci_lower_95=round(pcts[0], 4),
        ci_upper_95=round(pcts[4], 4),
        ci_lower_68=round(pcts[1], 4),
        ci_upper_68=round(pcts[3], 4),
        prob_positive=round(prob_positive, 4),
        prob_beat_benchmark=round(prob_beat, 4) if prob_beat is not None else None,
        benchmark_return_pct=round(bench_ret_pct, 4) if bench_ret_pct is not None else None,
        runs=run_summaries,
        best_history=run_histories[best_idx],
        median_history=run_histories[median_idx],
        worst_history=run_histories[worst_idx],
    )
