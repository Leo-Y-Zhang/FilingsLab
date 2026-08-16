"""
Real Data Seeder
================
Replaces synthetic GBM data with real SEC EDGAR Form 4 insider trades
and real yfinance OHLCV price history.

Flow:
  1. Fetch ~120 recent Form 4 filings from EDGAR (last 60 days)
  2. Filter for buys >= $50k with a valid insider CIK
  3. Pick the top 12 insiders by total purchase volume
  4. Fetch their 2-year filing history via EDGAR Submissions API
  5. Pull 2-year OHLCV from yfinance for all involved tickers + SPY
  6. Persist prices → Price table
  7. Create Trader + Trade rows
  8. Compute PerformanceMetric for each trader
"""
from __future__ import annotations

import logging
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta
from decimal import Decimal
from typing import Optional

import httpx
import yfinance as yf

from sqlalchemy.orm import Session

from app.models.trader import Trader
from app.models.trade import Trade
from app.models.performance import PerformanceMetric
from app.ingestion.pipeline import ingest_prices
from app.services import edgar

logger = logging.getLogger(__name__)

_SUBMISSIONS = "https://data.sec.gov/submissions/CIK{}.json"
_HEADERS = {"User-Agent": "FilingsLab research@filingslab.local"}

HISTORY_YEARS = 2
MIN_BUY_USD = 50_000
TOP_N_INSIDERS = 12


# ── EDGAR Submissions history ──────────────────────────────────────────────────

def _fetch_submissions(cik: str) -> Optional[dict]:
    padded = cik.zfill(10)
    url = _SUBMISSIONS.format(padded)
    try:
        r = httpx.get(url, headers=_HEADERS, timeout=12)
        if r.status_code == 200:
            return r.json()
    except Exception as exc:
        logger.debug("Submissions fetch failed for CIK %s: %s", cik, exc)
    return None


def _history_for_cik(cik: str) -> list[dict]:
    """
    Returns Form 4 P/S transactions for an insider from EDGAR Submissions API.
    Covers the most recent filings up to HISTORY_YEARS back.
    """
    data = _fetch_submissions(cik)
    if not data:
        return []

    filings = data.get("filings", {}).get("recent", {})
    forms       = filings.get("form", [])
    dates       = filings.get("filingDate", [])
    accs        = filings.get("accessionNumber", [])
    docs        = filings.get("primaryDocument", [])

    cutoff = (date.today() - timedelta(days=HISTORY_YEARS * 365)).isoformat()

    form4_items = []
    for form, fdate, adsh, doc in zip(forms, dates, accs, docs):
        if form != "4":
            continue
        if fdate < cutoff:
            break   # filings are reverse-chronological
        form4_items.append((fdate, adsh, doc, cik))

    results = []
    for fdate, adsh, doc, cik_val in form4_items:
        xml = edgar._fetch_xml(adsh, [cik_val], doc)
        if not xml:
            continue
        txs = edgar._parse_xml(xml, fdate)
        results.extend(txs)
        time.sleep(0.12)   # stay well under 10 req/s

    return results


# ── Price fetching ─────────────────────────────────────────────────────────────

def _fetch_prices_yf(tickers: list[str], years: int = HISTORY_YEARS) -> list[dict]:
    period = f"{years}y"
    records: list[dict] = []
    for ticker in tickers:
        try:
            # Ticker.history always returns single-level columns (safe across yfinance versions)
            df = yf.Ticker(ticker).history(period=period, auto_adjust=True)
            if df.empty:
                logger.warning("yfinance: no data for %s", ticker)
                continue
            for idx, row in df.iterrows():
                dt = idx.date() if hasattr(idx, "date") else idx
                vol = row.get("Volume", 0)
                try:
                    vol_int = int(vol)
                except (TypeError, ValueError):
                    vol_int = 0
                records.append({
                    "asset_symbol":  ticker,
                    "date":          dt,
                    "closing_price": round(float(row["Close"]), 4),
                    "open":          round(float(row["Open"]),  4),
                    "high":          round(float(row["High"]),  4),
                    "low":           round(float(row["Low"]),   4),
                    "volume":        vol_int,
                })
            logger.debug("yfinance: %d rows for %s", len(df), ticker)
        except Exception as exc:
            logger.warning("yfinance failed for %s: %s", ticker, exc)
    return records


# ── Performance computation ────────────────────────────────────────────────────

