"""
Hypothesis Testing Module
==========================
Structured hypothesis tests for the research layer.

H1: "Traders of a given category generate statistically significant excess
     returns relative to the market benchmark."

H2: "Acting on disclosures within 3 days produces higher risk-adjusted
     returns than acting after 14 days."
"""

import logging
from typing import Optional

from sqlalchemy.orm import Session

from app.simulation.config import EngineConfig
from app.simulation.engine import run as sim_run
from app.analytics.statistics import bootstrap_mean_ci, one_sample_t_test
from app.analytics.performance import daily_returns_from_values
from app.schemas.research import HypothesisTestResult

logger = logging.getLogger(__name__)


def _get_portfolio_daily_returns(db: Session, trader_id: int, delay: int) -> list[float]:
    cfg = EngineConfig(
        trader_id=trader_id,
        initial_capital=100_000.0,
        delay_days=delay,
        allocation_strategy="proportional",
        transaction_cost=0.001,
        slippage=0.0005,
        value_estimation_method="midpoint",
    )
    try:
        result = sim_run(db, cfg)
        vals = [p.portfolio_value for p in result.portfolio_history]
        return daily_returns_from_values(vals)
    except Exception:
        return []


def test_h1_excess_returns(db: Session, category: str = "politician") -> HypothesisTestResult:
    """
    H0: mean daily excess return of {category} traders == 0
    H1: mean daily excess return > 0

    One-sample t-test on daily portfolio returns minus benchmark daily return.
    """
    from app.models.trader import Trader
    traders = db.query(Trader).filter(Trader.category == category).all()
    if not traders:
        raise ValueError(f"No traders with category '{category}'")

    all_daily_rets: list[float] = []
    for t in traders:
        rets = _get_portfolio_daily_returns(db, t.id, delay=1)
        all_daily_rets.extend(rets)

    if not all_daily_rets:
        raise ValueError("No return data available")

    # ~10% historical SPY annual return → daily
    bench_daily_ret = 0.10 / 252
    excess_rets = [r - bench_daily_ret for r in all_daily_rets]

    t_stat, p_val = one_sample_t_test(excess_rets, 0.0)
    _, ci_lo, ci_hi = bootstrap_mean_ci(excess_rets, n_bootstrap=1000)

    mean_excess = sum(excess_rets) / len(excess_rets)
    reject = p_val < 0.05
    interpretation = (
        f"{'Reject' if reject else 'Fail to reject'} H0 (p={p_val:.4f}). "
        f"Mean daily excess return: {mean_excess * 100:.4f}%. "
        + ("Statistically significant outperformance detected." if reject and mean_excess > 0
           else "No statistically significant outperformance detected.")
    )

    return HypothesisTestResult(
        hypothesis=f"Do {category} traders generate positive excess returns?",
        null_hypothesis="Mean daily excess return = 0",
        test_name="One-sample t-test (daily excess returns)",
        test_statistic=round(t_stat, 4),
        p_value=round(p_val, 4),
        reject_null=reject,
        interpretation=interpretation,
        bootstrap_ci_lower=round(ci_lo * 100, 4),
        bootstrap_ci_upper=round(ci_hi * 100, 4),
    )


def test_h2_early_vs_late(db: Session) -> HypothesisTestResult:
    """
    H0: mean return at delay=3 == mean return at delay=14
    H1: early action (delay=3) produces higher returns

    Paired t-test on per-trader return differences.
    """
    from app.models.trader import Trader
    traders = db.query(Trader).all()[:6]   # subset for speed

    early_returns = []
    late_returns = []

    for t in traders:
        cfg_early = EngineConfig(t.id, delay_days=3,  initial_capital=100_000.0,
                                 allocation_strategy="proportional",
                                 transaction_cost=0.001, slippage=0.0005,
                                 value_estimation_method="midpoint")
        cfg_late  = EngineConfig(t.id, delay_days=14, initial_capital=100_000.0,
                                 allocation_strategy="proportional",
                                 transaction_cost=0.001, slippage=0.0005,
                                 value_estimation_method="midpoint")
        try:
            r_early = sim_run(db, cfg_early)
            r_late  = sim_run(db, cfg_late)
            early_returns.append(r_early.total_return_pct)
            late_returns.append(r_late.total_return_pct)
        except Exception:
            continue

    if not early_returns or not late_returns:
        raise ValueError("Insufficient data for H2 test")

    diffs = [e - l for e, l in zip(early_returns, late_returns)]
    t_stat, p_val = one_sample_t_test(diffs, 0.0)
    _, ci_lo, ci_hi = bootstrap_mean_ci(diffs, n_bootstrap=500)
    mean_diff = sum(diffs) / len(diffs)
    reject = p_val < 0.05

    interpretation = (
        f"{'Reject' if reject else 'Fail to reject'} H0 (p={p_val:.4f}). "
        f"Mean return difference (early − late): {mean_diff:.4f}%. "
        + ("Early action significantly outperforms late action." if reject and mean_diff > 0
           else "No significant difference between early and late action detected.")
    )

    return HypothesisTestResult(
        hypothesis="Does acting within 3 days outperform acting after 14 days?",
        null_hypothesis="Mean(return at 3 days) − Mean(return at 14 days) = 0",
        test_name="One-sample t-test on paired return differences",
        test_statistic=round(t_stat, 4),
        p_value=round(p_val, 4),
        reject_null=reject,
        interpretation=interpretation,
        bootstrap_ci_lower=round(ci_lo, 4),
        bootstrap_ci_upper=round(ci_hi, 4),
    )
