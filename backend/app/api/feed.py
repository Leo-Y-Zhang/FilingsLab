"""
Live Disclosure Feed API
========================
GET  /api/feed/disclosures        — recent SEC Form 4 insider trades, scored (open)
GET  /api/feed/disclosures/{ticker} — insider trades for one ticker (open)
GET  /api/feed/broker/status      — paper portfolio status (token)
GET  /api/feed/portfolio          — positions and order history (token)
POST /api/feed/execute            — execute a paper trade (token)
DELETE /api/feed/position/{ticker} — close a paper position (token)

Everything that touches the paper account or the auto-trader requires the
operator bearer token (``API_TOKEN``); the two disclosure lookups are public
read-only research data and stay open, rate limited.
"""
from __future__ import annotations

import logging
import re
import threading
import time
from typing import Literal, Optional

import yfinance as yf
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.limiter import limiter
from app.core.security import require_api_token
from app.models.paper_portfolio import AutoTraderLog
from app.services import edgar
from app.services import signal_engine as se
from app.services import paper_broker as pb
from app.services import auto_trader as at

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/feed", tags=["Live Feed"])
settings = get_settings()

# Routes that change state or expose the operator's control surface.
_ADMIN = [Depends(require_api_token)]

# A cache miss on the disclosure feed costs ~18 s of in-request sleeping and up
# to 120 SEC Archives fetches, and `limit` was part of the cache key — so
# looping N=1..200 was 200 guaranteed misses from one anonymous client. Collapse
# every requested limit onto this short ladder: at most four upstream fetches
# exist, whatever a caller asks for. The UI only ever asks for 25/50/100, which
# land on their own buckets unchanged.
_LIMIT_BUCKETS = (25, 50, 100, 200)

# Tickers become cache keys and EDGAR searches, so they are validated, not
# merely upper-cased. Same shape as the forecast router's whitelist.
_TICKER_RE = re.compile(r"^[A-Za-z0-9.\-]{1,12}$")

# ── What a cold visitor is told ───────────────────────────────────────────────
# The cold path is two background stages: the EDGAR crawl (~20 s, paced to stay
# inside SEC's guidance) and then pricing every returned filing. Both are now
# chained, so they run back to back without waiting for another request — but
# the client still has to come back and collect the result, and the steady-state
# poll is five minutes. Left at five minutes a lone visitor waits about ten,
# which is what the review measured. So the warming response says how soon to
# ask again, and the UI honours it.
#
# 15 s is four requests a minute against a 10/minute budget for this route, so
# even a couple of open tabs stay inside the limit while warming.
_WARMING_RETRY_SECONDS = 15

_WARMING_MESSAGE = (
    "Warming up. FilingsLab is crawling SEC EDGAR for recent Form 4 filings and "
    "then pricing each one; both stages run in the background so this page "
    "stays responsive. The first load after a restart usually takes under a "
    "minute, and a few minutes when EDGAR is slow. This page retries "
    f"automatically every {_WARMING_RETRY_SECONDS} seconds."
)

_NO_DATA_MESSAGE = (
    "No Form 4 transactions found in the past 14 days (market may be closed or "
    "no significant trades)."
)


# ── Enrichment cache ──────────────────────────────────────────────────────────
# Moving the EDGAR crawl off the request thread (see app/services/edgar.py) is
# only half of it. `_enrich` runs per disclosure, and per disclosure it makes two
# yfinance calls and one Kronos call — up to 200 rows is up to 600 network round
# trips, on the same anyio worker the crawl used to hold. A cached feed that then
# blocks on enrichment has moved the stall, not removed it.
#
# So the enriched payload gets the same treatment as the raw one: the request
# path reads a cache and schedules the work, single flight per key, bounded
# process-wide. The key carries a fingerprint of the raw rows, so new filings are
# re-enriched promptly but a repeat request never re-enriches the same data.

_ENRICH_TTL             = 600   # seconds; prices go stale, filings do not
_ENRICH_MIN_INTERVAL    = 30    # seconds between attempts on the same key
_MAX_ENRICH_JOBS        = 2
_MAX_ENRICH_ENTRIES     = 32
# _enrich_last_attempt is keyed on the caller's ticker exactly as _enrich_cache
# is, so capping only the cache left the same unbounded-growth surface open one
# layer up. Same rule as app/services/edgar.py: expired records go first, live
# ones only if every record is still inside the backoff window.
_MAX_ENRICH_ATTEMPTS    = 64

_enrich_lock = threading.Lock()
_enrich_cache: dict[str, tuple[float, str, list[dict]]] = {}   # key -> (ts, fingerprint, rows)
_enrich_inflight: set[str] = set()
_enrich_last_attempt: dict[str, float] = {}