def _compute_performance(db: Session, trader: Trader) -> None:
    from app.simulation.config import EngineConfig
    from app.simulation.engine import run as sim_run
    from app.analytics.performance import compute_all

    cfg = EngineConfig(
        trader_id=trader.id,
        initial_capital=100_000.0,
        delay_days=1,
        allocation_strategy="proportional",
        transaction_cost=0.001,
        slippage=0.0005,
        value_estimation_method="midpoint",
    )

    try:
        result = sim_run(db, cfg)
    except Exception as exc:
        logger.warning("Performance compute failed for trader %d: %s", trader.id, exc)
        return

    vals = [p.portfolio_value for p in result.portfolio_history]
    period_days = max((result.simulation_end - result.simulation_start).days, 1)
    metrics = compute_all(vals, [], period_days)
    # compute_all only sees the portfolio value series, not the individual
    # fills, so on its own it can only store win_rate 0.0 and trade_count 0.
    # The engine counted both during the run — keep its numbers.
    metrics["win_rate"] = result.win_rate
    metrics["trade_count"] = result.executed_trade_count

    existing = (
        db.query(PerformanceMetric)
        .filter(PerformanceMetric.trader_id == trader.id)
        .first()
    )
    bm = (
        Decimal(str(result.benchmark_return_pct / 100))
        if result.benchmark_return_pct is not None
        else None
    )
    if existing:
        for k, v in metrics.items():
            setattr(existing, k, v)
        existing.benchmark_return = bm
        existing.period_start    = result.simulation_start
        existing.period_end      = result.simulation_end
        existing.delay_days_used = 1
    else:
        db.add(PerformanceMetric(
            trader_id=trader.id,
            period_start=result.simulation_start,
            period_end=result.simulation_end,
            delay_days_used=1,
            benchmark_return=bm,
            **metrics,
        ))


# ── Role helpers ───────────────────────────────────────────────────────────────

def _category_from_role(role: str) -> str:
    role_lower = role.lower()
    if any(w in role_lower for w in ("ceo", "cfo", "coo", "cto", "president",
                                      "officer", "director", "vp", "vice")):
        return "executive"
    if "10%" in role_lower or "owner" in role_lower:
        return "insider"
    return "insider"


def _value_label(amount: float) -> str:
    if amount <= 15_000:
        return "$1,001 - $15,000"
    if amount <= 50_000:
        return "$15,001 - $50,000"
    if amount <= 100_000:
        return "$50,001 - $100,000"
    if amount <= 250_000:
        return "$100,001 - $250,000"
    return "$250,001 - $500,000"


# ── Public entry point ─────────────────────────────────────────────────────────

