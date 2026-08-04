"""
Kronos AI Forecasting Service — FilingsLab
======================================
Wraps the Kronos foundation model (AAAI 2026, MIT licence) for real-time
asset price forecasting using yfinance OHLCV data.

GitHub:  https://github.com/shiyu-coder/Kronos
Licence: MIT

Setup (one-time):
    python setup_kronos.py          # clones Kronos into backend/kronos_lib/
    pip install -r requirements.txt  # installs torch + Kronos deps
    docker compose up --build        # rebuilds image
"""
from __future__ import annotations

import logging
import sys
import time
from pathlib import Path
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)

# ── Kronos library location ───────────────────────────────────────────────────
# setup_kronos.py clones into  <project>/backend/kronos_lib/
# In Docker (volume mount ./backend:/app) that maps to  /app/kronos_lib/
_THIS = Path(__file__).parent           # backend/app/kronos/
_BACKEND = _THIS.parent.parent          # backend/
KRONOS_LIB_PATH = _BACKEND / "kronos_lib"

# ── In-memory state ───────────────────────────────────────────────────────────
_predictor = None
_available: Optional[bool] = None
_forecast_cache: dict[str, tuple[float, list[dict]]] = {}
CACHE_TTL = 3600  # 1 hour

# Assets tracked by FilingsLab seed data
TRACKED_ASSETS: list[str] = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA",
    "JPM", "PFE", "XOM", "LMT", "BA",
    "META", "TSLA", "AMD", "UNH", "MRK", "SPY",
]


# ── Availability check ────────────────────────────────────────────────────────

def _ensure_path() -> None:
    if KRONOS_LIB_PATH.exists():
        p = str(KRONOS_LIB_PATH)
        if p not in sys.path:
            sys.path.insert(0, p)


def check_available() -> bool:
    """True if Kronos model code + torch are importable."""
    global _available
    if _available is not None:
        return _available

    _ensure_path()
    try:
        import torch          # noqa: F401
        from model import Kronos, KronosTokenizer, KronosPredictor  # noqa: F401
        _available = True
    except ImportError:
        _available = False

    return _available


def get_status() -> dict:
    """Return availability, hardware info, and setup instructions."""
    ok = check_available()
    device = "unavailable"
    gpu: Optional[str] = None

    if ok:
        import torch
        if torch.cuda.is_available():
            gpu = torch.cuda.get_device_name(0)
            device = f"cuda ({gpu})"
        else:
            device = "cpu (no GPU — inference will be slower)"

    return {
        "available": ok,
        "model": "Kronos-mini (4.1 M params · 2 k context)",
        "device": device,
        "gpu": gpu,
        "kronos_lib_path": str(KRONOS_LIB_PATH),
        "setup_required": not ok,
        "setup_instructions": (
            None if ok else
            "Run `python setup_kronos.py` at project root, "
            "then `pip install -r backend/requirements.txt`, "
            "then rebuild Docker (`docker compose up --build`)."
        ),
    }


# ── Model loading ─────────────────────────────────────────────────────────────

def _load_predictor():
    """Lazy-load Kronos-mini (called once; result cached in _predictor)."""
    global _predictor
    if _predictor is not None:
        return _predictor

    _ensure_path()

    import torch
    from model import Kronos, KronosTokenizer, KronosPredictor

    device = "cuda:0" if torch.cuda.is_available() else "cpu"
    logger.info("Loading Kronos-mini on %s …", device)

    tokenizer = KronosTokenizer.from_pretrained("NeoQuasar/Kronos-Tokenizer-2k")
    model     = Kronos.from_pretrained("NeoQuasar/Kronos-mini")
    _predictor = KronosPredictor(model, tokenizer, device=device, max_context=2048)

    logger.info("Kronos-mini ready on %s.", device)
    return _predictor


# ── Market data ───────────────────────────────────────────────────────────────

def _fetch_ohlcv(symbol: str, period: str = "2y") -> pd.DataFrame:
    """
    Fetch real OHLCV data via yfinance.
    Returns a DatetimeIndex DataFrame with columns open/high/low/close/volume.
    Empty DataFrame if unavailable.
    """
    import yfinance as yf

    valid = {"1y": "1y", "2y": "2y", "5y": "5y"}
    yf_period = valid.get(period, "2y")

    try:
        hist = yf.Ticker(symbol.upper()).history(period=yf_period)
    except Exception as exc:
        logger.warning("yfinance error for %s: %s", symbol, exc)
        return pd.DataFrame()

    if hist.empty:
        return pd.DataFrame()

    df = pd.DataFrame({
        "open":   hist["Open"].astype(float),
        "high":   hist["High"].astype(float),
        "low":    hist["Low"].astype(float),
        "close":  hist["Close"].astype(float),
        "volume": hist["Volume"].fillna(0).astype(int),
    }, index=hist.index)

    return df.dropna(subset=["open", "high", "low", "close"])


