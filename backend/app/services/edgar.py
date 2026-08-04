"""
SEC EDGAR Form 4 Client
=======================
Fetches real insider trading disclosures directly from SEC EDGAR.
No API key required — completely free and official.

Form 4 = Statement of Changes in Beneficial Ownership
Filed by corporate directors, officers, and 10%+ shareholders.

We only capture transaction codes:
  P = Open market purchase  → buy signal
  S = Open market sale      → sell signal
"""
from __future__ import annotations

import logging
import threading
import time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta
from typing import Callable, Optional

import httpx

logger = logging.getLogger(__name__)

_SEARCH  = "https://efts.sec.gov/LATEST/search-index"
_ARCHIVE = "https://www.sec.gov/Archives/edgar/data"
_HEADERS = {"User-Agent": "FilingsLab research@filingslab.local"}

_CACHE_TTL = 900  # 15 minutes

# The cache key is caller-influenced (a limit, or a ticker), so it needs a hard
# ceiling as well as a TTL — otherwise a caller can grow this dict without
# bound. The API layer buckets limits and validates tickers; this is the
# belt-and-braces at the layer that actually holds the memory.
_MAX_CACHE_ENTRIES = 64

_cache: dict[str, tuple[float, list[dict]]] = {}


def _cached(key: str) -> Optional[list[dict]]:
    entry = _cache.get(key)
    if entry and time.time() - entry[0] < _CACHE_TTL:
        return entry[1]
    return None


def _store(key: str, data: list[dict]) -> None:
    if key not in _cache and len(_cache) >= _MAX_CACHE_ENTRIES:
        oldest = min(_cache, key=lambda k: _cache[k][0])
        _cache.pop(oldest, None)
    _cache[key] = (time.time(), data)


def _stale(key: str) -> Optional[list[dict]]:
    """Last known data for *key*, however old. None if we have never had any."""
    entry = _cache.get(key)
    return entry[1] if entry else None


# ── Background refresh ─────────────────────────────────────────────────────────
# A crawl is ~120 archive fetches paced at 0.15 s apart to respect SEC's 10 req/s
# guidance, so it takes about 18 seconds of wall clock. That work must never
# happen on a request thread: FastAPI runs sync endpoints on anyio's threadpool,
# which is 40 workers for the WHOLE process, so 40 concurrent cache misses stall
# every route in the app — health check included — for the length of a crawl.
# 10 requests/minute is a per-IP limit, and ~14 source IPs at that rate is
# already 40 concurrent misses, so the rate limiter cannot close this by itself.
#
# So: the request path is cache-only. It answers from the cache (fresh, or stale
# if that is all there is, or empty), and *schedules* the crawl. Callers that are
# not request threads — the auto-trader loop — use refresh_recent_now().
#
# Three bounds on the scheduled work:
#   * single flight per key, so N concurrent misses are one crawl, not N
#   * at most _MAX_CONCURRENT_REFRESHES crawls in the whole process
#   * at most one attempt per key per _MIN_REFRESH_INTERVAL, success or failure,
#     so an EDGAR outage cannot be turned into a crawl per allowed request

_MIN_REFRESH_INTERVAL = 120     # seconds between attempts on the same key
_MAX_CONCURRENT_REFRESHES = 2

# _last_attempt is written with the same caller-influenced key as _cache, so
# bounding _cache alone left half the leak open: 500 distinct tickers through
# the public feed held _cache at 64 and grew _last_attempt to 500. Anything
# keyed by a caller on a public path gets a ceiling.
#
# The ceiling is larger than the cache's on purpose. An entry here is a
# *backoff* record — it is what stops an EDGAR outage becoming one crawl per
# allowed request — and it must outlive the cached payload it protects, so the
# cheap dict of floats gets more room than the dict of filing lists.
_MAX_ATTEMPT_ENTRIES = 128

_refresh_lock = threading.Lock()
_inflight: set[str] = set()
_last_attempt: dict[str, float] = {}


