"""
Financial Modeling Prep (FMP) Client
=====================================
Fetches real congressional trading disclosures from the FMP API.

Free API key at https://financialmodelingprep.com (250 req/day)

Endpoints used:
  GET /api/v4/senate-trading-rss-feed   — recent Senate disclosures
  GET /api/v4/house-disclosure-rss-feed — recent House disclosures
  GET /api/v4/senate-trading            — Senate trades for a ticker
  GET /api/v4/house-disclosure          — House trades for a ticker
"""
from __future__ import annotations

import logging
import time
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

_BASE = "https://financialmodelingprep.com"
_CACHE_TTL = 900  # 15 minutes
_cache: dict[str, tuple[float, list[dict]]] = {}


def _cached(key: str) -> Optional[list[dict]]:
    entry = _cache.get(key)
    if entry and time.time() - entry[0] < _CACHE_TTL:
        return entry[1]
    return None


def _store(key: str, data: list[dict]) -> None:
    _cache[key] = (time.time(), data)


def _parse_amount(amount_str: Optional[str]) -> Optional[float]:
    """Parse '$1,001 - $15,000' → midpoint float."""
    if not amount_str:
        return None
    try:
        clean = amount_str.replace("$", "").replace(",", "").strip()
        if " - " in clean:
            lo, hi = clean.split(" - ", 1)
            return (float(lo.strip()) + float(hi.strip())) / 2
        return float(clean)
    except Exception:
        return None


def _tx_type(raw: Optional[str]) -> str:
    if not raw:
        return "buy"
    r = raw.lower()
    if "sale" in r or "sell" in r:
        return "sell"
    return "buy"


def _normalise_senate(row: dict) -> dict:
    return {
        "trader_name":      f"{row.get('firstName', '')} {row.get('lastName', '')}".strip(),
        "ticker":           (row.get("ticker") or "").upper(),
        "transaction_type": _tx_type(row.get("type")),
        "trade_date":       row.get("transactionDate") or row.get("dateRecieved") or "",
        "disclosure_date":  row.get("dateRecieved") or "",
        "amount_str":       row.get("amount") or "",
        "amount_est":       _parse_amount(row.get("amount")),
        "asset_type":       "Stock",
        "description":      row.get("assetDescription") or "",
        "chamber":          "Senate",
    }


def _normalise_house(row: dict) -> dict:
    return {
        "trader_name":      row.get("representative") or row.get("name") or "Unknown",
        "ticker":           (row.get("ticker") or "").upper(),
        "transaction_type": _tx_type(row.get("type")),
        "trade_date":       row.get("transaction_date") or row.get("transactionDate") or "",
        "disclosure_date":  row.get("disclosure_date") or row.get("dateRecieved") or "",
        "amount_str":       row.get("amount") or "",
        "amount_est":       _parse_amount(row.get("amount")),
        "asset_type":       "Stock",
        "description":      row.get("asset_description") or row.get("assetDescription") or "",
        "chamber":          "House",
    }


def _get(api_key: str, path: str, params: dict = {}) -> list[dict]:
    try:
        r = httpx.get(
            f"{_BASE}{path}",
            params={"apikey": api_key, **params},
            timeout=15,
        )
        r.raise_for_status()
        data = r.json()
        return data if isinstance(data, list) else []
    except Exception as exc:
        logger.warning("FMP request %s failed: %s", path, exc)
        return []


def fetch_recent(api_key: str, limit: int = 50) -> list[dict]:
    """Recent disclosures from both Senate and House, combined."""
    if not api_key:
        return []

    cache_key = f"recent:{limit}"
    cached = _cached(cache_key)
    if cached is not None:
        return cached

    per_chamber = max(limit // 2, 20)

    senate_raw = _get(api_key, "/api/v4/senate-trading-rss-feed", {"page": 0})
    house_raw  = _get(api_key, "/api/v4/house-disclosure-rss-feed", {"page": 0})

    senate = [_normalise_senate(r) for r in senate_raw[:per_chamber] if r.get("ticker")]
    house  = [_normalise_house(r)  for r in house_raw[:per_chamber]  if r.get("ticker")]

    combined = senate + house
    # sort by disclosure date descending
    combined.sort(key=lambda x: x.get("disclosure_date") or "", reverse=True)
    data = combined[:limit]

    _store(cache_key, data)
    logger.info("FMP: fetched %d disclosures (%d senate, %d house)", len(data), len(senate), len(house))
    return data


def fetch_for_ticker(api_key: str, ticker: str) -> list[dict]:
    """All disclosures for a specific ticker from both chambers."""
    if not api_key:
        return []

    cache_key = f"ticker:{ticker}"
    cached = _cached(cache_key)
    if cached is not None:
        return cached

    senate_raw = _get(api_key, "/api/v4/senate-trading", {"symbol": ticker})
    house_raw  = _get(api_key, "/api/v4/house-disclosure", {"symbol": ticker})

    senate = [_normalise_senate(r) for r in senate_raw]
    house  = [_normalise_house(r)  for r in house_raw]

    data = senate + house
    data.sort(key=lambda x: x.get("disclosure_date") or "", reverse=True)

    _store(cache_key, data)
    logger.info("FMP: fetched %d disclosures for %s", len(data), ticker)
    return data