def reset_enrichment_state() -> None:
    """Test hook: drop every cached/failed enrichment."""
    with _enrich_lock:
        _enrich_cache.clear()
        _enrich_last_attempt.clear()


def _fingerprint(raw: list[dict]) -> str:
    return str(
        hash(
            tuple(
                (r.get("trader_name"), r.get("ticker"), r.get("trade_date"), r.get("transaction_type"))
                for r in raw
            )
        )
    )


def _prune_enrich_attempts(now: float) -> None:
    """Make room for one more attempt record. Caller must hold ``_enrich_lock``."""
    if len(_enrich_last_attempt) < _MAX_ENRICH_ATTEMPTS:
        return
    for expired in [k for k, ts in _enrich_last_attempt.items()
                    if now - ts >= _ENRICH_MIN_INTERVAL]:
        _enrich_last_attempt.pop(expired, None)
    while len(_enrich_last_attempt) >= _MAX_ENRICH_ATTEMPTS:
        oldest = min(_enrich_last_attempt, key=_enrich_last_attempt.__getitem__)
        _enrich_last_attempt.pop(oldest, None)


def _claim_enrich(key: str) -> bool:
    now = time.time()
    with _enrich_lock:
        if key in _enrich_inflight:
            return False
        if now - _enrich_last_attempt.get(key, 0.0) < _ENRICH_MIN_INTERVAL:
            return False
        if len(_enrich_inflight) >= _MAX_ENRICH_JOBS:
            return False
        if key not in _enrich_last_attempt:
            _prune_enrich_attempts(now)
        _enrich_last_attempt[key] = now
        _enrich_inflight.add(key)
        return True


def _run_enrich(key: str, fingerprint: str, raw: list[dict]) -> None:
    try:
        rows = _enrich(raw)
        with _enrich_lock:
            if key not in _enrich_cache and len(_enrich_cache) >= _MAX_ENRICH_ENTRIES:
                oldest = min(_enrich_cache, key=lambda k: _enrich_cache[k][0])
                _enrich_cache.pop(oldest, None)
            _enrich_cache[key] = (time.time(), fingerprint, rows)
    except Exception:
        logger.exception("Enrichment failed for %s", key)
    finally:
        with _enrich_lock:
            _enrich_inflight.discard(key)


def _is_enrichment_fresh(key: str, fingerprint: str) -> bool:
    entry = _enrich_cache.get(key)
    return (
        entry is not None
        and entry[1] == fingerprint
        and time.time() - entry[0] < _ENRICH_TTL
    )


def _schedule_enrich(key: str, raw: list[dict]) -> bool:
    """
    Start enrichment for *raw* on a background thread if it is needed and not
    already running. Returns True if a job was started. Never blocks, and never
    runs `_enrich` on the calling thread.
    """
    if not raw:
        return False
    fingerprint = _fingerprint(raw)
    if _is_enrichment_fresh(key, fingerprint):
        return False
    if not _claim_enrich(key):
        return False
    threading.Thread(
        target=_run_enrich,
        args=(key, fingerprint, raw),
        name=f"feed-enrich-{key}",
        daemon=True,
    ).start()
    return True


def _enriched(key: str, raw: list[dict]) -> tuple[list[dict], bool]:
    """
    Return ``(rows, warming)`` for *raw* without ever running `_enrich` here.

    ``warming`` is True only when there is nothing at all to show yet — an empty
    list because the enrichment has not run once, as opposed to an empty list
    because EDGAR genuinely returned nothing.
    """
    if not raw:
        return [], False

    entry = _enrich_cache.get(key)
    if _is_enrichment_fresh(key, _fingerprint(raw)):
        return entry[2], False

    _schedule_enrich(key, raw)

    # Last known good beats nothing, even if it is for slightly older filings.
    if entry is not None:
        return entry[2], False
    return [], True


# ── Helpers ───────────────────────────────────────────────────────────────────

def _bucket_limit(limit: int) -> int:
    """Round a caller-supplied limit up onto the fixed cache-key ladder."""
    for bucket in _LIMIT_BUCKETS:
        if limit <= bucket:
            return bucket
    return _LIMIT_BUCKETS[-1]


def _warming_or_empty(warming: bool) -> dict:
    """
    The body for a feed with nothing to show. ``warming`` and "EDGAR returned
    nothing" are different answers and get different messages; only the first
    asks the client to come back soon.

    The hint goes in the body rather than on ``Retry-After``, even though that
    is the header for exactly this. slowapi already writes ``Retry-After`` on
    every response from a limited route, where it means "your rate-limit window
    resets in N seconds" (see ``Limiter._inject_headers`` and the note in
    app/core/limiter.py). Overwriting it would hand the client a different
    quantity under the same name and destroy the back-off signal the limiter
    module deliberately kept. Two meanings, two fields.
    """
    body: dict = {
        "configured": True,
        "count": 0,
        "disclosures": [],
        "warming": warming,
        "message": _WARMING_MESSAGE if warming else _NO_DATA_MESSAGE,
    }
    if warming:
        body["retry_after_seconds"] = _WARMING_RETRY_SECONDS
    return body