def _prune_attempts(now: float) -> None:
    """
    Make room for one more attempt record. Caller must hold ``_refresh_lock``.

    Expired records are dropped first because they carry no remaining meaning —
    ``_claim_refresh`` would ignore them anyway. Only when every record is still
    inside the backoff window does this evict a live one, oldest first, which
    costs at worst one extra crawl for a key that has not been asked for in the
    longest time.
    """
    if len(_last_attempt) < _MAX_ATTEMPT_ENTRIES:
        return
    for expired in [k for k, ts in _last_attempt.items() if now - ts >= _MIN_REFRESH_INTERVAL]:
        _last_attempt.pop(expired, None)
    while len(_last_attempt) >= _MAX_ATTEMPT_ENTRIES:
        oldest = min(_last_attempt, key=_last_attempt.__getitem__)
        _last_attempt.pop(oldest, None)


def _claim_refresh(key: str) -> bool:
    """Reserve the right to crawl *key* now. False means somebody else has it."""
    now = time.time()
    with _refresh_lock:
        if key in _inflight:
            return False
        if now - _last_attempt.get(key, 0.0) < _MIN_REFRESH_INTERVAL:
            return False
        if len(_inflight) >= _MAX_CONCURRENT_REFRESHES:
            logger.debug("EDGAR refresh for %s skipped: %d already running", key, len(_inflight))
            return False
        if key not in _last_attempt:
            _prune_attempts(now)
        _last_attempt[key] = now
        _inflight.add(key)
        return True


def _release_refresh(key: str) -> None:
    with _refresh_lock:
        _inflight.discard(key)


def _run_refresh(
    key: str,
    build: Callable[[], list[dict]],
    on_refresh: Optional[Callable[[list[dict]], None]] = None,
) -> list[dict]:
    try:
        data = build()
        _store(key, data)
        return data
    except Exception:
        # The stale entry, if any, is left in place: last-known-good beats empty.
        logger.exception("EDGAR refresh failed for %s", key)
        return _stale(key) or []
    finally:
        _release_refresh(key)
        # After the slot is released, so a downstream stage cannot occupy a
        # crawl slot, and outside the try, so a failed crawl still notifies —
        # the caller decides what to do with whatever is cached.
        if on_refresh is not None:
            try:
                on_refresh(_cached(key) or _stale(key) or [])
            except Exception:
                logger.exception("EDGAR refresh callback failed for %s", key)


def _schedule_refresh(
    key: str,
    build: Callable[[], list[dict]],
    on_refresh: Optional[Callable[[list[dict]], None]] = None,
) -> None:
    if not _claim_refresh(key):
        return
    threading.Thread(
        target=_run_refresh,
        args=(key, build, on_refresh),
        name=f"edgar-refresh-{key}",
        daemon=True,
    ).start()


def _cache_first(
    key: str,
    build: Callable[[], list[dict]],
    on_refresh: Optional[Callable[[list[dict]], None]] = None,
) -> list[dict]:
    """
    Serve *key* from cache and refresh it in the background. Never blocks.

    ``on_refresh`` is called on the background thread once the crawl has
    finished and the cache has been updated. It exists so a caller with a
    *second* stage of work — the feed's enrichment — can start it the moment
    this stage lands, instead of waiting for the next inbound request. Without
    it a cold visitor needs one request per stage, which is one client poll
    interval per stage, which is how "a few seconds" measured at ten minutes.
    """
    fresh = _cached(key)
    if fresh is not None:
        return fresh
    _schedule_refresh(key, build, on_refresh)
    return _stale(key) or []


# ── EDGAR search ───────────────────────────────────────────────────────────────

def _search(days_back: int, limit: int) -> list[dict]:
    start = (date.today() - timedelta(days=days_back)).isoformat()
    end   = date.today().isoformat()
    try:
        r = httpx.get(
            _SEARCH,
            headers=_HEADERS,
            params={"forms": "4", "dateRange": "custom", "startdt": start, "enddt": end},
            timeout=15,
        )
        r.raise_for_status()
        return r.json().get("hits", {}).get("hits", [])[:limit]
    except Exception as exc:
        logger.warning("EDGAR search failed: %s", exc)
        return []


