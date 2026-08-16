"""
Seed Data Generator
====================
Generates synthetic but realistic mock data for development and demonstration.

Price simulation uses Geometric Brownian Motion (GBM) with asset-specific
drift and volatility. All traders, names, and affiliations are entirely
fictional. Any resemblance to real persons is coincidental.

Data is for educational/research demonstration only.
"""

import random
import math
from datetime import date, timedelta
from decimal import Decimal
import logging

from sqlalchemy.orm import Session

from app.models.trader import Trader
from app.models.trade import Trade
from app.models.price import Price
from app.models.performance import PerformanceMetric
from app.ingestion.pipeline import ingest_prices

logger = logging.getLogger(__name__)

SEED = 42
random.seed(SEED)

DATA_START = date.today() - timedelta(days=4 * 365)
DATA_END   = date.today()

# ── 12 fictional traders ───────────────────────────────────────────────────────
TRADERS = [
    {"name": "Eleanor Ashworth",  "category": "politician", "party": "Progressive",  "state": "California",
     "bio": "Chair of the Banking Oversight Subcommittee. Extensive background in finance and technology policy."},
    {"name": "Thomas Hargrave",   "category": "politician", "party": "Conservative", "state": "Texas",
     "bio": "Senior member of the Energy and Natural Resources committee. Former oil-and-gas attorney."},
    {"name": "Priya Nair-Kapoor", "category": "politician", "party": "Progressive",  "state": "New York",
     "bio": "Technology and AI policy advocate on the Science, Space, and Commerce committees."},
    {"name": "Walter Fenwick",    "category": "politician", "party": "Conservative", "state": "Ohio",
     "bio": "Armed Services and Defence Appropriations committees member. 20-year military career."},
    {"name": "Isabelle Chartier", "category": "politician", "party": "Progressive",  "state": "Massachusetts",
     "bio": "Chair of the Health, Pharmaceutical, and Biotech Oversight Subcommittee."},
    {"name": "Cassandra Whitley", "category": "politician", "party": "Conservative", "state": "Florida",
     "bio": "Financial Services and Banking Regulation subcommittee member. Former mortgage banker."},
    {"name": "Victoria Morrow",   "category": "politician", "party": "Progressive",  "state": "Oregon",
     "bio": "Serves on the Health, Judiciary, and Veterans' Affairs committees. Healthcare reform focus."},
    {"name": "Leonard Harrington","category": "politician", "party": "Conservative", "state": "Georgia",
     "bio": "Agriculture, Trade, and Appropriations committees. Former agri-business executive."},
    {"name": "Raymond Goldblum",  "category": "executive",  "party": None, "state": "Delaware",
     "bio": "Retired CFO of a Fortune 100 financial conglomerate. Board member at several listed firms."},
    {"name": "Gregory Falcone",   "category": "executive",  "party": None, "state": "Washington",
     "bio": "Managing director at a private equity fund with technology and energy sector focus."},
    {"name": "Sunita Patel-Rao",  "category": "insider",    "party": None, "state": "New Jersey",
     "bio": "Senior VP at a major pharmaceutical distribution firm. Serves on three audit committees."},
    {"name": "Dmitri Volkov",     "category": "insider",    "party": None, "state": "Illinois",
     "bio": "Chief Strategy Officer at a semiconductor distribution company. Former sell-side analyst."},
]

# ── 16 assets (SPY is benchmark) ───────────────────────────────────────────────
ASSETS = [
    {"symbol": "AAPL",  "name": "Apple Inc.",                  "base": 130.0, "drift": 0.00035, "vol": 0.015},
    {"symbol": "MSFT",  "name": "Microsoft Corporation",       "base": 280.0, "drift": 0.00040, "vol": 0.013},
    {"symbol": "GOOGL", "name": "Alphabet Inc.",                "base": 125.0, "drift": 0.00030, "vol": 0.014},
    {"symbol": "AMZN",  "name": "Amazon.com Inc.",              "base": 100.0, "drift": 0.00025, "vol": 0.018},
    {"symbol": "NVDA",  "name": "NVIDIA Corporation",           "base": 150.0, "drift": 0.00090, "vol": 0.028},
    {"symbol": "JPM",   "name": "JPMorgan Chase & Co.",         "base": 135.0, "drift": 0.00020, "vol": 0.012},
    {"symbol": "PFE",   "name": "Pfizer Inc.",                  "base": 42.0,  "drift": -0.00008,"vol": 0.013},
    {"symbol": "XOM",   "name": "Exxon Mobil Corporation",      "base": 85.0,  "drift": 0.00015, "vol": 0.016},
    {"symbol": "LMT",   "name": "Lockheed Martin Corporation",  "base": 400.0, "drift": 0.00018, "vol": 0.011},
    {"symbol": "BA",    "name": "Boeing Company",               "base": 200.0, "drift": -0.00005,"vol": 0.022},
    {"symbol": "META",  "name": "Meta Platforms Inc.",          "base": 180.0, "drift": 0.00055, "vol": 0.021},
    {"symbol": "TSLA",  "name": "Tesla Inc.",                   "base": 220.0, "drift": 0.00030, "vol": 0.032},
    {"symbol": "AMD",   "name": "Advanced Micro Devices Inc.",  "base": 80.0,  "drift": 0.00060, "vol": 0.026},
    {"symbol": "UNH",   "name": "UnitedHealth Group Inc.",      "base": 380.0, "drift": 0.00025, "vol": 0.012},
    {"symbol": "MRK",   "name": "Merck & Co. Inc.",             "base": 75.0,  "drift": 0.00020, "vol": 0.011},
    {"symbol": "SPY",   "name": "SPDR S&P 500 ETF Trust",       "base": 380.0, "drift": 0.00030, "vol": 0.010},
]

