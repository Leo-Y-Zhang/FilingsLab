"""
Kronos AI Forecast API
======================
GET  /api/forecast/status          — Kronos availability + hardware info
GET  /api/forecast/history/{sym}   — Last N days OHLCV for chart context
GET  /api/forecast/{symbol}        — AI price forecast (pred_days trading days)
"""
import re
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.limiter import limiter
from app.kronos import service as kronos
from app.models.price import Price
from app.schemas.forecast import ForecastResult, HistoricalPoint, KronosStatus

router = APIRouter(prefix="/forecast", tags=["Kronos Forecast"])

# Whitelist: uppercase letters, digits, dots (e.g. "BRK.A"), hyphens
_SYMBOL_RE = re.compile(r"^[A-Z0-9.\-]{1,12}$")


def _validate_symbol(symbol: str) -> str:
    s = symbol.upper().strip()
    if not _SYMBOL_RE.match(s):
        raise HTTPException(status_code=422, detail=f"Invalid symbol: {symbol!r}")
    return s


def _db_history(db: Session, symbol: str, days: int) -> list[dict]:
    """Fallback: pull OHLCV from the FilingsLab synthetic price database."""
    rows = (
        db.query(Price)
        .filter(Price.asset_symbol == symbol)
        .order_by(Price.date.desc())
        .limit(days)
        .all()
    )
    if not rows:
        return []
    return [
        {
            "date":  str(r.date),
            "open":  round(float(r.open_price  or r.closing_price), 4),
            "high":  round(float(r.high_price  or r.closing_price), 4),
            "low":   round(float(r.low_price   or r.closing_price), 4),
            "close": round(float(r.closing_price), 4),
        }
        for r in reversed(rows)
    ]


@router.get("/status", response_model=KronosStatus, summary="Kronos availability")
def forecast_status():
    """Check whether Kronos AI forecasting is ready on this server."""
    return kronos.get_status()


@router.get(
    "/history/{symbol}",
    response_model=list[HistoricalPoint],
    summary="Historical OHLCV for chart context",
)
def history(
    symbol: str,
    days: int = Query(60, ge=10, le=500, description="Number of past trading days"),
    db: Session = Depends(get_db),
):
    """Return recent OHLCV for *symbol* — yfinance first, DB fallback."""
    sym = _validate_symbol(symbol)
    try:
        data = kronos.get_historical_for_chart(sym, days=days)
    except Exception:
        data = []

    if not data:
        data = _db_history(db, sym, days)

    if not data:
        raise HTTPException(
            status_code=404,
            detail=f"No market data for {sym!r}. yfinance may be unavailable and this symbol is not in the local database.",
        )
    return data


@router.get(
    "/{symbol}",
    response_model=ForecastResult,
    summary="Kronos AI price forecast",
)
@limiter.limit("10/minute")
def forecast(
    request: Request,
    response: Response,
    symbol: str,
    pred_days: int = Query(
        10, ge=5, le=30,
        description="Future trading days to forecast (5–30)",
    ),
):
    """
    Run Kronos AI price forecast for *symbol*.

    Returns predicted open / high / low / close for the next `pred_days` trading days.
    Results are cached in memory for **1 hour**.

    Requires Kronos to be set up (`python setup_kronos.py`).
    """
    sym = _validate_symbol(symbol)
    try:
        return kronos.get_forecast(sym, pred_days)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