# ── XML fetch & parse ──────────────────────────────────────────────────────────

_archives_429_count = 0   # module-level counter for consecutive 429s


def _fetch_xml(adsh: str, ciks: list[str], filename: str) -> Optional[str]:
    """Try each CIK until we get the XML."""
    global _archives_429_count
    adsh_clean = adsh.replace("-", "")
    for cik in ciks:
        url = f"{_ARCHIVE}/{cik.lstrip('0')}/{adsh_clean}/{filename}"
        try:
            r = httpx.get(url, headers=_HEADERS, timeout=12)
            if r.status_code == 200:
                _archives_429_count = 0   # reset on success
                return r.text
            if r.status_code == 429:
                _archives_429_count += 1
                logger.debug("EDGAR Archives 429 (consecutive: %d)", _archives_429_count)
                return None   # fail fast — caller checks consecutive count
            # 404 / other — try next CIK
        except Exception:
            pass
    return None


def _text(parent: ET.Element, tag: str) -> Optional[str]:
    el = parent.find(f".//{tag}/value")
    if el is not None:
        return el.text
    el = parent.find(f".//{tag}")
    return el.text if el is not None else None


def _parse_xml(xml_str: str, file_date: str) -> list[dict]:
    try:
        root = ET.fromstring(xml_str)
    except ET.ParseError:
        return []

    ticker  = (_text(root, "issuerTradingSymbol") or "").upper().strip()
    company = _text(root, "issuerName") or ""

    if not ticker:
        return []

    # Insider identity & role
    insider     = _text(root, "rptOwnerName") or "Unknown"
    insider_cik = (_text(root, "rptOwnerCik") or "").strip()
    is_dir  = (_text(root, "isDirector")        or "").lower() in ("true", "1")
    is_off  = (_text(root, "isOfficer")         or "").lower() in ("true", "1")
    is_10pct= (_text(root, "isTenPercentOwner") or "").lower() in ("true", "1")
    title   = _text(root, "officerTitle") or ""

    if is_off:
        role = title or "Officer"
    elif is_dir:
        role = "Director"
    elif is_10pct:
        role = "10%+ Owner"
    else:
        role = "Insider"

    results = []
    for tx in root.findall(".//nonDerivativeTransaction"):
        code = _text(tx, "transactionCode") or ""
        if code not in ("P", "S"):
            continue

        tx_date    = _text(tx, "transactionDate") or file_date
        shares_str = _text(tx, "transactionShares") or "0"
        price_str  = _text(tx, "transactionPricePerShare") or "0"

        try:
            shares = float(shares_str)
            price  = float(price_str)
        except ValueError:
            continue

        if price <= 0 or shares <= 0:
            continue

        amount = round(shares * price, 2)
        if amount < 10_000:      # skip tiny transactions (< $10k)
            continue

        results.append({
            "trader_name":      insider,
            "insider_cik":      insider_cik,
            "trader_role":      role,
            "company":          company,
            "ticker":           ticker,
            "transaction_type": "buy" if code == "P" else "sell",
            "trade_date":       tx_date,
            "disclosure_date":  file_date,
            "amount_est":       amount,
            "amount_str":       f"${amount:,.0f}",
            "shares":           shares,
            "price_per_share":  price,
            "chamber":          "Corporate Insider",
        })

    return results


# ── Process one EDGAR hit ──────────────────────────────────────────────────────

def _process_hit(hit: dict) -> list[dict]:
    src    = hit.get("_source", {})
    id_str = hit.get("_id", "")

    if ":" not in id_str:
        return []

    adsh, filename = id_str.rsplit(":", 1)
    if not filename.endswith(".xml"):
        return []

    ciks      = src.get("ciks", [])
    file_date = src.get("file_date", "")

    # Try reversed order first (company CIK tends to be last for Form 4)
    xml = _fetch_xml(adsh, list(reversed(ciks)) + ciks, filename)
    if not xml:
        return []

    return _parse_xml(xml, file_date)


