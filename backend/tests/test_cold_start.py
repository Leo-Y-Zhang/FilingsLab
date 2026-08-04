"""
The cold disclosure feed must converge in seconds, and say so honestly
=====================================================================
Round 2 took the EDGAR crawl and the per-row enrichment off the request thread,
which was right, and then described the result as "a few seconds on a cold
start", which was not. The review measured what a lone visitor actually
experiences:

    request 1  -> schedules the EDGAR crawl, returns warming
    (nothing pulls again until the client's next poll: 5 minutes)
    request 2  -> raw filings are cached; schedules enrichment, returns warming
    (5 more minutes)
    request 3  -> data

About ten minutes, for work that takes well under a minute. Two separate
defects were hiding behind the honest-sounding "warming" flag:

  1. **A missing link in the chain.** Nothing connected the end of the EDGAR
     crawl to the start of the enrichment, so the second stage could only ever
     begin on the *next* inbound request. The stages are now chained in the
     background, which removes one whole poll interval from the cold path.

  2. **A poll interval sized for the steady state.** Five minutes is right for
     a 15-minute cache; it is absurd while warming. The warming response now
     carries the interval the client should use, and the client honours it.

Neither is fixed by putting the crawl back on the request thread — that was the
original defect and these tests still forbid it.
"""
from __future__ import annotations

import os
import threading
import time

import pytest

os.environ.setdefault("API_TOKEN", "test-token-not-a-real-secret")

from fastapi.testclient import TestClient  # noqa: E402

from app.api import feed as feed_api  # noqa: E402
from app.core.database import get_db  # noqa: E402
from app.core.limiter import limiter  # noqa: E402
from app.main import app  # noqa: E402
from app.services import edgar  # noqa: E402


class _FakeSession:
    def close(self) -> None:  # pragma: no cover - trivial
        pass


def _fake_db():
    yield _FakeSession()