VALUE_RANGES = [
    ("$1,001 - $15,000",      1_001,   15_000),
    ("$15,001 - $50,000",    15_001,   50_000),
    ("$50,001 - $100,000",   50_001,  100_000),
    ("$100,001 - $250,000", 100_001,  250_000),
    ("$250,001 - $500,000", 250_001,  500_000),
]

TRADER_ASSETS = {
    "Eleanor Ashworth":   ["JPM", "MSFT", "AAPL", "META", "GOOGL"],
    "Thomas Hargrave":    ["XOM", "LMT", "BA", "JPM", "MSFT"],
    "Priya Nair-Kapoor":  ["AAPL", "NVDA", "GOOGL", "TSLA", "META"],
    "Walter Fenwick":     ["LMT", "BA", "XOM", "JPM", "UNH"],
    "Isabelle Chartier":  ["PFE", "UNH", "MRK", "AMZN", "AAPL"],
    "Cassandra Whitley":  ["JPM", "AAPL", "MSFT", "XOM", "GOOGL"],
    "Victoria Morrow":    ["PFE", "MRK", "UNH", "AMZN", "MSFT"],
    "Leonard Harrington": ["XOM", "BA", "LMT", "AMZN", "JPM"],
    "Raymond Goldblum":   ["JPM", "MSFT", "AAPL", "AMZN", "META"],
    "Gregory Falcone":    ["NVDA", "AMD", "TSLA", "AAPL", "META"],
    "Sunita Patel-Rao":   ["PFE", "UNH", "MRK", "AMZN", "AAPL"],
    "Dmitri Volkov":      ["NVDA", "AMD", "MSFT", "TSLA", "GOOGL"],
}


def _fetch_real_prices(symbols: list[str]) -> list[dict]:
    """Download real 4-year OHLCV history from yfinance for each symbol."""
    try:
        import yfinance as yf
        records: list[dict] = []
        for sym in symbols:
            try:
                # Use Ticker.history — always returns single-level columns
                ticker_obj = yf.Ticker(sym)
                df = ticker_obj.history(period="4y", auto_adjust=True)
                if df.empty:
                    continue
                for idx, row in df.iterrows():
                    dt = idx.date() if hasattr(idx, "date") else idx
                    vol = row.get("Volume", 0)
                    try:
                        vol_int = int(vol)
                    except (TypeError, ValueError):
                        vol_int = 0
                    records.append({
                        "asset_symbol":  sym,
                        "date":          dt,
                        "closing_price": round(float(row["Close"]), 4),
                        "open":          round(float(row["Open"]),  4),
                        "high":          round(float(row["High"]),  4),
                        "low":           round(float(row["Low"]),   4),
                        "volume":        vol_int,
                    })
                logger.debug("yfinance: %d rows for %s", len(df), sym)
            except Exception as exc:
                logger.warning("yfinance failed for %s: %s", sym, exc)
        return records
    except ImportError:
        return []
    except Exception as exc:
        logger.warning("_fetch_real_prices failed: %s", exc)
        return []


def _gbm_prices(symbol, base, drift, vol, start, end):
    records = []
    price = base
    cur = start
    while cur <= end:
        if cur.weekday() < 5:
            shock = random.gauss(0, 1)
            price = price * math.exp(drift + vol * shock)
            price = max(price, 0.01)
            records.append({
                "asset_symbol": symbol,
                "date": cur,
                "closing_price": round(price, 4),
                "open":   round(price * random.uniform(0.99, 1.01), 4),
                "high":   round(price * random.uniform(1.00, 1.02), 4),
                "low":    round(price * random.uniform(0.98, 1.00), 4),
                "volume": random.randint(500_000, 30_000_000),
            })
        cur += timedelta(days=1)
    return records