# ── Forecast ──────────────────────────────────────────────────────────────────

def get_forecast(symbol: str, pred_days: int = 10) -> dict:
    """
    Run Kronos AI price forecast for *symbol*.

    Args:
        symbol:    Stock ticker (e.g. "AAPL").
        pred_days: Future trading days to predict (5–30).

    Returns:
        {
            "source":      "kronos" | "cache",
            "model":       "Kronos-mini",
            "device":      "cpu" | "cuda (...)",
            "symbol":      "AAPL",
            "predictions": [
                {
                  "date": "YYYY-MM-DD",
                  "open": float, "high": float,
                  "low":  float, "close": float,
                },
                ...
            ]
        }

    Raises:
        RuntimeError: Kronos not set up (setup_kronos.py not run).
        ValueError:   Insufficient OHLCV history.
    """
    # ── Sanitise symbol (prevent cache key injection) ──
    safe = symbol.upper().replace("/", "").replace("\\", "").replace("..", "")
    cache_key = f"{safe}_{pred_days}"
    now = time.time()

    if cache_key in _forecast_cache:
        ts, data = _forecast_cache[cache_key]
        if now - ts < CACHE_TTL:
            return {"source": "cache", "model": "Kronos-mini", "symbol": safe, "predictions": data}

    if not check_available():
        raise RuntimeError(
            "Kronos is not set up. "
            "Run `python setup_kronos.py` at the project root, then "
            "`pip install -r backend/requirements.txt`, then rebuild Docker."
        )

    predictor = _load_predictor()

    df = _fetch_ohlcv(safe, period="2y")
    if df.empty:
        raise ValueError(f"No OHLCV data available for {safe}.")
    if len(df) < 30:
        raise ValueError(
            f"Insufficient history for {safe}: {len(df)} days available, need ≥ 30."
        )

    # Kronos-mini supports 2 048-token context; cap at 400 bars for stability
    ctx = df.iloc[-min(len(df), 400):]
    x_df = ctx[["open", "high", "low", "close"]].reset_index(drop=True)
    x_ts  = pd.Series(ctx.index)

    last_date = pd.Timestamp(ctx.index[-1])
    y_ts = pd.bdate_range(start=last_date + pd.Timedelta(days=1), periods=pred_days)

    import torch
    device_str = "cuda:0" if torch.cuda.is_available() else "cpu"

    pred_df = predictor.predict(
        df=x_df,
        x_timestamp=x_ts,
        y_timestamp=pd.Series(y_ts),
        pred_len=pred_days,
        T=0.8,
        top_p=0.9,
        sample_count=3,   # average 3 paths → smoother output
        verbose=False,
    )

    predictions = [
        {
            "date":  pd.Timestamp(dt).strftime("%Y-%m-%d"),
            "open":  round(float(row["open"]),  4),
            "high":  round(float(row["high"]),  4),
            "low":   round(float(row["low"]),   4),
            "close": round(float(row["close"]), 4),
        }
        for dt, row in pred_df.iterrows()
    ]

    _forecast_cache[cache_key] = (now, predictions)

    return {
        "source":      "kronos",
        "model":       "Kronos-mini",
        "device":      device_str,
        "symbol":      safe,
        "predictions": predictions,
    }


def get_historical_for_chart(symbol: str, days: int = 60) -> list[dict]:
    """
    Return last `days` trading days of closing prices for chart display.
    Uses real yfinance data so the chart context matches the Kronos input.
    """
    df = _fetch_ohlcv(symbol, period="1y")
    if df.empty:
        return []

    recent = df.tail(days)
    return [
        {
            "date":  pd.Timestamp(idx).strftime("%Y-%m-%d"),
            "open":  round(float(row["open"]),  4),
            "high":  round(float(row["high"]),  4),
            "low":   round(float(row["low"]),   4),
            "close": round(float(row["close"]), 4),
        }
        for idx, row in recent.iterrows()
    ]
