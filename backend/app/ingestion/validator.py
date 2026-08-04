"""
Data Validator
==============
Business-rule validation applied after normalisation.
Returns a (is_valid, reason) tuple for each record.
"""

from datetime import date
from typing import Optional

MIN_DATE = date(2000, 1, 1)
MAX_FUTURE_DAYS = 30
MIN_VALUE = 1.0
MAX_VALUE = 50_000_000.0
MAX_DISCLOSURE_DELAY_DAYS = 720


def validate_normalised_record(record: dict) -> tuple[bool, Optional[str]]:
    trade_date: Optional[date] = record.get("trade_date")
    disclosure_date: Optional[date] = record.get("disclosure_date")
    value_estimate = record.get("value_estimate")
    symbol: Optional[str] = record.get("asset_symbol")

    if not trade_date:
        return False, "missing trade_date"
    if trade_date < MIN_DATE:
        return False, f"trade_date {trade_date} predates MIN_DATE {MIN_DATE}"
    if trade_date > date.today():
        return False, f"trade_date {trade_date} is in the future"
    if disclosure_date and disclosure_date < trade_date:
        return False, "disclosure_date precedes trade_date"
    if disclosure_date:
        delay = (disclosure_date - trade_date).days
        if delay > MAX_DISCLOSURE_DELAY_DAYS:
            return False, f"disclosure delay {delay} days exceeds maximum {MAX_DISCLOSURE_DELAY_DAYS}"
    if value_estimate is not None:
        val = float(value_estimate)
        if val < MIN_VALUE:
            return False, f"value_estimate {val} below minimum {MIN_VALUE}"
        if val > MAX_VALUE:
            return False, f"value_estimate {val} exceeds maximum {MAX_VALUE}"
    if not symbol or len(symbol) < 1:
        return False, "invalid asset_symbol"

    return True, None


def validate_price_record(record: dict) -> tuple[bool, Optional[str]]:
    symbol = record.get("asset_symbol")
    price_date = record.get("date")
    closing = record.get("closing_price")

    if not symbol:
        return False, "missing asset_symbol"
    if not price_date:
        return False, "missing date"
    if closing is None or float(closing) <= 0:
        return False, f"invalid closing_price {closing}"

    return True, None