def _gen_trades(trader_id, preferred_symbols, n_trades, start, end):
    records = []
    cur = start
    for _ in range(n_trades):
        gap = random.randint(5, 40)
        cur = cur + timedelta(days=gap)
        if cur > end:
            break

        symbol = random.choice(preferred_symbols)
        asset = next((a for a in ASSETS if a["symbol"] == symbol), None)

        txn = random.choices(["buy", "sell"], weights=[0.65, 0.35])[0]
        range_label, lo, hi = random.choice(VALUE_RANGES)
        mid = (lo + hi) / 2

        delay = random.randint(1, 45)
        disclosure = cur + timedelta(days=delay)
        if disclosure > end:
            disclosure = end

        records.append({
            "trader_id":         trader_id,
            "asset_symbol":      symbol,
            "asset_name":        asset["name"] if asset else symbol,
            "transaction_type":  txn,
            "trade_date":        cur,
            "disclosure_date":   disclosure,
            "value_range_label": range_label,
            "value_range_low":   Decimal(str(lo)),
            "value_range_high":  Decimal(str(hi)),
            "value_estimate":    Decimal(str(mid)),
        })

    return records


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
        logger.warning("Performance seed failed for trader %d: %s", trader.id, exc)
        return

    vals = [p.portfolio_value for p in result.portfolio_history]
    period_days = max((result.simulation_end - result.simulation_start).days, 1)
    metrics = compute_all(vals, [], period_days)
    # compute_all only sees the portfolio value series, not the individual
    # fills, so on its own it can only store win_rate 0.0 and trade_count 0.
    # The engine counted both during the run — keep its numbers.
    metrics["win_rate"] = result.win_rate
    metrics["trade_count"] = result.executed_trade_count

    existing = db.query(PerformanceMetric).filter(PerformanceMetric.trader_id == trader.id).first()
    if existing:
        for k, v in metrics.items():
            setattr(existing, k, v)
        existing.benchmark_return = (
            Decimal(str(result.benchmark_return_pct / 100))
            if result.benchmark_return_pct is not None else None
        )
        existing.period_start = result.simulation_start
        existing.period_end   = result.simulation_end
        existing.delay_days_used = 1
    else:
        db.add(PerformanceMetric(
            trader_id=trader.id,
            period_start=result.simulation_start,
            period_end=result.simulation_end,
            delay_days_used=1,
            benchmark_return=(
                Decimal(str(result.benchmark_return_pct / 100))
                if result.benchmark_return_pct is not None else None
            ),
            **metrics,
        ))


def seed_database(db: Session) -> None:
    """
    Idempotent seeder. Tries real EDGAR data first; falls back to
    synthetic GBM data if EDGAR is unreachable or returns no results.
    """
    if db.query(Trader).count() > 0:
        logger.info("Database already seeded — skipping.")
        return

    # ── Try real data first ───────────────────────────────────────────────────
    try:
        from app.core.real_seed import seed_real_data
        if seed_real_data(db):
            logger.info("Database seeded with real EDGAR insider trading data.")
            return
    except Exception as exc:
        logger.warning("Real seeder raised an exception (%s) — falling back to synthetic data.", exc)

    logger.info("Seeding database with synthetic traders + real price history...")

    # ── 1. Price data — try yfinance first, fall back to GBM ──────────────────
    symbols = [a["symbol"] for a in ASSETS]
    all_price_records = _fetch_real_prices(symbols)

    if all_price_records:
        logger.info("Using real yfinance prices (%d records).", len(all_price_records))
    else:
        logger.info("yfinance unavailable — generating GBM price series...")
        for asset in ASSETS:
            all_price_records.extend(
                _gbm_prices(
                    asset["symbol"], asset["base"], asset["drift"], asset["vol"],
                    DATA_START, DATA_END,
                )
            )

    ingest_prices(db, all_price_records)
    logger.info("Inserted %d price records.", len(all_price_records))

    # ── 2. Traders + trades ───────────────────────────────────────────────────
    for t_data in TRADERS:
        trader = Trader(**t_data)
        db.add(trader)
        db.flush()

        preferred = TRADER_ASSETS.get(t_data["name"], [a["symbol"] for a in ASSETS[:5]])
        n_trades = random.randint(45, 110)

        trade_records = _gen_trades(
            trader.id, preferred, n_trades, DATA_START, DATA_END
        )
        for rec in trade_records:
            db.add(Trade(**rec))

        db.flush()
        logger.info("Created trader '%s' with %d trades.", trader.name, len(trade_records))

    db.commit()

    # ── 3. Performance metrics ────────────────────────────────────────────────
    traders = db.query(Trader).all()
    for trader in traders:
        _compute_performance(db, trader)
    db.commit()

    logger.info("Seeding complete. %d traders, %d price records.", len(traders), len(all_price_records))
