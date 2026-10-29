"""Small, independent examples of the disclosure parsing contract."""

from datetime import date, datetime
from decimal import Decimal

import pytest

from app.ingestion.normalizer import (
    normalise_record,
    normalise_symbol,
    normalise_transaction_type,
    parse_date_flexible,
    parse_value_range,
)


@pytest.mark.parametrize("label,expected", [
    (" $1,001 - $15,000 ", (1001, 15000, 8000.5)),
    ("OVER $5,000,000", (5000001, 15000000, 10000000.5)),
    ("$20,000 – $10,000", (10000, 20000, 15000)),
    ("250 — 750", (250, 750, 500)),
    ("over $20,000", (20000, 60000, 40000)),
    ("", (None, None, None)),
    ("not disclosed", (None, None, None)),
])
def test_value_range_bounds_and_midpoint(label, expected):
    assert parse_value_range(label) == expected


@pytest.mark.parametrize("value", [
    date(2024, 2, 29), datetime(2024, 2, 29, 23, 59),
    " 2024-02-29 ", "02/29/2024", "29/02/2024", "20240229", "29-02-2024",
])
def test_date_formats_keep_the_calendar_day(value):
    result = parse_date_flexible(value)
    assert result == date(2024, 2, 29)
    assert type(result) is date


@pytest.mark.parametrize("value", [None, "", "2023-02-29", "2024-02", "garbage", 20240229])
def test_invalid_or_truncated_dates_are_rejected(value):
    assert parse_date_flexible(value) is None


@pytest.mark.parametrize("raw,expected", [
    (" BUY ", "buy"), ("purchase", "buy"), ("Acquisition", "buy"),
    (" Full Sale ", "sell"), ("disposition", "sell"), ("sold", "sell"),
    ("gift", None),
])
def test_transaction_direction(raw, expected):
    assert normalise_transaction_type(raw) == expected


@pytest.mark.parametrize("raw,expected", [
    (" brk.b ", "BRK.B"), ("a", "A"), ("abcdefghij", "ABCDEFGHIJ"),
    ("abcdefghijk", None), ("!!!", None), ("", None),
])
def test_symbol_normalization_and_length(raw, expected):
    assert normalise_symbol(raw) == expected


def raw_record(**changes):
    return dict({
        "trader_id": "7", "asset_symbol": " acme ", "asset_name": " Example ",
        "transaction_type": "Purchase", "trade_date": "2024-02-29",
        "disclosure_date": "2024-03-01", "value_range_label": "$1,001 - $15,000",
    }, **changes)


def test_complete_record_has_typed_values_and_exact_midpoint():
    assert normalise_record(raw_record()) == {
        "trader_id": 7, "asset_symbol": "ACME", "asset_name": "Example",
        "transaction_type": "buy", "trade_date": date(2024, 2, 29),
        "disclosure_date": date(2024, 3, 1), "value_range_label": "$1,001 - $15,000",
        "value_range_low": Decimal("1001"), "value_range_high": Decimal("15000"),
        "value_estimate": Decimal("8000.5"),
    }


@pytest.mark.parametrize("disclosed", [None, "invalid", "2024-02-28"])
def test_missing_or_earlier_disclosure_uses_trade_date(disclosed):
    record = normalise_record(raw_record(disclosure_date=disclosed))
    assert record["disclosure_date"] == date(2024, 2, 29)


@pytest.mark.parametrize("field", ["trader_id", "asset_symbol", "transaction_type", "trade_date"])
def test_removed_required_fields_are_rejected(field):
    raw = raw_record()
    del raw[field]
    assert normalise_record(raw) is None


@pytest.mark.parametrize("changes", [
    {"trade_date": "2024-02"}, {"transaction_type": "gift"},
    {"asset_symbol": "!!!"}, {"asset_symbol": "ABCDEFGHIJK"},
])
def test_corrupted_record_is_rejected(changes):
    assert normalise_record(raw_record(**changes)) is None


def test_zero_id_and_unknown_value_are_preserved():
    result = normalise_record(raw_record(trader_id=0, value_range_label="", asset_name=" "))
    assert result["trader_id"] == 0
    assert result["asset_name"] is None
    assert result["value_range_label"] is None
    assert result["value_range_low"] is None
    assert result["value_range_high"] is None
    assert result["value_estimate"] is None
