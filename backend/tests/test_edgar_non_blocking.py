"""
The disclosure feed must not block a request thread on SEC EDGAR
===============================================================
The original exhaustion finding was only half fixed. Round 1 bucketed the cache
key so at most four distinct upstream fetches could exist, but a *miss* still
ran the whole upstream crawl inside the request handler: ``fetch_recent``
submits up to 120 archive jobs and calls ``time.sleep(0.15)`` between each one,
on the anyio worker thread FastAPI borrowed to run the sync endpoint.

anyio's default threadpool is 40 workers. Forty concurrent misses and the
process serves nothing at all — not the health check, not the research routes —
for the best part of twenty seconds, from callers who never exceeded their own
rate limit. The limiter cannot close this on its own: 10/minute across ~14
source IPs is enough.

Two properties make it safe, and both were watched failing against the pre-fix
module:

  1. the call the request handler makes returns promptly on a cold cache
  2. concurrent cold callers cause ONE upstream crawl, not one each

The helpers below read module internals through ``getattr`` defaults so the
tests are meaningful against the pre-fix code too (which had no background
refresh state at all, and for which "wait for refreshes" is a no-op).
"""
from __future__ import annotations

import threading
import time

import pytest

from app.services import edgar


def _reset_edgar_state() -> None:
    edgar._cache.clear()
    getattr(edgar, "_last_attempt", {}).clear()


