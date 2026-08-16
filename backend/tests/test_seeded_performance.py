"""
Seeded performance-metric regression tests
==========================================
Both seeders wrote their PerformanceMetric row from

    compute_all(portfolio_values, [], period_days)

with an empty per-trade list, so every stored row carried win_rate = 0.0 and
trade_count = 0 no matter what the trader did. Those two columns are served by
/api/traders/{id} and /api/rankings, and the composite ranking score weights
win_rate at 0.15 — a term that cannot vary when every trader scores zero.

The fixture below is a single trader who buys once and later sells at a higher
price, so the simulation has one closed trade and it is a winner.
"""
from datetime import date, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.models.performance import PerformanceMetric
from app.models.price import Price
from app.models.trade import Trade
from app.models.trader import Trader

START = date(2023, 1, 2)
END = date(2023, 12, 29)


@pytest.fixture()
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()

    day = START
    step = 0
    while day <= END:
        session.add(Price(asset_symbol="ACME", date=day, closing_price=100.0 + step * 0.05))
        session.add(Price(asset_symbol="SPY", date=day, closing_price=400.0))
        day += timedelta(days=1)
        step += 1

    trader = Trader(name="Fixture Trader", category="politician")
    session.add(trader)
    session.flush()

    buy_disclosed = START + timedelta(days=10)
    sell_disclosed = START + timedelta(days=200)
    for disclosed, kind in ((buy_disclosed, "buy"), (sell_disclosed, "sell")):
        session.add(Trade(
            trader_id=trader.id,
            asset_symbol="ACME",
            transaction_type=kind,
            trade_date=disclosed - timedelta(days=20),
            disclosure_date=disclosed,
            value_range_low=10_000,
            value_range_high=20_000,
            value_estimate=15_000,
        ))
    session.commit()

    yield session
    session.close()


def _metric(session, trader_id: int) -> PerformanceMetric:
    return (
        session.query(PerformanceMetric)
        .filter(PerformanceMetric.trader_id == trader_id)
        .first()
    )


def test_synthetic_seeder_records_trade_activity(db):
    from app.core.seed_data import _compute_performance

    trader = db.query(Trader).first()
    _compute_performance(db, trader)
    db.commit()

    metric = _metric(db, trader.id)
    assert metric is not None
    assert metric.trade_count == 2          # one buy, one sell, both executed
    assert float(metric.win_rate) > 0.0     # the sell closed at a profit


def test_real_seeder_records_trade_activity(db):
    from app.core.real_seed import _compute_performance

    trader = db.query(Trader).first()
    _compute_performance(db, trader)
    db.commit()

    metric = _metric(db, trader.id)
    assert metric is not None
    assert metric.trade_count == 2
    assert float(metric.win_rate) > 0.0
