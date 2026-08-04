"""
QuiverQuant API Client
======================
Fetches congressional STOCK Act trade disclosures from the QuiverQuant API.

Free API key at https://quiverquant.com

Endpoints used:
  GET /beta/live/congresstrading       — recent disclosures across all members
  GET /beta/historical/congresstrading/{ticker} — all disclosures for one ticker
"""
from __future__ import annotations

import logging
import time
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

_BASE = "https://api.quiverquant.com"

# ── In-process cache (15 min TTL) ─────────────────────────────────────────────
_cache: dict[str, tuple[float, list[dict]]] = {}
_CACHE_TTL = 900  # seconds


def _cached(key: str) -> Optional[list[dict]]:
    entry = _cache.get(key)
    if entry and time.time() - entry[0] < _CACHE_TTL:
        return entry[1]
    return None


def _store(key: str, data: list[dict]) -> None:
    _cache[key] = (time.time(), data)


# ── Field normalisation ────────────────────────────────────────────────────────

def _parse_amount(amount_str: Optional[str]) -> Optional[float]:
    """
    Parse QuiverQuant amount ranges like '$1,001 - $15,000' → midpoint float.
    Returns None when unparseable.
    """
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


def _normalise_congress(row: dict) -> dict:
    """Map QuiverQuant congress field names to our internal schema."""
    tx_raw = (row.get("Transaction") or row.get("transaction_type") or "buy").lower()
    tx_type = "sell" if "sale" in tx_raw or "sell" in tx_raw else "buy"

    return {
        "trader_name":       row.get("Representative") or row.get("Senator") or row.get("name") or "Unknown",
        "ticker":            (row.get("Ticker") or row.get("ticker") or "").upper(),
        "transaction_type":  tx_type,
        "trade_date":        row.get("TransactionDate") or row.get("trade_date") or "",
        "disclosure_date":   row.get("ReportDate") or row.get("disclosure_date") or "",
        "amount_str":        row.get("Amount") or row.get("amount") or "",
        "amount_est":        _parse_amount(row.get("Amount") or row.get("amount")),
        "asset_type":        row.get("AssetType") or row.get("asset_type") or "Stock",
        "description":       row.get("AssetDescription") or row.get("description") or "",
        "chamber":           row.get("Chamber") or ("Senate" if row.get("Senator") else "House"),
    }


# ── Public functions ───────────────────────────────────────────────────────────

def fetch_recent_congress(api_key: str, limit: int = 50) -> list[dict]:
    """
    Returns up to `limit` recent congressional disclosures, normalised.
    Returns [] if no API key or request fails.
    """
    if not api_key:
        return []

    cache_key = f"recent:{limit}"
    cached = _cached(cache_key)
    if cached is not None:
        return cached

    try:
        r = httpx.get(
            f"{_BASE}/beta/live/congresstrading",
            headers={"Authorization": f"Token {api_key}"},
            params={"limit": limit},
            timeout=15,
        )
        r.raise_for_status()
        raw = r.json()
        data = [_normalise_congress(row) for row in (raw if isinstance(raw, list) else raw.get("data", []))]
        _store(cache_key, data)
        logger.info("QuiverQuant: fetched %d congress disclosures", len(data))
        return data
    except Exception as exc:
        logger.warning("QuiverQuant fetch_recent_congress failed: %s", exc)
        return []


def fetch_congress_for_ticker(api_key: str, ticker: str) -> list[dict]:
    """
    Returns all historical disclosures for a specific ticker.
    Returns [] if no API key or request fails.
    """
    if not api_key:
        return []

    cache_key = f"ticker:{ticker}"
    cached = _cached(cache_key)
    if cached is not None:
        return cached

    try:
        r = httpx.get(
            f"{_BASE}/beta/historical/congresstrading/{ticker}",
            headers={"Authorization": f"Token {api_key}"},
            timeout=15,
        )
        r.raise_for_status()
        raw = r.json()
        data = [_normalise_congress(row) for row in (raw if isinstance(raw, list) else raw.get("data", []))]
        _store(cache_key, data)
        logger.info("QuiverQuant: fetched %d disclosures for %s", len(data), ticker)
        return data
    except Exception as exc:
        logger.warning("QuiverQuant fetch_congress_for_ticker(%s) failed: %s", ticker, exc)
        return []
