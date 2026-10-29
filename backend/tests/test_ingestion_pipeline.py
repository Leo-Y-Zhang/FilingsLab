"""Validate before persisting, deduplicate, and report actual database changes."""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.database import Base
from app.ingestion.pipeline import ingest_prices, ingest_trades
from app.models.performance import PerformanceMetric  # noqa: F401 - mapper registration
from app.models.price import Price
from app.models.trade import Trade
from app.models.trader import Trader


@pytest.fixture()
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(Trader(id=1, name="Example Trader", category="insider"))
        session.commit()
        yield session
    engine.dispose()


def trade(**changes):
    return dict({
        "trader_id": 1, "asset_symbol": "ACME", "transaction_type": "buy",
        "trade_date": "2020-01-02", "disclosure_date": "2020-01-03",
        "value_range_label": "$1,001 - $15,000",
    }, **changes)


def test_trades_count_rejections_and_do_not_persist_invalid_records(db):
    truncated = trade()
    del truncated["trade_date"]
    records = [
        trade(), truncated, trade(value_range_label="$60,000,000 - $70,000,000"),
        trade(trade_date="1999-12-31"), trade(transaction_type="gift"),
        trade(trader_id="not an integer"),
    ]
    assert ingest_trades(db, records) == {"inserted": 1, "skipped": 0, "errors": 5}
    db.expire_all()
    row, = db.query(Trade).all()
    assert row.asset_symbol == "ACME"
    assert row.trade_date == date(2020, 1, 2)
    assert row.value_estimate == Decimal("8000.50")


def test_trade_duplicate_key_includes_symbol_date_direction_and_trader(db):
    db.add(Trader(id=2, name="Other Trader", category="insider"))
    db.commit()
    assert ingest_trades(db, [trade()]) == {"inserted": 1, "skipped": 0, "errors": 0}
    # The value is not part of the disclosure identity; a duplicate is not an update.
    assert ingest_trades(db, [trade(value_range_label="$15,001 - $50,000")]) == {
        "inserted": 0, "skipped": 1, "errors": 0,
    }
    variants = [
        trade(asset_symbol="BETA"), trade(trade_date="2020-01-01"),
        trade(transaction_type="sell"), trade(trader_id=2),
    ]
    assert ingest_trades(db, variants) == {"inserted": 4, "skipped": 0, "errors": 0}
    assert db.query(Trade).count() == 5
    assert db.query(Trade).order_by(Trade.id).first().value_estimate == Decimal("8000.50")


def test_prices_insert_update_and_count_only_valid_rows(db):
    raw = dict(asset_symbol=" acme ", date="2024-02-29", closing_price="100.1250",
               open="99.25", high="105", low="98", volume="1000")
    assert ingest_prices(db, [raw]) == {"inserted": 1, "updated": 0, "errors": 0}
    row, = db.query(Price).all()
    assert (row.asset_symbol, row.date) == ("ACME", date(2024, 2, 29))
    assert row.closing_price == Decimal("100.1250")
    assert (row.open_price, row.high_price, row.low_price, row.volume) == (
        Decimal("99.25"), Decimal("105"), Decimal("98"), Decimal("1000"),
    )
    assert ingest_prices(db, [dict(raw, asset_symbol="ACME", closing_price="120.5")]) == {
        "inserted": 0, "updated": 1, "errors": 0,
    }
    db.expire_all()
    row, = db.query(Price).all()
    assert row.closing_price == Decimal("120.5000")

    truncated = dict(raw)
    del truncated["closing_price"]
    invalid = [dict(raw, closing_price=0), dict(raw, closing_price=-1),
               dict(raw, date="2024-02"), dict(raw, asset_symbol=""), truncated]
    assert ingest_prices(db, invalid) == {"inserted": 0, "updated": 0, "errors": 5}
    db.expire_all()
    row, = db.query(Price).all()
    assert row.closing_price == Decimal("120.5000")


def test_empty_batches_have_zero_counts(db):
    assert ingest_trades(db, []) == {"inserted": 0, "skipped": 0, "errors": 0}
    assert ingest_prices(db, []) == {"inserted": 0, "updated": 0, "errors": 0}
    assert db.query(Trade).count() == db.query(Price).count() == 0