def _settle(timeout: float = 20.0) -> None:
    """
    Block until no background refresh is in flight. Tests must never abandon a
    live crawl: monkeypatched stubs are undone at test exit, so a thread still
    running afterwards would fall through to the real SEC endpoints.
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not getattr(edgar, "_inflight", ()):
            return
        time.sleep(0.02)
    raise AssertionError("background refresh did not finish within the timeout")


@pytest.fixture(autouse=True)
def _clean_edgar_state(monkeypatch):
    """
    Takes ``monkeypatch`` as an argument on purpose: that makes monkeypatch set
    up FIRST, so this fixture's teardown (which waits for background crawls)
    runs BEFORE the stubs are undone. Without that ordering a still-running
    refresh thread falls through to the real ``_search``/``_process_hit`` and
    goes out to sec.gov — which is both flaky and rude.
    """
    monkeypatch.setattr(
        edgar.httpx,
        "get",
        lambda *a, **k: pytest.fail("a test reached the real network"),
    )
    _reset_edgar_state()
    yield
    _settle()
    _reset_edgar_state()


def _fake_hits(n: int) -> list[dict]:
    return [
        {"_id": f"000-{i}:doc.xml", "_source": {"ciks": ["1"], "file_date": "2026-08-01"}}
        for i in range(n)
    ]


def _row(ticker: str) -> dict:
    return {
        "trader_name": "An Insider",
        "ticker": ticker,
        "trade_date": "2026-07-30",
        "disclosure_date": "2026-08-01",
        "transaction_type": "buy",
    }


def test_cold_fetch_recent_returns_promptly_instead_of_sleeping_in_request(monkeypatch):
    """Pre-fix this took ~18 s: time.sleep(0.15) once per archive job, inline."""
    # 20 archive jobs paced 0.15 s apart is 3 s of crawl; the production path
    # allows 120 of them, which is the ~18 s the audit measured.
    monkeypatch.setattr(edgar, "_search", lambda days_back, limit: _fake_hits(20))
    monkeypatch.setattr(edgar, "_process_hit", lambda hit: [])

    started = time.perf_counter()
    out = edgar.fetch_recent(limit=50)
    elapsed = time.perf_counter() - started

    assert out == []
    assert elapsed < 0.5, f"fetch_recent blocked its caller for {elapsed:.1f}s"


def test_cold_fetch_for_ticker_returns_promptly(monkeypatch):
    monkeypatch.setattr(edgar, "_search", lambda days_back, limit: _fake_hits(40))
    # Each hit is an archive fetch over the network; 60 of them across 2 pool
    # workers is seconds of wall clock the caller must not be made to wait for.
    monkeypatch.setattr(edgar, "_process_hit", lambda hit: (time.sleep(0.05), [])[1])

    started = time.perf_counter()
    out = edgar.fetch_for_ticker("AAPL")
    elapsed = time.perf_counter() - started

    assert out == []
    assert elapsed < 0.5, f"fetch_for_ticker blocked its caller for {elapsed:.1f}s"


def test_concurrent_cold_callers_cause_one_upstream_crawl(monkeypatch):
    """
    Pre-fix, N simultaneous misses were N simultaneous EDGAR crawls — the
    amplification a per-IP rate limit cannot close.
    """
    searches: list[int] = []
    lock = threading.Lock()

    def _slow_search(days_back, limit):
        with lock:
            searches.append(limit)
        time.sleep(0.4)
        return []

    monkeypatch.setattr(edgar, "_search", _slow_search)
    monkeypatch.setattr(edgar, "_process_hit", lambda hit: [])

    threads = [threading.Thread(target=lambda: edgar.fetch_recent(limit=50)) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    _settle()
    assert len(searches) == 1, f"8 callers produced {len(searches)} upstream crawls"


def test_background_refresh_populates_the_cache_for_the_next_caller(monkeypatch):
    """A prompt return is only acceptable if the data does actually arrive."""
    monkeypatch.setattr(edgar, "_search", lambda days_back, limit: _fake_hits(3))
    monkeypatch.setattr(edgar, "_process_hit", lambda hit: [_row("AAPL")])

    assert edgar.fetch_recent(limit=50) == [], "a cold call should not wait for EDGAR"
    _settle()

    later = edgar.fetch_recent(limit=50)
    assert len(later) == 1 and later[0]["ticker"] == "AAPL"


def test_a_failed_refresh_is_not_retried_on_every_request(monkeypatch):
    """Otherwise an EDGAR outage turns every allowed request into a fresh crawl."""
    attempts: list[int] = []

    def _boom(days_back, limit):
        attempts.append(limit)
        raise RuntimeError("EDGAR unavailable")

    monkeypatch.setattr(edgar, "_search", _boom)

    for _ in range(6):
        assert edgar.fetch_recent(limit=50) == []
        _settle()

    assert len(attempts) == 1, f"{len(attempts)} crawls attempted after one failure"


def test_stale_data_is_served_while_a_refresh_runs(monkeypatch):
    monkeypatch.setattr(edgar, "_search", lambda days_back, limit: _fake_hits(1))
    monkeypatch.setattr(edgar, "_process_hit", lambda hit: [_row("OLD")])

    edgar.fetch_recent(limit=50)
    _settle()
    assert edgar.fetch_recent(limit=50)[0]["ticker"] == "OLD"

    # Age the entry past its TTL, then make the next crawl slow.
    key = "recent:50"
    stamp, data = edgar._cache[key]
    edgar._cache[key] = (stamp - edgar._CACHE_TTL - 1, data)
    getattr(edgar, "_last_attempt", {}).clear()
    monkeypatch.setattr(edgar, "_search", lambda days_back, limit: (time.sleep(0.4), _fake_hits(1))[1])
    monkeypatch.setattr(edgar, "_process_hit", lambda hit: [_row("NEW")])

    started = time.perf_counter()
    served = edgar.fetch_recent(limit=50)
    elapsed = time.perf_counter() - started

    assert elapsed < 0.3, f"a stale cache still made the caller wait {elapsed:.1f}s"
    assert served and served[0]["ticker"] == "OLD", "a stale but usable feed was dropped"

    _settle()
    assert edgar.fetch_recent(limit=50)[0]["ticker"] == "NEW"


def test_the_auto_trader_still_gets_data_synchronously(monkeypatch):
    """
    The background auto-trader loop is not a request thread and does need the
    data before it can decide anything, so it keeps a blocking entry point.
    """
    monkeypatch.setattr(edgar, "_search", lambda days_back, limit: _fake_hits(2))
    monkeypatch.setattr(edgar, "_process_hit", lambda hit: [_row("MSFT")])

    out = edgar.refresh_recent_now(limit=60)
    assert len(out) == 1 and out[0]["ticker"] == "MSFT"


# ── The same bug class, one layer up ──────────────────────────────────────────
# Fixing the EDGAR crawl is not enough on its own. Once the raw filings are
# cached, `_enrich` still runs per disclosure, and per disclosure it calls
# yfinance twice (`_current_price`, `_volume_ratio`) and Kronos once — up to 200
# rows, so up to 600 network calls, on the same anyio worker the crawl used to
# occupy. A cached feed that then blocks on enrichment has moved the stall, not
# removed it.

import os

os.environ.setdefault("API_TOKEN", "test-token-not-a-real-secret")

from fastapi.testclient import TestClient  # noqa: E402

from app.api import feed as feed_api  # noqa: E402
from app.core.database import get_db  # noqa: E402
from app.core.limiter import limiter  # noqa: E402
from app.main import app  # noqa: E402


class _FakeSession:
    def close(self) -> None:  # pragma: no cover - trivial
        pass


def _fake_db():
    yield _FakeSession()


@pytest.fixture()
def client():
    app.dependency_overrides[get_db] = _fake_db
    limiter.reset()
    if hasattr(feed_api, "reset_enrichment_state"):
        feed_api.reset_enrichment_state()
    yield TestClient(app, raise_server_exceptions=False)
    _settle_enrichment()
    app.dependency_overrides.clear()
    limiter.reset()
    if hasattr(feed_api, "reset_enrichment_state"):
        feed_api.reset_enrichment_state()


def _settle_enrichment(timeout: float = 20.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not getattr(feed_api, "_enrich_inflight", ()):
            return
        time.sleep(0.02)
    raise AssertionError("background enrichment did not finish within the timeout")


def test_enrichment_does_not_run_on_the_request_thread(client, monkeypatch):
    monkeypatch.setattr(edgar, "fetch_recent", lambda limit, on_refresh=None: [_row("AAPL")])

    threads: list[str] = []

    def _slow_enrich(rows):
        threads.append(threading.current_thread().name)
        time.sleep(0.5)
        return [{**r, "score": 90.0, "action": "buy"} for r in rows]

    monkeypatch.setattr(feed_api, "_enrich", _slow_enrich)

    started = time.perf_counter()
    r = client.get("/api/feed/disclosures?limit=25")
    elapsed = time.perf_counter() - started

    assert r.status_code == 200, r.text
    assert elapsed < 0.3, f"the request waited {elapsed:.1f}s for yfinance and Kronos"
    assert r.json()["warming"] is True

    _settle_enrichment()
    assert threads and "MainThread" not in threads[0]

    later = client.get("/api/feed/disclosures?limit=25")
    assert later.status_code == 200
    body = later.json()
    assert body["count"] == 1
    assert body["disclosures"][0]["ticker"] == "AAPL"
    assert body["warming"] is False
