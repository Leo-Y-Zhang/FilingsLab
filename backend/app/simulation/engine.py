"""
Core Simulation Engine
=======================
Replays a trader's public disclosures as a follower portfolio.

CRITICAL DESIGN DECISION
------------------------
Trades are executed at  disclosure_date + delay_days  (not at trade_date).
This models the realistic constraint that a market participant can only act
on information once it has entered the public record.

trade_date      : when the insider actually traded (not yet public)
disclosure_date : when the filing became publicly visible
execution_date  : disclosure_date + config.delay_days  ← what we simulate

DISCLAIMER
----------
This is a historical simulation for educational research only.
It does not constitute financial advice or real trading of any kind.
"""

import random
from datetime import date, timedelta
from typing import Optional
import logging

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.trade import Trade
from app.models.price import Price
from app.models.trader import Trader
from app.simulation.config import EngineConfig
from app.simulation.portfolio import Portfolio
from app.schemas.simulation import PortfolioPoint, SimulationResult
from app.analytics.performance import compute_all, daily_returns_from_values

logger = logging.getLogger(__name__)

PRICE_LOOKBACK_DAYS = 10   # search window for nearest price on non-trading days


# ── Price helpers ──────────────────────────────────────────────────────────────

def _lookup_price(db: Session, symbol: str, target: date) -> Optional[float]:
    """Return the most recent closing price on or before target."""
    row = (
        db.query(Price)
        .filter(
            Price.asset_symbol == symbol,
            Price.date <= target,
            Price.date >= target - timedelta(days=PRICE_LOOKBACK_DAYS),
        )
        .order_by(Price.date.desc())
        .first()
    )
    return float(row.closing_price) if row else None


def _prices_on_date(db: Session, symbols: set[str], target: date) -> dict[str, float]:
    """Return {symbol: price} for all known symbols on or before target."""
    from_date = target - timedelta(days=PRICE_LOOKBACK_DAYS)
    rows = (
        db.query(Price)
        .filter(
            Price.asset_symbol.in_(symbols),
            Price.date >= from_date,
            Price.date <= target,
        )
        .all()
    )
    result: dict[str, float] = {}
    for row in sorted(rows, key=lambda r: r.date):
        result[row.asset_symbol] = float(row.closing_price)
    return result


# ── Value estimation ──────────────────────────────────────────────────────────

def _estimate_value(
    trade: Trade,
    method: str,
    rng: Optional[random.Random],
) -> float:
    """
    Estimate the trade's cash value from its reported range.

    midpoint:      uses the pre-computed (lo+hi)/2
    probabilistic: samples uniformly from [lo, hi] — used in Monte Carlo
    """
    lo = float(trade.value_range_low) if trade.value_range_low else None
    hi = float(trade.value_range_high) if trade.value_range_high else None

    if method == "probabilistic" and rng and lo is not None and hi is not None:
        return rng.uniform(lo, hi)

    if trade.value_estimate:
        return float(trade.value_estimate)
    if lo is not None and hi is not None:
        return (lo + hi) / 2
    return 10_000.0


# ── Benchmark helper ──────────────────────────────────────────────────────────

def _benchmark_return(db: Session, start: Optional[date], end: Optional[date]) -> Optional[float]:
    """Total return for 'SPY' over the period."""
    if not start or not end:
        return None
    p0 = _lookup_price(db, "SPY", start)
    p1 = _lookup_price(db, "SPY", end)
    if p0 and p1 and p0 > 0:
        return (p1 - p0) / p0
    return None


# ── Core engine ───────────────────────────────────────────────────────────────