def _settle(timeout: float = 20.0) -> None:
    """Wait for every background stage — the crawl AND anything it chained."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not edgar._inflight and not feed_api._enrich_inflight:
            # One more pass: the crawl releases its slot before a chained job is
            # visible, so a single empty reading is not proof of quiescence.
            time.sleep(0.05)
            if not edgar._inflight and not feed_api._enrich_inflight:
                return
        time.sleep(0.02)
    raise AssertionError("background work did not finish within the timeout")


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setattr(
        edgar.httpx,
        "get",
        lambda *a, **k: pytest.fail("a test reached the real network"),
    )
    edgar._cache.clear()
    edgar._last_attempt.clear()
    feed_api.reset_enrichment_state()
    app.dependency_overrides[get_db] = _fake_db
    limiter.reset()
    yield TestClient(app, raise_server_exceptions=False)
    _settle()
    app.dependency_overrides.clear()
    limiter.reset()
    edgar._cache.clear()
    edgar._last_attempt.clear()
    feed_api.reset_enrichment_state()


def _row(ticker: str) -> dict:
    return {
        "trader_name": "An Insider",
        "ticker": ticker,
        "trade_date": "2026-07-30",
        "disclosure_date": "2026-08-01",
        "transaction_type": "buy",
    }


def _stub_pipeline(monkeypatch) -> None:
    """A working upstream: one filing, enriched instantly, no network."""
    monkeypatch.setattr(
        edgar,
        "_search",
        lambda days_back, limit: [
            {"_id": "000-1:doc.xml", "_source": {"ciks": ["1"], "file_date": "2026-08-01"}}
        ],
    )
    monkeypatch.setattr(edgar, "_process_hit", lambda hit: [_row("AAPL")])
    monkeypatch.setattr(
        feed_api,
        "_enrich",
        lambda rows: [{**r, "score": 90.0, "action": "buy"} for r in rows],
    )


def _stub_slow_empty_crawl(monkeypatch) -> None:
    """
    A crawl that is still running when the response is written, which is what
    "warming" means. A crawl that finishes instantly would race the assertion:
    the background thread can populate the cache before the handler reads it.
    """
    monkeypatch.setattr(edgar, "_search", lambda days_back, limit: (time.sleep(0.3), [])[1])
    monkeypatch.setattr(edgar, "_process_hit", lambda hit: [])


# ── 1. one poll interval removed from the cold path ───────────────────────────

def test_a_cold_visitor_gets_data_on_the_second_request(client, monkeypatch):
    """
    The measurement the review made, as a test. Pre-fix the second request was
    still warming and only the THIRD carried data, which at a 5-minute poll is
    the ten minutes reported.
    """
    _stub_pipeline(monkeypatch)

    first = client.get("/api/feed/disclosures?limit=25").json()
    assert first["count"] == 0 and first["warming"] is True

    # Everything the first request set in motion, including whatever it chained.
    _settle()

    second = client.get("/api/feed/disclosures?limit=25").json()
    assert second["warming"] is False, (
        "the second request was still warming: the EDGAR crawl finished but "
        "nothing started the enrichment, so a third request is needed"
    )
    assert second["count"] == 1
    assert second["disclosures"][0]["ticker"] == "AAPL"


def test_the_chained_enrichment_still_never_runs_on_the_request_thread(client, monkeypatch):
    """
    Chaining the stages must not quietly put stage two back on the caller. The
    fix for the ten minutes is not allowed to reintroduce the original defect.
    """
    _stub_pipeline(monkeypatch)
    threads: list[str] = []

    def _slow_enrich(rows):
        threads.append(threading.current_thread().name)
        time.sleep(0.4)
        return [{**r, "score": 90.0, "action": "buy"} for r in rows]

    monkeypatch.setattr(feed_api, "_enrich", _slow_enrich)

    started = time.perf_counter()
    client.get("/api/feed/disclosures?limit=25")
    first_elapsed = time.perf_counter() - started

    _settle()

    started = time.perf_counter()
    r = client.get("/api/feed/disclosures?limit=25")
    second_elapsed = time.perf_counter() - started

    assert first_elapsed < 0.3, f"the first request blocked for {first_elapsed:.2f}s"
    assert second_elapsed < 0.3, f"the second request blocked for {second_elapsed:.2f}s"
    assert r.json()["count"] == 1
    assert threads and "MainThread" not in threads[0], (
        f"enrichment ran on the request thread: {threads}"
    )


# ── 2. the client is told how long, and how often to ask ──────────────────────

def test_the_warming_response_carries_a_retry_interval(client, monkeypatch):
    _stub_slow_empty_crawl(monkeypatch)

    r = client.get("/api/feed/disclosures?limit=25")
    body = r.json()

    assert body["warming"] is True
    hint = body.get("retry_after_seconds")
    assert isinstance(hint, int), (
        "a warming response with no retry hint leaves the client on its "
        f"steady-state 5-minute poll; body was {body}"
    )
    # Fast enough that a lone visitor converges in seconds, slow enough to stay
    # well inside the public 10/minute budget for this route.
    assert 6 <= hint <= 60, f"retry hint of {hint}s is outside the usable range"
    # The hint deliberately does NOT go on Retry-After: slowapi already writes
    # that header on every response from a limited route, where it carries the
    # rate-limit window. Reusing the name for the warm-up interval would put two
    # different quantities under one field and throw away the back-off signal
    # app/core/limiter.py exists to preserve.
    assert r.headers.get("Retry-After") == "60", (
        "the limiter's own rate-limit window signal was overwritten; headers "
        f"were {dict(r.headers)}"
    )


def test_the_warming_message_does_not_promise_a_few_seconds(client, monkeypatch):
    """
    The user-visible half of the same defect. "A few seconds" was measured at
    about ten minutes; a status message that under-promises the wait by two
    orders of magnitude is worse than no message, because the visitor concludes
    the app is broken and leaves.
    """
    _stub_slow_empty_crawl(monkeypatch)

    message = client.get("/api/feed/disclosures?limit=25").json()["message"].lower()

    assert "a few seconds" not in message, f"still promising seconds: {message!r}"
    assert "minute" in message, (
        f"the message gives the visitor no idea of the real wait: {message!r}"
    )


def test_a_settled_feed_is_not_told_to_poll_fast(client, monkeypatch):
    """The fast poll belongs to the warming state only."""
    _stub_pipeline(monkeypatch)

    client.get("/api/feed/disclosures?limit=25")
    _settle()

    r = client.get("/api/feed/disclosures?limit=25")
    body = r.json()
    assert body["warming"] is False
    assert body.get("retry_after_seconds") is None, (
        "a warm feed asked the client to keep polling every few seconds"
    )