# ── Public API ─────────────────────────────────────────────────────────────────

def fetch_recent(
    limit: int = 50,
    on_refresh: Optional[Callable[[list[dict]], None]] = None,
) -> list[dict]:
    """
    Up to `limit` recent insider buy/sell transactions, **without blocking**.

    Safe to call from a request handler: it answers from the 15-minute cache and
    schedules the crawl in the background if that cache is cold or stale. A
    caller that arrives before the first crawl finishes gets an empty list —
    ``is_warming()`` distinguishes that from "EDGAR returned nothing", so the API
    can say which. Background callers that genuinely need the data should use
    ``refresh_recent_now()`` instead.

    ``on_refresh`` fires on the background thread when a scheduled crawl lands;
    see ``_cache_first``.
    """
    key = f"recent:{limit}"
    return _cache_first(key, lambda: _crawl_recent(limit), on_refresh)


def refresh_recent_now(limit: int = 50) -> list[dict]:
    """
    Blocking crawl for callers that are **not** request threads (the auto-trader
    loop runs on its own thread and cannot act without the data). Returns the
    cached copy when it is fresh, so a busy loop still costs one crawl per TTL.
    """
    key = f"recent:{limit}"
    fresh = _cached(key)
    if fresh is not None:
        return fresh
    if not _claim_refresh(key):
        # Someone else is already crawling, or we crawled very recently and
        # failed. Do not pile on; last-known-good is the honest answer.
        return _stale(key) or []
    return _run_refresh(key, lambda: _crawl_recent(limit))


def is_warming(limit: Optional[int] = None, ticker: Optional[str] = None) -> bool:
    """True when we have never successfully cached this key (empty != no data)."""
    key = f"recent:{limit}" if ticker is None else f"ticker:{ticker.upper()}"
    return key not in _cache


def _crawl_recent(limit: int) -> list[dict]:
    # Over-fetch hits because many filings have no P/S transactions
    search_limit = min(limit * 4, 120)
    hits = _search(days_back=14, limit=search_limit)

    results: list[dict] = []

    # 2 concurrent workers with small delay — SEC limit is 10 req/s
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = []
        for hit in hits:
            futures.append(pool.submit(_process_hit, hit))
            time.sleep(0.15)   # ~6-7 req/s across 2 workers
        for fut in as_completed(futures):
            try:
                results.extend(fut.result())
            except Exception as exc:
                logger.debug("Hit processing error: %s", exc)

    # Sort, deduplicate, limit
    results.sort(key=lambda x: x.get("disclosure_date", ""), reverse=True)

    seen: set[tuple] = set()
    deduped: list[dict] = []
    for r in results:
        key = (r["trader_name"], r["ticker"], r["trade_date"], r["transaction_type"])
        if key not in seen:
            seen.add(key)
            deduped.append(r)

    data = deduped[:limit]
    logger.info("EDGAR: %d Form 4 transactions fetched", len(data))
    return data


def fetch_for_ticker(
    ticker: str,
    on_refresh: Optional[Callable[[list[dict]], None]] = None,
) -> list[dict]:
    """
    Recent Form 4 transactions for one ticker, **without blocking** — same
    cache-first contract as ``fetch_recent``.
    """
    sym = ticker.upper()
    return _cache_first(f"ticker:{sym}", lambda: _crawl_for_ticker(sym), on_refresh)


def _crawl_for_ticker(ticker: str) -> list[dict]:
    hits = _search(days_back=90, limit=60)

    results: list[dict] = []
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(_process_hit, hit) for hit in hits]
        for fut in as_completed(futures):
            try:
                results.extend(t for t in fut.result() if t.get("ticker") == ticker.upper())
            except Exception:
                pass

    results.sort(key=lambda x: x.get("disclosure_date", ""), reverse=True)
    return results
