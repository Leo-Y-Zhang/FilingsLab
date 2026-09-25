"""
Simulation engine contract tests
================================
The engine is the part of FilingsLab every published number comes from:
/api/simulate, Monte Carlo, comparison, alpha decay, both hypothesis tests, the
three experiments and the seeded rankings all call ``engine.run``. Until now it
had no test of its own, only indirect coverage through the seeders and the
hypothesis tests.

Each test here was watched failing against the code it fixes.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.models.performance import PerformanceMetric  # noqa: F401 - mapper registration
from app.models.price import Price
from app.models.trade import Trade
from app.models.trader import Trader
from app.schemas.simulation import MonteCarloConfig
from app.simulation import engine
from app.simulation.config import EngineConfig
from app.simulation.monte_carlo import run_monte_carlo

START = date(2023, 1, 2)    # a Monday
END = date(2023, 6, 30)


def _session():
    eng = create_engine("sqlite://")
    Base.metadata.create_all(eng)
    return sessionmaker(bind=eng)()


def _trade(trader_id: int, disclosed: date, kind: str = "buy", symbol: str = "ACME",
           value: float = 15_000) -> Trade:
    return Trade(
        trader_id=trader_id,
        asset_symbol=symbol,
        transaction_type=kind,
        trade_date=disclosed - timedelta(days=20),
        disclosure_date=disclosed,
        value_range_low=value * 0.5,
        value_range_high=value * 1.5,
        value_estimate=value,
    )


@pytest.fixture()
def db():
    """One trader, a price on every calendar day, ACME rising and SPY rising slower."""
    session = _session()
    day, step = START, 0
    while day <= END:
        session.add(Price(asset_symbol="ACME", date=day, closing_price=100.0 + step * 0.05))
        session.add(Price(asset_symbol="SPY", date=day, closing_price=400.0 + step * 0.01))
        day += timedelta(days=1)
        step += 1
    trader = Trader(name="Fixture Trader", category="politician")
    session.add(trader)
    session.flush()
    session.add(_trade(trader.id, START + timedelta(days=10), "buy"))
    session.add(_trade(trader.id, START + timedelta(days=100), "sell"))
    session.commit()
    yield session
    session.close()


def _trader_id(session) -> int:
    return session.query(Trader).first().id


# ── The simulated window is bounded by the price data ─────────────────────────

def test_a_window_far_beyond_the_price_data_costs_only_the_price_data(db, monkeypatch):
    """
    start_date and end_date arrive unvalidated from three open POST routes, and
    the engine walked every calendar day between them with a query per day. A
    100-year window measured 61 s on one worker thread against the synthetic
    seed; 1900-9999 is about 80 minutes, per request, per thread.
    """
    budget = (END - START).days + 1
    calls = 0
    real = engine._prices_on_date

    def counted(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls > budget:
            raise AssertionError(
                f"more than {budget} price lookups for {budget} days of price data"
            )
        return real(*args, **kwargs)

    monkeypatch.setattr(engine, "_prices_on_date", counted)
    result = engine.run(db, EngineConfig(
        trader_id=_trader_id(db), start_date=date(1900, 1, 1), end_date=date(9999, 12, 1),
    ))

    assert (result.simulation_start, result.simulation_end) == (START, END)
    assert result.benchmark_return_pct is not None


def test_a_window_with_no_price_data_is_refused_rather_than_simulated(db):
    with pytest.raises(ValueError, match="No price data in the requested window"):
        engine.run(db, EngineConfig(
            trader_id=_trader_id(db), start_date=date(1990, 1, 1), end_date=date(1995, 1, 1),
        ))


def test_monte_carlo_benchmarks_the_window_it_actually_simulated(db):
    """
    Monte Carlo priced its benchmark over the requested dates rather than the
    simulated ones, so a start a month before the data had no SPY price to
    look up and the result carried no benchmark at all.
    """
    start = START - timedelta(days=30)
    mc = run_monte_carlo(db, MonteCarloConfig(
        trader_id=_trader_id(db), n_runs=10, random_seed=7, start_date=start,
    ))
    single = engine.run(db, EngineConfig(trader_id=_trader_id(db), start_date=start))

    assert mc.benchmark_return_pct is not None
    assert mc.benchmark_return_pct == pytest.approx(single.benchmark_return_pct)