def seed_real_data(db: Session) -> bool:
    """
    Seeds the database with real EDGAR Form 4 insider trading data.
    Returns True on success, False if EDGAR is unreachable or no valid
    insiders were found (caller should fall back to synthetic seeding).
    """
    logger.info("Real seeder: fetching recent EDGAR Form 4 filings...")

    # Step 1 — collect recent hits (keep low to limit archive fetch count)
    try:
        hits = edgar._search(days_back=60, limit=40)
    except Exception as exc:
        logger.warning("Real seeder: EDGAR search failed (%s) — falling back", exc)
        return False

    if not hits:
        logger.warning("Real seeder: no EDGAR hits returned — falling back")
        return False

    # Step 2 — parse transactions; bail early if Archives is rate-limiting us
    from app.services import edgar as _edgar_mod
    _edgar_mod._archives_429_count = 0   # reset counter

    all_txs: list[dict] = []
    for hit in hits:
        try:
            all_txs.extend(edgar._process_hit(hit))
        except Exception:
            pass
        # If Archives is consistently refusing us, give up — fall through to synthetic
        if _edgar_mod._archives_429_count >= 3:
            logger.warning(
                "Real seeder: EDGAR Archives returning 429 repeatedly — "
                "SEC is rate-limiting this IP. Falling back to synthetic + real prices."
            )
            return False
        time.sleep(0.5)

    qualified = [
        t for t in all_txs
        if t.get("transaction_type") == "buy"
        and t.get("amount_est", 0) >= MIN_BUY_USD
        and t.get("insider_cik", "").strip()
    ]

    if not qualified:
        logger.warning("Real seeder: no qualifying buy transactions — falling back")
        return False

    # Step 3 — rank insiders by total purchase volume, pick top N
    vol_by_cik: dict[str, float] = defaultdict(float)
    meta_by_cik: dict[str, dict] = {}
    for tx in qualified:
        cik = tx["insider_cik"]
        vol_by_cik[cik] += tx["amount_est"]
        if cik not in meta_by_cik:
            meta_by_cik[cik] = {
                "name":    tx["trader_name"],
                "role":    tx["trader_role"],
                "company": tx["company"],
            }

    top_ciks = sorted(vol_by_cik, key=vol_by_cik.__getitem__, reverse=True)[:TOP_N_INSIDERS]
    logger.info("Real seeder: selected %d top insiders", len(top_ciks))

    # Step 4 — fetch 2-year history for each insider's CIK
    all_trades_by_cik: dict[str, list[dict]] = {}
    tickers_seen: set[str] = set()

    for cik in top_ciks:
        logger.info("Real seeder: fetching history for CIK %s (%s)...",
                    cik, meta_by_cik[cik]["name"])
        txs = _history_for_cik(cik)
        # Supplement with what we already fetched from the recent scan
        recent = [t for t in all_txs if t.get("insider_cik") == cik]
        combined = {
            (t["trader_name"], t["ticker"], t["trade_date"], t["transaction_type"]): t
            for t in txs + recent
        }
        all_trades_by_cik[cik] = list(combined.values())
        for tx in all_trades_by_cik[cik]:
            tickers_seen.add(tx["ticker"])

    if not tickers_seen:
        logger.warning("Real seeder: no tickers found — falling back")
        return False

    tickers_list = sorted(tickers_seen) + (["SPY"] if "SPY" not in tickers_seen else [])
    logger.info("Real seeder: downloading prices for %d tickers via yfinance...",
                len(tickers_list))

    # Step 5 — download real OHLCV prices
    price_records = _fetch_prices_yf(tickers_list)
    if not price_records:
        logger.warning("Real seeder: yfinance returned nothing — falling back")
        return False

    # Step 6 — persist prices
    ingest_prices(db, price_records)
    logger.info("Real seeder: inserted %d price records", len(price_records))

    # Step 7 — create Trader + Trade rows
    traders_created: list[Trader] = []

    for cik in top_ciks:
        meta  = meta_by_cik[cik]
        txs   = all_trades_by_cik.get(cik, [])
        ps_txs = [t for t in txs if t["transaction_type"] in ("buy", "sell")]

        if not ps_txs:
            continue

        category = _category_from_role(meta["role"])
        bio = f"{meta['role']} at {meta['company']}. SEC CIK: {cik}."

        trader = Trader(
            name=meta["name"],
            category=category,
            party=None,
            state=None,
            bio=bio,
        )
        db.add(trader)
        db.flush()

        for tx in ps_txs:
            amt = tx.get("amount_est", 0.0)
            label = _value_label(amt)
            # Use ± 10% as range bounds
            lo = round(amt * 0.90, 2)
            hi = round(amt * 1.10, 2)
            db.add(Trade(
                trader_id=trader.id,
                asset_symbol=tx["ticker"],
                asset_name=tx.get("company", tx["ticker"]),
                transaction_type=tx["transaction_type"],
                trade_date=date.fromisoformat(tx["trade_date"]),
                disclosure_date=date.fromisoformat(tx["disclosure_date"]),
                value_range_label=label,
                value_range_low=Decimal(str(lo)),
                value_range_high=Decimal(str(hi)),
                value_estimate=Decimal(str(round(amt, 2))),
            ))

        db.flush()
        traders_created.append(trader)
        logger.info("Real seeder: created trader '%s' with %d trades",
                    trader.name, len(ps_txs))

    if not traders_created:
        logger.warning("Real seeder: no traders created — falling back")
        db.rollback()
        return False

    # Require at least 5 traders with at least 5 trades each for a usable dataset
    MIN_TRADERS = 5
    MIN_TRADES  = 5
    qualified_traders = [
        t for t in traders_created
        if db.query(Trade).filter(Trade.trader_id == t.id).count() >= MIN_TRADES
    ]
    if len(qualified_traders) < MIN_TRADERS:
        logger.warning(
            "Real seeder: only %d traders with >= %d trades (need %d) — "
            "not enough data for meaningful backtesting. Falling back.",
            len(qualified_traders), MIN_TRADES, MIN_TRADERS,
        )
        db.rollback()
        return False

    db.commit()

    # Step 8 — compute performance metrics
    for trader in traders_created:
        _compute_performance(db, trader)
    db.commit()

    logger.info(
        "Real seeder complete: %d traders, %d price records.",
        len(traders_created), len(price_records),
    )
    return True
