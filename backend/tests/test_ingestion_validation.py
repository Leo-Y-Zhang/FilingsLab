"""Accept valid records and reject single-field corruptions at ingestion."""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.ingestion import validator


TODAY = date(2024, 6, 1)


@pytest.fixture(autouse=True)
def fixed_today(monkeypatch):
    class FixedDate(date):
        @classmethod
        def today(cls):
            return TODAY

    monkeypatch.setattr(validator, "date", FixedDate)


def trade_record(**changes):
    record = {
        "trade_date": date(2020, 1, 1),
        "disclosure_date": date(2020, 1, 2),
        "value_estimate": Decimal("100.00"),
        "asset_symbol": "ACME",
    }
    return dict(record, **changes)


@pytest.mark.parametrize("changes", [
    {},
    {"trade_date": date(2000, 1, 1), "disclosure_date": date(2000, 1, 1)},
    {"trade_date": TODAY, "disclosure_date": TODAY},
    {"disclosure_date": date(2020, 1, 1) + timedelta(days=720)},
    {"value_estimate": Decimal("1.00")},
    {"value_estimate": Decimal("50000000.00")},
    {"value_estimate": None, "disclosure_date": None},
])
def test_valid_trade_including_exact_boundaries(changes):
    assert validator.validate_normalised_record(trade_record(**changes)) == (True, None)


@pytest.mark.parametrize("field,value,reason", [
    ("trade_date", None, "missing trade_date"),
    ("trade_date", date(1999, 12, 31), "predates MIN_DATE"),
    ("trade_date", TODAY + timedelta(days=1), "in the future"),
    ("disclosure_date", date(2019, 12, 31), "precedes trade_date"),
    ("disclosure_date", date(2020, 1, 1) + timedelta(days=721), "exceeds maximum"),
    ("value_estimate", Decimal("0.99"), "below minimum"),
    ("value_estimate", Decimal("50000000.01"), "exceeds maximum"),
    ("asset_symbol", "", "invalid asset_symbol"),
    ("asset_symbol", None, "invalid asset_symbol"),
])
def test_trade_rejects_one_corrupted_field(field, value, reason):
    valid, message = validator.validate_normalised_record(trade_record(**{field: value}))
    assert valid is False
    assert reason in message


@pytest.mark.parametrize("field,reason", [
    ("trade_date", "missing trade_date"),
    ("asset_symbol", "invalid asset_symbol"),
])
def test_trade_rejects_removed_required_field(field, reason):
    record = trade_record()
    del record[field]
    assert validator.validate_normalised_record(record) == (False, reason)


@pytest.mark.parametrize("closing", [Decimal("0.01"), "125.50", 10])
def test_valid_price_is_accepted(closing):
    record = {"asset_symbol": "ACME", "date": TODAY, "closing_price": closing}
    assert validator.validate_price_record(record) == (True, None)


@pytest.mark.parametrize("changes,reason", [
    ({"asset_symbol": ""}, "missing asset_symbol"),
    ({"date": None}, "missing date"),
    ({"closing_price": None}, "invalid closing_price"),
    ({"closing_price": 0}, "invalid closing_price"),
    ({"closing_price": -0.01}, "invalid closing_price"),
])
def test_price_rejects_one_corrupted_field(changes, reason):
    record = dict(asset_symbol="ACME", date=TODAY, closing_price=100)
    valid, message = validator.validate_price_record(dict(record, **changes))
    assert valid is False
    assert reason in message


@pytest.mark.parametrize("field", ["asset_symbol", "date", "closing_price"])
def test_price_rejects_removed_required_field(field):
    record = dict(asset_symbol="ACME", date=TODAY, closing_price=100)
    del record[field]
    assert validator.validate_price_record(record)[0] is False
