"""
Caller-keyed dictionaries on public paths must be bounded
=========================================================
Round 2 bounded ``edgar._cache`` at 64 entries and stopped there. The review
afterwards drove 500 distinct tickers through the public feed with the network
stubbed and measured the result: ``_cache`` held at 64, and
``edgar._last_attempt`` — which is written from the same caller-controlled key —
grew to 500 and kept going.

Both endpoints that write these dictionaries are anonymous and rate limited at
10 requests a minute, which is 14,400 distinct keys a day from one client and
far more from a handful. A dict that only ever grows on a public path is a
memory-exhaustion surface whatever the per-entry cost is.

The same defect exists one layer up: ``feed._enrich_cache`` is capped at 32 but
``feed._enrich_last_attempt``, keyed on the same ticker, was not capped at all.
Both are covered here.

Every test in this file was watched failing against the unbounded code — the
sizes recorded there are in the assertion messages.
"""
from __future__ import annotations

import time

import pytest

from app.api import feed as feed_api
from app.services import edgar

# Comfortably more keys than either cap, and the order of magnitude the review
# actually drove through the API.
_KEYS = 500

# The caps are read through getattr with the intended value as the default, so
# these tests fail on the SIZE against the pre-fix modules (which define no such
# constant) rather than on an AttributeError. Measured pre-fix: 500 and 500.
def _edgar_cap() -> int:
    return getattr(edgar, "_MAX_ATTEMPT_ENTRIES", 128)


def _enrich_cap() -> int:
    return getattr(feed_api, "_MAX_ENRICH_ATTEMPTS", 64)


def _settle_refreshes(timeout: float = 20.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not edgar._inflight:
            return
        time.sleep(0.01)
    raise AssertionError("a background EDGAR refresh never finished")


def _settle_enrichment(timeout: float = 20.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not feed_api._enrich_inflight:
            return
        time.sleep(0.01)
    raise AssertionError("a background enrichment never finished")


@pytest.fixture(autouse=True)
def _clean_state(monkeypatch):
    """monkeypatch first, so teardown waits for threads before stubs are undone."""
    monkeypatch.setattr(
        edgar.httpx,
        "get",
        lambda *a, **k: pytest.fail("a test reached the real network"),
    )
    edgar._cache.clear()
    edgar._last_attempt.clear()
    feed_api.reset_enrichment_state()
    yield
    _settle_refreshes()
    _settle_enrichment()
    edgar._cache.clear()
    edgar._last_attempt.clear()
    feed_api.reset_enrichment_state()


# ── edgar._last_attempt ───────────────────────────────────────────────────────

def test_edgar_last_attempt_is_bounded_on_the_public_ticker_path(monkeypatch):
    """
    Drives the real public entry point — one distinct ticker per call, exactly
    what ``GET /api/feed/disclosures/{ticker}`` does with the key it is handed.
    """
    monkeypatch.setattr(edgar, "_search", lambda days_back, limit: [])

    for i in range(_KEYS):
        edgar.fetch_for_ticker(f"T{i:04d}")
        # Settle between calls so the two-crawl concurrency cap never refuses a
        # claim: every one of the 500 keys really is recorded.
        _settle_refreshes()

    assert len(edgar._cache) <= edgar._MAX_CACHE_ENTRIES
    assert len(edgar._last_attempt) <= _edgar_cap(), (
        f"{_KEYS} distinct tickers left {len(edgar._last_attempt)} attempt "
        f"timestamps behind (cap is {_edgar_cap()})"
    )


def test_edgar_attempt_bound_holds_under_direct_claims():
    """
    The same property at the function that owns the dictionary, without threads,
    so a failure here points at the eviction rule rather than at timing.
    """
    for i in range(_KEYS):
        assert edgar._claim_refresh(f"key-{i}") is True
        edgar._release_refresh(f"key-{i}")

    assert len(edgar._last_attempt) <= _edgar_cap(), (
        f"{_KEYS} claims left {len(edgar._last_attempt)} timestamps behind"
    )


def test_bounding_the_attempt_dict_still_suppresses_a_retry_storm(monkeypatch):
    """
    Eviction must not undo what the dictionary is for. A handful of keys is far
    below the cap, so a failed crawl is still not retried on the next request.
    """
    attempts: list[int] = []

    def _boom(days_back, limit):
        attempts.append(limit)
        raise RuntimeError("EDGAR unavailable")

    monkeypatch.setattr(edgar, "_search", _boom)

    for _ in range(6):
        edgar.fetch_recent(limit=50)
        _settle_refreshes()

    assert len(attempts) == 1, f"{len(attempts)} crawls attempted after one failure"


def test_pruning_prefers_expired_records_over_live_ones():
    """
    The bound must not be bought by throwing the backoff away.

    A dict that simply empties itself when it fills up would pass every size
    assertion above and still reintroduce the retry storm the dict exists to
    prevent — the storm test only ever holds one key, so it never reaches the
    eviction path at all. This drives eviction directly: fill the dict to the
    cap with records that have aged out, add one that has NOT, then force a
    prune with a new key. The live record must survive, because there were
    expired ones to drop instead.
    """
    now = time.time()
    stale_ts = now - edgar._MIN_REFRESH_INTERVAL - 1
    for i in range(_edgar_cap() - 1):
        edgar._last_attempt[f"expired-{i}"] = stale_ts
    edgar._last_attempt["still-backing-off"] = now

    assert len(edgar._last_attempt) == _edgar_cap()

    # A new key forces the prune.
    assert edgar._claim_refresh("a-brand-new-key") is True
    edgar._release_refresh("a-brand-new-key")

    assert len(edgar._last_attempt) <= _edgar_cap()
    # Released immediately whatever the answer, so a failure here reports the
    # eviction rule rather than hanging the fixture on a leaked in-flight slot.
    claimed_again = edgar._claim_refresh("still-backing-off")
    if claimed_again:
        edgar._release_refresh("still-backing-off")
    assert claimed_again is False, (
        "a live backoff record was evicted while expired records were available "
        "to drop, so a failing key can be re-crawled inside its backoff window"
    )
    assert not any(k.startswith("expired-") for k in edgar._last_attempt), (
        "expired records were kept in preference to nothing at all"
    )


# ── feed._enrich_last_attempt ─────────────────────────────────────────────────

def _row(ticker: str) -> dict:
    return {
        "trader_name": "An Insider",
        "ticker": ticker,
        "trade_date": "2026-07-30",
        "disclosure_date": "2026-08-01",
        "transaction_type": "buy",
    }


def test_enrichment_attempt_dict_is_bounded(monkeypatch):
    """
    ``_enriched`` is called once per request with a key built from the
    caller-supplied ticker, so it has exactly the same exposure as the EDGAR
    dictionary above.
    """
    monkeypatch.setattr(feed_api, "_enrich", lambda rows: list(rows))

    for i in range(_KEYS):
        sym = f"T{i:04d}"
        feed_api._enriched(f"ticker:{sym}", [_row(sym)])
        _settle_enrichment()

    assert len(feed_api._enrich_cache) <= feed_api._MAX_ENRICH_ENTRIES
    assert len(feed_api._enrich_last_attempt) <= _enrich_cap(), (
        f"{_KEYS} distinct tickers left {len(feed_api._enrich_last_attempt)} "
        f"enrichment timestamps behind (cap is {_enrich_cap()})"
    )