def _validate_ticker(ticker: str) -> str:
    if not _TICKER_RE.match(ticker):
        raise HTTPException(422, f"Invalid ticker: {ticker[:16]!r}")
    return ticker.upper()

def _current_price(ticker: str) -> Optional[float]:
    try:
        info = yf.Ticker(ticker).fast_info
        return float(info.last_price or info.previous_close or 0) or None
    except Exception:
        return None


def _enrich(disclosures: list[dict]) -> list[dict]:
    from app.services.auto_trader import _cluster_counts, _kronos_expected_return, _volume_ratio
    clusters  = _cluster_counts(disclosures)
    results   = []
    for d in disclosures:
        ticker    = d.get("ticker", "")
        tx_type   = d.get("transaction_type", "buy")
        price_now = _current_price(ticker) if ticker else None

        # Enrich with volume + Kronos (cached — fast after first call)
        vol_ratio = _volume_ratio(ticker) if ticker else 1.0
        kronos    = _kronos_expected_return(ticker) if ticker else None

        score, reason = se.score_signal(
            trader_name            = d.get("trader_name", ""),
            ticker                 = ticker,
            transaction_type       = tx_type,
            trade_date             = d.get("trade_date"),
            disclosure_date        = d.get("disclosure_date"),
            amount_est             = d.get("amount_est"),
            trader_role            = d.get("trader_role", ""),
            current_price          = price_now,
            volume_ratio           = vol_ratio,
            kronos_expected_return = kronos,
            cluster_count          = clusters.get(ticker, 1),
        )
        action = se.action_for_score(score, tx_type)
        results.append({
            **d,
            "score":        score,
            "action":       action,
            "price_now":    price_now,
            "score_reason": reason,
            "kronos_pct":   round(kronos * 100, 1) if kronos is not None else None,
            "volume_ratio": vol_ratio,
            "cluster":      clusters.get(ticker, 1),
        })
    results.sort(key=lambda x: x["score"], reverse=True)
    return results


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/disclosures", summary="Recent insider trades, scored")
@limiter.limit("10/minute")
def get_disclosures(
    request: Request,
    response: Response,
    limit: int = Query(50, ge=1, le=200),
):
    bucket = _bucket_limit(limit)
    key = f"recent:{bucket}"
    # Cache-first and non-blocking, twice over: the EDGAR crawl paces itself over
    # ~18 s (app/services/edgar.py) and enrichment costs up to three network
    # calls per row. Neither may run on an anyio request worker.
    #
    # The callback chains the two stages. When this request is the one that
    # schedules the crawl, the enrichment starts on the background thread the
    # moment the filings land, rather than waiting for the visitor to come back
    # and ask again — one whole poll interval off the cold path.
    raw = edgar.fetch_recent(
        limit=bucket,
        on_refresh=lambda rows: _schedule_enrich(key, rows),
    )
    enriched, enrich_warming = _enriched(key, raw)
    enriched = enriched[:limit]

    if not enriched:
        warming = enrich_warming or edgar.is_warming(limit=bucket)
        return _warming_or_empty(warming)
    return {
        "configured": True,
        "count": len(enriched),
        "disclosures": enriched,
        "warming": False,
        "message": None,
    }


@router.get("/disclosures/{ticker}", summary="Insider trades for a ticker")
@limiter.limit("10/minute")
def get_disclosures_for_ticker(request: Request, response: Response, ticker: str):
    sym = _validate_ticker(ticker)
    key = f"ticker:{sym}"
    raw = edgar.fetch_for_ticker(sym, on_refresh=lambda rows: _schedule_enrich(key, rows))
    enriched, enrich_warming = _enriched(key, raw)
    warming = (enrich_warming or edgar.is_warming(ticker=sym)) if not enriched else False
    body = {
        "ticker": sym,
        "count": len(enriched),
        "disclosures": enriched,
        "warming": warming,
    }
    if warming:
        body["retry_after_seconds"] = _WARMING_RETRY_SECONDS
    return body


@router.get("/broker/status", summary="Paper portfolio status", dependencies=_ADMIN)
def broker_status(db: Session = Depends(get_db)):
    return pb.get_status(db)


@router.get("/portfolio", summary="Paper portfolio positions", dependencies=_ADMIN)
def get_portfolio(db: Session = Depends(get_db)):
    return pb.get_portfolio(db)


# The paper account starts with $100,000 of virtual cash; these ceilings are
# far above any legitimate order and stop a single request from moving numbers
# the UI reports as performance.
_MAX_NOTIONAL = 10_000_000.0
_MAX_QTY      = 1_000_000.0


