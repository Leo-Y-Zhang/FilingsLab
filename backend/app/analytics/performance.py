"""
Performance Analytics Engine
==============================
Pure-function library for computing financial performance metrics.
No database dependency — accepts plain Python lists/floats.

All functions are independently unit-testable.
"""

import math
from typing import Optional


# ── Return metrics ─────────────────────────────────────────────────────────────

def total_return(initial: float, final: float) -> float:
    """(final - initial) / initial"""
    if initial <= 0:
        raise ValueError(f"initial value must be positive, got {initial}")
    return (final - initial) / initial


def annualized_return(total_ret: float, days: int) -> float:
    """
    CAGR: (1 + total_ret)^(365/days) - 1.
    Returns 0.0 for degenerate inputs.
    """
    if days <= 0:
        return 0.0
    years = days / 365.0
    try:
        return (1 + total_ret) ** (1.0 / years) - 1
    except (ZeroDivisionError, ValueError):
        return 0.0


# ── Risk metrics ───────────────────────────────────────────────────────────────

def daily_returns_from_values(portfolio_values: list[float]) -> list[float]:
    """Convert a value series to a list of daily percentage returns."""
    if len(portfolio_values) < 2:
        return []
    out = []
    for i in range(1, len(portfolio_values)):
        prev = portfolio_values[i - 1]
        curr = portfolio_values[i]
        if prev > 0:
            out.append((curr - prev) / prev)
        else:
            out.append(0.0)
    return out


def volatility(daily_rets: list[float]) -> float:
    """
    Annualised volatility = sample std-dev of daily returns × sqrt(252).
    Returns 0.0 if fewer than 2 observations.
    """
    n = len(daily_rets)
    if n < 2:
        return 0.0
    mu = sum(daily_rets) / n
    var = sum((r - mu) ** 2 for r in daily_rets) / (n - 1)
    return math.sqrt(var) * math.sqrt(252)


def sharpe_ratio(daily_rets: list[float], annual_risk_free: float = 0.04) -> float:
    """
    Sharpe = (mean excess daily return / daily return std-dev) × sqrt(252).
    Returns 0.0 if insufficient data or zero variance.
    """
    n = len(daily_rets)
    if n < 2:
        return 0.0
    daily_rf = annual_risk_free / 252
    excess = [r - daily_rf for r in daily_rets]
    mu = sum(excess) / n
    var = sum((r - mu) ** 2 for r in excess) / (n - 1)
    std = math.sqrt(var)
    if std == 0:
        return 0.0
    return (mu / std) * math.sqrt(252)


def sortino_ratio(daily_rets: list[float], annual_risk_free: float = 0.04) -> float:
    """
    Sortino = (mean excess daily return / downside deviation) × sqrt(252).

    Downside deviation uses only negative excess returns (below the risk-free rate),
    which penalises harmful volatility while not punishing upside variation.
    Returns 0.0 if insufficient data or zero downside variance.
    """
    n = len(daily_rets)
    if n < 2:
        return 0.0
    daily_rf = annual_risk_free / 252
    excess = [r - daily_rf for r in daily_rets]
    mean_excess = sum(excess) / n

    # Downside deviations: only returns below the risk-free threshold
    downside = [min(e, 0.0) ** 2 for e in excess]
    downside_var = sum(downside) / n   # population variance of downside returns
    downside_std = math.sqrt(downside_var)

    if downside_std == 0:
        return 0.0
    return (mean_excess / downside_std) * math.sqrt(252)


def max_drawdown(portfolio_values: list[float]) -> float:
    """
    Maximum peak-to-trough decline.
    Returns a negative decimal (e.g. -0.30 for -30%).
    Returns 0.0 for an empty or monotonically rising series.
    """
    if not portfolio_values:
        return 0.0
    peak = portfolio_values[0]
    mdd = 0.0
    for v in portfolio_values:
        if v > peak:
            peak = v
        dd = (v - peak) / peak
        if dd < mdd:
            mdd = dd
    return mdd


def win_rate(per_trade_returns: list[float]) -> float:
    """Fraction of trades with positive return."""
    if not per_trade_returns:
        return 0.0
    return sum(1 for r in per_trade_returns if r > 0) / len(per_trade_returns)


# ── Composite ─────────────────────────────────────────────────────────────────

def compute_all(
    portfolio_values: list[float],
    per_trade_returns: list[float],
    period_days: int,
    annual_risk_free: float = 0.04,
) -> dict:
    """
    Compute the complete metric set from a portfolio value time-series.

    Returns a dict with keys matching PerformanceMetric columns.
    All values are floats rounded to 6 decimal places, or None if uncomputable.
    """
    if len(portfolio_values) < 2:
        return {
            "total_return": None,
            "annualized_return": None,
            "sharpe_ratio": None,
            "sortino_ratio": None,
            "volatility": None,
            "max_drawdown": None,
            "win_rate": None,
            "trade_count": len(per_trade_returns),
        }

    initial = portfolio_values[0]
    final = portfolio_values[-1]

    tot = total_return(initial, final)
    ann = annualized_return(tot, period_days)
    d_rets = daily_returns_from_values(portfolio_values)
    vol = volatility(d_rets)
    sr = sharpe_ratio(d_rets, annual_risk_free)
    so = sortino_ratio(d_rets, annual_risk_free)
    mdd = max_drawdown(portfolio_values)
    wr = win_rate(per_trade_returns)

    def _r(v):
        return round(v, 6) if v is not None else None

    return {
        "total_return":      _r(tot),
        "annualized_return": _r(ann),
        "sharpe_ratio":      _r(sr),
        "sortino_ratio":     _r(so),
        "volatility":        _r(vol),
        "max_drawdown":      _r(mdd),
        "win_rate":          _r(wr),
        "trade_count":       len(per_trade_returns),
    }
