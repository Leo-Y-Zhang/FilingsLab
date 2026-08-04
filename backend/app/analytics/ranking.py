"""
Ranking Service
===============
Computes composite performance scores across all traders and returns an
ordered leaderboard. All metrics are min-max normalised across the current
trader population so the score is invariant to absolute metric magnitudes.
"""

from sqlalchemy.orm import Session
from app.models.trader import Trader
from app.models.performance import PerformanceMetric
from app.schemas.trader import RankedTraderOut
from app.core.config import get_settings
from decimal import Decimal

settings = get_settings()


def _f(value) -> float:
    return float(value) if value is not None else 0.0


def _minmax(values: list[float]) -> list[float]:
    """Min-max normalise a list to [0, 1]. Returns uniform [0.5] if constant."""
    if not values:
        return []
    lo, hi = min(values), max(values)
    spread = hi - lo
    if spread == 0:
        return [0.5] * len(values)
    return [(v - lo) / spread for v in values]


def compute_rankings(db: Session) -> list[RankedTraderOut]:
    """
    Score = w_return × norm(return)
           + w_sharpe  × norm(sharpe)
           − w_drawdown × norm(|drawdown|)   ← penalty
           + w_consistency × norm(win_rate)

    All weights from settings (configurable via .env).
    """
    rows = (
        db.query(Trader, PerformanceMetric)
        .join(PerformanceMetric, Trader.id == PerformanceMetric.trader_id, isouter=True)
        .all()
    )
    if not rows:
        return []

    entries = [
        {
            "trader": t,
            "perf": p,
            "ret":     _f(p.total_return if p else None),
            "sharpe":  _f(p.sharpe_ratio if p else None),
            "dd_abs":  abs(_f(p.max_drawdown if p else None)),
            "wr":      _f(p.win_rate if p else None),
        }
        for t, p in rows
    ]

    ret_n    = _minmax([e["ret"]    for e in entries])
    sharpe_n = _minmax([e["sharpe"] for e in entries])
    dd_n     = _minmax([e["dd_abs"] for e in entries])
    wr_n     = _minmax([e["wr"]     for e in entries])

    w = settings
    ranked: list[RankedTraderOut] = []
    for i, entry in enumerate(entries):
        score = (
            w.rank_w_return       * ret_n[i]
            + w.rank_w_sharpe     * sharpe_n[i]
            - w.rank_w_drawdown   * dd_n[i]
            + w.rank_w_consistency * wr_n[i]
        )
        score = max(0.0, min(1.0, score))

        t, p = entry["trader"], entry["perf"]

        excess = None
        if p and p.total_return is not None and p.benchmark_return is not None:
            excess = Decimal(str(float(p.total_return) - float(p.benchmark_return)))

        ranked.append(
            RankedTraderOut(
                rank=0,
                trader_id=t.id,
                name=t.name,
                category=t.category,
                party=t.party,
                state=t.state,
                ranking_score=Decimal(str(round(score, 6))),
                total_return=p.total_return if p else None,
                annualized_return=p.annualized_return if p else None,
                sharpe_ratio=p.sharpe_ratio if p else None,
                sortino_ratio=p.sortino_ratio if p else None,
                max_drawdown=p.max_drawdown if p else None,
                volatility=p.volatility if p else None,
                win_rate=p.win_rate if p else None,
                trade_count=p.trade_count if p else None,
                benchmark_return=p.benchmark_return if p else None,
                excess_return=excess,
            )
        )

        if p:
            p.ranking_score = score

    db.commit()
    ranked.sort(key=lambda r: float(r.ranking_score or 0), reverse=True)
    for i, r in enumerate(ranked):
        r.rank = i + 1

    return ranked
