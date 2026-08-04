"""
Data Normalizer
===============
Converts raw disclosure records into a clean, typed, numeric form.
"""

import re
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional
import logging

logger = logging.getLogger(__name__)

_CANONICAL_RANGES: list[tuple[str, float, float]] = [
    ("$1 - $1,000",               1,         1_000),
    ("$1,001 - $15,000",          1_001,    15_000),
    ("$15,001 - $50,000",        15_001,    50_000),
    ("$50,001 - $100,000",       50_001,   100_000),
    ("$100,001 - $250,000",     100_001,   250_000),
    ("$250,001 - $500,000",     250_001,   500_000),
    ("$500,001 - $1,000,000",   500_001, 1_000_000),
    ("$1,000,001 - $5,000,000", 1_000_001, 5_000_000),
    ("over $5,000,000",         5_000_001, 15_000_000),
]

_RANGE_RE = re.compile(r"\$?([\d,]+)\s*[-–—]\s*\$?([\d,]+)", re.IGNORECASE)
_OVER_RE  = re.compile(r"over\s+\$?([\d,]+)", re.IGNORECASE)


def parse_value_range(label: str) -> tuple[Optional[float], Optional[float], Optional[float]]:
    """Parse a range label → (low, high, midpoint)."""
    if not label:
        return None, None, None

    clean = label.strip()

    for canon_label, lo, hi in _CANONICAL_RANGES:
        if clean.lower() == canon_label.lower():
            return lo, hi, (lo + hi) / 2

    m = _RANGE_RE.search(clean)
    if m:
        try:
            lo = float(m.group(1).replace(",", ""))
            hi = float(m.group(2).replace(",", ""))
            if lo > hi:
                lo, hi = hi, lo
            return lo, hi, (lo + hi) / 2
        except ValueError:
            pass

    m = _OVER_RE.search(clean)
    if m:
        try:
            lo = float(m.group(1).replace(",", ""))
            hi = lo * 3
            return lo, hi, (lo + hi) / 2
        except ValueError:
            pass

    return None, None, None


def parse_date_flexible(value: Any) -> Optional[date]:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str):
        for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y", "%Y%m%d", "%d-%m-%Y"):
            try:
                return datetime.strptime(value.strip(), fmt).date()
            except ValueError:
                continue
    return None


def normalise_transaction_type(raw: str) -> Optional[str]:
    raw_clean = raw.strip().lower()
    buy_synonyms  = {"buy", "purchase", "bought", "acquisition", "full purchase"}
    sell_synonyms = {"sell", "sale", "sold", "disposition", "full sale"}
    if raw_clean in buy_synonyms:
        return "buy"
    if raw_clean in sell_synonyms:
        return "sell"
    return None


def normalise_symbol(raw: str) -> Optional[str]:
    clean = re.sub(r"[^A-Za-z0-9.]", "", raw).upper()
    return clean if 1 <= len(clean) <= 10 else None


def normalise_record(raw: dict) -> Optional[dict]:
    """Convert a raw disclosure dict to normalised form for DB insertion."""
    required = ("trader_id", "asset_symbol", "transaction_type", "trade_date")
    for key in required:
        if not raw.get(key) and raw.get(key) != 0:
            return None

    trade_date = parse_date_flexible(raw["trade_date"])
    if not trade_date:
        return None

    disclosure_date = parse_date_flexible(raw.get("disclosure_date")) or trade_date
    if disclosure_date < trade_date:
        disclosure_date = trade_date

    txn = normalise_transaction_type(raw.get("transaction_type", ""))
    if not txn:
        return None

    symbol = normalise_symbol(raw.get("asset_symbol", ""))
    if not symbol:
        return None

    label = raw.get("value_range_label", "")
    lo, hi, mid = parse_value_range(label)

    return {
        "trader_id":          int(raw["trader_id"]),
        "asset_symbol":       symbol,
        "asset_name":         (raw.get("asset_name") or "").strip() or None,
        "transaction_type":   txn,
        "trade_date":         trade_date,
        "disclosure_date":    disclosure_date,
        "value_range_label":  label or None,
        "value_range_low":    Decimal(str(lo))  if lo  is not None else None,
        "value_range_high":   Decimal(str(hi))  if hi  is not None else None,
        "value_estimate":     Decimal(str(mid)) if mid is not None else None,
    }