def run(
    db: Session,
    config: EngineConfig,
    rng: Optional[random.Random] = None,
) -> SimulationResult:
    """
    Execute one simulation run and return a full SimulationResult.

    Parameters
    ----------
    db     : SQLAlchemy session
    config : EngineConfig (see simulation/config.py)
    rng    : optional seeded random.Random for Monte Carlo reproducibility
    """
    trader = db.query(Trader).filter(Trader.id == config.trader_id).first()
    if not trader:
        raise ValueError(f"Trader {config.trader_id} not found")

    all_trades: list[Trade] = (
        db.query(Trade)
        .filter(Trade.trader_id == config.trader_id)
        .order_by(Trade.disclosure_date, Trade.trade_date)
        .all()
    )
    if not all_trades:
        raise ValueError(f"No trades found for trader {config.trader_id}")

    sim_start = config.start_date or all_trades[0].disclosure_date

    # Cap end date to the latest price in the database so benchmark lookups
    # never fall outside the synthetic price range.
    latest_price_date: Optional[date] = db.query(func.max(Price.date)).scalar()
    default_end = latest_price_date if latest_price_date else date.today()
    sim_end = config.end_date or default_end

    if sim_start >= sim_end:
        raise ValueError("start_date must precede end_date")

    # Index trades by their execution date (disclosure_date + delay_days)
    trades_by_exec: dict[date, list[Trade]] = {}
    for t in all_trades:
        exec_date = t.disclosure_date + timedelta(days=config.delay_days)
        if sim_start <= exec_date <= sim_end:
            trades_by_exec.setdefault(exec_date, []).append(t)

    symbols = {t.asset_symbol for t in all_trades} | {"SPY"}

    portfolio = Portfolio(initial_capital=config.initial_capital)
    history: list[PortfolioPoint] = []
    portfolio_values: list[float] = []
    per_trade_returns: list[float] = []
    executed_count = 0

    current = sim_start
    while current <= sim_end:
        day_trades = trades_by_exec.get(current, [])
        prices = _prices_on_date(db, symbols, current)

        # ── Execute trades ───────────────────────────────────────────────────
        if day_trades:
            buy_trades = [t for t in day_trades if t.transaction_type == "buy"]
            sell_trades = [t for t in day_trades if t.transaction_type == "sell"]

            # Sells first — free up cash before buys
            for trade in sell_trades:
                price = prices.get(trade.asset_symbol)
                if price is None:
                    continue
                slippage_adj = price * (1 - config.slippage)
                value = _estimate_value(trade, config.value_estimation_method, rng)
                avg_cost_before = (
                    portfolio.positions[trade.asset_symbol].avg_cost
                    if trade.asset_symbol in portfolio.positions else slippage_adj
                )
                proceeds = portfolio.sell(
                    trade.asset_symbol, value, slippage_adj, config.transaction_cost
                )
                if proceeds > 0:
                    pnl_pct = (slippage_adj - avg_cost_before) / avg_cost_before if avg_cost_before > 0 else 0
                    per_trade_returns.append(pnl_pct)
                    executed_count += 1

            for trade in buy_trades:
                price = prices.get(trade.asset_symbol)
                if price is None:
                    continue
                slippage_adj = price * (1 + config.slippage)
                value = _estimate_value(trade, config.value_estimation_method, rng)
                portfolio_total = portfolio.total_value(prices)
                max_alloc = portfolio_total * config.max_position_pct

                if config.allocation_strategy == "proportional":
                    allocation = min(value, max_alloc, portfolio.cash)
                else:  # equal_weight
                    equal_share = portfolio.cash / max(1, len(buy_trades))
                    allocation = min(equal_share, max_alloc)

                if allocation <= 0:
                    continue

                shares = portfolio.buy(
                    trade.asset_symbol, allocation, slippage_adj, config.transaction_cost
                )
                if shares > 0:
                    per_trade_returns.append(0.0)
                    executed_count += 1

        # ── Mark to market ───────────────────────────────────────────────────
        total_val = portfolio.total_value(prices)
        portfolio_values.append(total_val)

        cum_ret = (total_val - config.initial_capital) / config.initial_capital
        history.append(
            PortfolioPoint(
                date=current,
                portfolio_value=round(total_val, 2),
                cash=round(portfolio.cash, 2),
                invested=round(total_val - portfolio.cash, 2),
                cumulative_return=round(cum_ret, 6),
            )
        )

        current += timedelta(days=1)

    if not portfolio_values:
        raise ValueError("Simulation produced no data points")

    period_days = max((sim_end - sim_start).days, 1)
    metrics = compute_all(portfolio_values, per_trade_returns, period_days)
    bench_ret = _benchmark_return(db, sim_start, sim_end)

    final_val = portfolio_values[-1]
    tot_ret_pct = (final_val - config.initial_capital) / config.initial_capital * 100

    from app.schemas.simulation import SimulationConfig as SimCfgSchema, AllocationStrategy, ValueEstimationMethod
    config_out = SimCfgSchema(
        trader_id=config.trader_id,
        initial_capital=config.initial_capital,
        delay_days=config.delay_days,
        allocation_strategy=AllocationStrategy(config.allocation_strategy),
        transaction_cost=config.transaction_cost,
        slippage=config.slippage,
        value_estimation_method=ValueEstimationMethod(config.value_estimation_method),
        max_position_pct=config.max_position_pct,
        start_date=config.start_date,
        end_date=config.end_date,
    )

    return SimulationResult(
        trader_id=config.trader_id,
        trader_name=trader.name,
        config=config_out,
        starting_capital=config.initial_capital,
        final_value=round(final_val, 2),
        total_return_pct=round(tot_ret_pct, 4),
        annualized_return_pct=round((metrics.get("annualized_return") or 0) * 100, 4),
        sharpe_ratio=round(metrics.get("sharpe_ratio") or 0, 4),
        sortino_ratio=round(metrics.get("sortino_ratio") or 0, 4),
        max_drawdown_pct=round((metrics.get("max_drawdown") or 0) * 100, 4),
        volatility_pct=round((metrics.get("volatility") or 0) * 100, 4),
        win_rate=round(metrics.get("win_rate") or 0, 4),
        trade_count=len(all_trades),
        executed_trade_count=executed_count,
        simulation_start=sim_start,
        simulation_end=sim_end,
        portfolio_history=history,
        benchmark_return_pct=round(bench_ret * 100, 4) if bench_ret is not None else None,
        excess_return_pct=(
            round(tot_ret_pct - bench_ret * 100, 4) if bench_ret is not None else None
        ),
    )
