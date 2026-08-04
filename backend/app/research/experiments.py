"""
Structured Experiment Framework
================================
Three pre-defined experiments investigating the core research question:
"Do publicly disclosed trades contain exploitable signals?"

Experiment 1 — Benchmark Comparison
   Tests whether traders outperform the market benchmark (SPY proxy).
   1-day execution delay after disclosure; proportional allocation.

Experiment 2 — Disclosure Delay Impact
   Sweeps delay from 0 to 14 days; measures return and risk-adjusted decay.
   Includes Sortino ratio alongside Sharpe.

Experiment 3 — Allocation Strategy Comparison
   Head-to-head: proportional (sized by disclosed value) vs equal-weight.
"""

import logging
from typing import Optional

from sqlalchemy.orm import Session

from app.models.trader import Trader
from app.simulation.config import EngineConfig
from app.simulation.engine import run as sim_run
from app.analytics.statistics import one_sample_t_test
from app.schemas.research import (
    Experiment1Result,
    Experiment2Result,
    Experiment3Result,
    ExperimentsBundle,
    BenchmarkComparisonRow,
    DelayComparisonRow,
    StrategyComparisonRow,
)

logger = logging.getLogger(__name__)

_EXP2_DELAYS = [0, 3, 7, 14]
_EXP1_DELAY = 1
_INITIAL_CAPITAL = 100_000.0


def _run_sim(
    db: Session,
    trader_id: int,
    delay: int,
    strategy: str = "proportional",
    initial_capital: float = _INITIAL_CAPITAL,
) -> Optional[object]:
    cfg = EngineConfig(
        trader_id=trader_id,
        initial_capital=initial_capital,
        delay_days=delay,
        allocation_strategy=strategy,
        transaction_cost=0.001,
        slippage=0.0005,
        value_estimation_method="midpoint",
    )
    try:
        return sim_run(db, cfg)
    except Exception as exc:
        logger.warning("Simulation failed trader=%d delay=%d strat=%s: %s", trader_id, delay, strategy, exc)
        return None


def experiment_1_benchmark_comparison(db: Session) -> Experiment1Result:
    traders = db.query(Trader).all()
    rows: list[BenchmarkComparisonRow] = []
    bench_ret_pct: Optional[float] = None

    for t in traders:
        result = _run_sim(db, t.id, _EXP1_DELAY)
        if result is None:
            continue

        if bench_ret_pct is None and result.benchmark_return_pct is not None:
            bench_ret_pct = result.benchmark_return_pct

        bench_pct = result.benchmark_return_pct or 0.0
        excess_pct = result.total_return_pct - bench_pct

        portfolio_vals = [p.portfolio_value for p in result.portfolio_history]
        if len(portfolio_vals) > 1:
            daily_rets = [
                (portfolio_vals[i] - portfolio_vals[i-1]) / portfolio_vals[i-1]
                for i in range(1, len(portfolio_vals))
            ]
            period_days = max(1, (result.simulation_end - result.simulation_start).days)
            bench_daily = (bench_pct / 100) / max(period_days, 1) if bench_pct else 0.0
            t_stat, p_val = one_sample_t_test([r * 100 for r in daily_rets], bench_daily * 100)
        else:
            t_stat, p_val = 0.0, 1.0

        rows.append(
            BenchmarkComparisonRow(
                trader_id=t.id,
                name=t.name,
                category=t.category,
                total_return_pct=result.total_return_pct,
                benchmark_return_pct=bench_pct,
                excess_return_pct=excess_pct,
                annualized_return_pct=result.annualized_return_pct,
                sharpe_ratio=result.sharpe_ratio,
                sortino_ratio=result.sortino_ratio,
                t_statistic=round(t_stat, 4),
                p_value=round(p_val, 4),
                statistically_significant=p_val < 0.05,
            )
        )

    rows.sort(key=lambda r: r.excess_return_pct, reverse=True)
    n_out = sum(1 for r in rows if r.excess_return_pct > 0)
    mean_excess = sum(r.excess_return_pct for r in rows) / max(len(rows), 1)

    return Experiment1Result(
        delay_days=_EXP1_DELAY,
        rows=rows,
        n_outperforming=n_out,
        n_underperforming=len(rows) - n_out,
        mean_excess_return_pct=round(mean_excess, 4),
        benchmark_return_pct=bench_ret_pct or 0.0,
    )