class ExecuteRequest(BaseModel):
    ticker:   str = Field(..., min_length=1, max_length=12, pattern=r"^[A-Za-z0-9.\-]+$")
    side:     Literal["buy", "sell"]
    # gt=0 is the fix for the confirmed exploit: a negative notional was
    # SUBTRACTED from cash on a "buy", inventing balance out of nothing and
    # inflating total_return_pct.
    notional: Optional[float] = Field(None, gt=0, le=_MAX_NOTIONAL)
    qty:      Optional[float] = Field(None, gt=0, le=_MAX_QTY)


@router.post("/execute", summary="Execute a paper trade", dependencies=_ADMIN)
def execute_trade(req: ExecuteRequest, db: Session = Depends(get_db)):
    ticker = req.ticker.upper()
    if not req.notional and not req.qty:
        raise HTTPException(422, "provide notional (dollars) or qty (shares)")
    try:
        result = pb.execute_trade(db, ticker, req.side, notional=req.notional, qty=req.qty)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return {"order": result, "simulated": False}


@router.delete("/position/{ticker}", summary="Close a paper position", dependencies=_ADMIN)
def close_position(ticker: str, db: Session = Depends(get_db)):
    result = pb.close_position(db, _validate_ticker(ticker))
    if result is None:
        raise HTTPException(404, f"No open position for {ticker.upper()}")
    return {"result": result}


# ── Auto-trader endpoints ──────────────────────────────────────────────────────

@router.get("/auto-trader/config", summary="Get auto-trader configuration", dependencies=_ADMIN)
def get_auto_trader_config(db: Session = Depends(get_db)):
    cfg = at.get_or_create_config(db)
    return {
        "enabled":            cfg.enabled,
        "min_score":          cfg.min_score,
        "trade_buys":         cfg.trade_buys,
        "trade_sell_signals": cfg.trade_sell_signals,
        "max_position_pct":   cfg.max_position_pct,
        "max_positions":      cfg.max_positions,
        "take_profit_pct":    cfg.take_profit_pct,
        "stop_loss_pct":      cfg.stop_loss_pct,
        "run_interval_mins":  cfg.run_interval_mins,
        "last_run_at":        cfg.last_run_at.isoformat() if cfg.last_run_at else None,
        "last_run_summary":   cfg.last_run_summary,
    }


class AutoTraderConfigRequest(BaseModel):
    """
    Every numeric field is bounded. Unbounded, these were not merely silly
    values: run_interval_mins=0 busy-loops the background thread and a negative
    one raises inside time.sleep, killing the loop until restart.
    """
    enabled:            Optional[bool]  = None
    min_score:          Optional[float] = Field(None, ge=0, le=100)
    trade_buys:         Optional[bool]  = None
    trade_sell_signals: Optional[bool]  = None
    max_position_pct:   Optional[float] = Field(None, gt=0, le=100)
    max_positions:      Optional[int]   = Field(None, ge=1, le=100)
    take_profit_pct:    Optional[float] = Field(None, gt=0, le=1000)
    stop_loss_pct:      Optional[float] = Field(None, gt=0, le=100)
    run_interval_mins:  Optional[int]   = Field(None, ge=1, le=1440)


@router.post("/auto-trader/config", summary="Update auto-trader configuration", dependencies=_ADMIN)
def update_auto_trader_config(req: AutoTraderConfigRequest, db: Session = Depends(get_db)):
    updates = {k: v for k, v in req.model_dump().items() if v is not None}
    cfg = at.update_config(db, **updates)
    return {"saved": True, "enabled": cfg.enabled}


@router.post("/auto-trader/run", summary="Trigger an auto-trader cycle immediately", dependencies=_ADMIN)
@limiter.limit("5/minute")
def run_auto_trader_now(request: Request, response: Response):
    try:
        summary = at.trigger_now()
        return {"status": "ok", "summary": summary}
    except Exception as exc:
        logger.exception("Auto-trader manual run failed")
        raise HTTPException(500, "Auto-trader cycle failed; see server log.")


@router.get("/auto-trader/log", summary="Recent auto-trader activity log", dependencies=_ADMIN)
def get_auto_trader_log(db: Session = Depends(get_db), limit: int = Query(50, ge=1, le=200)):
    rows = (
        db.query(AutoTraderLog)
        .order_by(AutoTraderLog.created_at.desc())
        .limit(limit)
        .all()
    )
    return {
        "count": len(rows),
        "log": [
            {
                "id":         r.id,
                "action":     r.action,
                "ticker":     r.ticker,
                "reason":     r.reason,
                "score":      r.score,
                "price":      r.price,
                "notional":   r.notional,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ],
    }