def experiment_2_delay_impact(db: Session) -> Experiment2Result:
    traders = db.query(Trader).all()
    delay_rows: list[DelayComparisonRow] = []

    for delay in _EXP2_DELAYS:
        returns = []
        excesses = []
        sharpes = []
        sortinos = []

        for t in traders:
            result = _run_sim(db, t.id, delay)
            if result is None:
                continue
            returns.append(result.total_return_pct)
            excesses.append(result.excess_return_pct or 0.0)
            sharpes.append(result.sharpe_ratio)
            sortinos.append(result.sortino_ratio)

        n = max(len(returns), 1)
        delay_rows.append(
            DelayComparisonRow(
                delay_days=delay,
                mean_total_return_pct=round(sum(returns) / n, 4),
                mean_excess_return_pct=round(sum(excesses) / n, 4),
                mean_sharpe=round(sum(sharpes) / n, 4),
                mean_sortino=round(sum(sortinos) / n, 4),
                n_traders=n,
            )
        )

    optimal = max(delay_rows, key=lambda r: r.mean_total_return_pct).delay_days

    return Experiment2Result(
        delays_tested=_EXP2_DELAYS,
        rows=delay_rows,
        optimal_delay_days=optimal,
    )


def experiment_3_strategy_comparison(db: Session) -> Experiment3Result:
    traders = db.query(Trader).all()
    rows: list[StrategyComparisonRow] = []

    for t in traders:
        prop_res  = _run_sim(db, t.id, _EXP1_DELAY, "proportional")
        equal_res = _run_sim(db, t.id, _EXP1_DELAY, "equal_weight")
        if prop_res is None or equal_res is None:
            continue

        prop_ret   = prop_res.total_return_pct
        equal_ret  = equal_res.total_return_pct

        margin = abs(prop_ret - equal_ret)
        if margin < 0.5:
            winner = "tie"
        elif prop_ret > equal_ret:
            winner = "proportional"
        else:
            winner = "equal_weight"

        rows.append(
            StrategyComparisonRow(
                trader_id=t.id,
                name=t.name,
                proportional_return_pct=prop_ret,
                equal_weight_return_pct=equal_ret,
                proportional_sharpe=prop_res.sharpe_ratio,
                equal_weight_sharpe=equal_res.sharpe_ratio,
                winner=winner,
            )
        )

    prop_wins  = sum(1 for r in rows if r.winner == "proportional")
    equal_wins = sum(1 for r in rows if r.winner == "equal_weight")
    ties = sum(1 for r in rows if r.winner == "tie")
    n = max(len(rows), 1)
    mean_prop  = sum(r.proportional_return_pct  for r in rows) / n
    mean_equal = sum(r.equal_weight_return_pct for r in rows) / n

    return Experiment3Result(
        delay_days=_EXP1_DELAY,
        rows=rows,
        proportional_wins=prop_wins,
        equal_weight_wins=equal_wins,
        ties=ties,
        mean_proportional_return_pct=round(mean_prop, 4),
        mean_equal_weight_return_pct=round(mean_equal, 4),
    )


def run_all_experiments(db: Session) -> ExperimentsBundle:
    logger.info("Running experiment 1: benchmark comparison...")
    exp1 = experiment_1_benchmark_comparison(db)

    logger.info("Running experiment 2: delay impact...")
    exp2 = experiment_2_delay_impact(db)

    logger.info("Running experiment 3: strategy comparison...")
    exp3 = experiment_3_strategy_comparison(db)

    return ExperimentsBundle(
        experiment_1=exp1,
        experiment_2=exp2,
        experiment_3=exp3,
    )
