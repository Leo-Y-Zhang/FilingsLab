"""
Rate-limiting contract tests
============================
Round 1 hardened the API and broke it. The rate-limit tests that shipped with
it asserted only on internal state (which bucket a limit maps to) or on the
*presence of a 429* in a flood — never on the success path — so a change that
made every rate-limited endpoint answer HTTP 500 passed the whole suite.

These tests fix that hole. Three separate claims, each written against the
broken code and watched failing first:

  A. a rate-limited endpoint still answers 200 with its real body
     (``Limiter(headers_enabled=True)`` makes slowapi call ``_inject_headers``
     with ``kwargs.get("response")``, which raises unless the endpoint
     declares ``response: Response``)
  B. every ``@limiter.limit`` route declares that parameter, so the next
     endpoint someone decorates cannot reintroduce (A)
  C. the limit is scoped to the *route*, not to the concrete URL — slowapi
     defaults to ``key_style="url"``, which gives every distinct path segment
     its own bucket, so any path-parameterised route was unlimited
"""
from __future__ import annotations

import inspect
import os

# Must be set before app.core.config is imported anywhere.
os.environ.setdefault("API_TOKEN", "test-token-not-a-real-secret")

import pytest
from fastapi.testclient import TestClient

from app.core.database import get_db
from app.core.limiter import limiter
from app.main import app
from app.services import edgar


class _FakeSession:
    def close(self) -> None:  # pragma: no cover - trivial
        pass


def _fake_db():
    yield _FakeSession()


@pytest.fixture()
def client():
    app.dependency_overrides[get_db] = _fake_db
    limiter.reset()
    yield TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.clear()
    limiter.reset()


# ── A. the success path ───────────────────────────────────────────────────────

def test_rate_limited_endpoint_returns_200_and_a_real_body(client, monkeypatch):
    """
    The regression round 1 shipped: this endpoint answered 500 to every single
    caller, rate limited or not. Asserting the status AND the body is the point
    — a hardened endpoint that cannot serve a request is worse than an
    unhardened one.
    """
    monkeypatch.setattr(edgar, "fetch_recent", lambda limit, on_refresh=None: [])

    r = client.get("/api/feed/disclosures?limit=25")

    assert r.status_code == 200, f"rate-limited endpoint failed: {r.text[:200]}"
    body = r.json()
    assert body["configured"] is True
    assert body["count"] == 0
    assert body["disclosures"] == []


def test_rate_limited_path_parameter_endpoint_returns_200_and_a_real_body(client, monkeypatch):
    monkeypatch.setattr(edgar, "fetch_for_ticker", lambda ticker, on_refresh=None: [])

    r = client.get("/api/feed/disclosures/AAPL")

    assert r.status_code == 200, f"rate-limited endpoint failed: {r.text[:200]}"
    body = r.json()
    assert body["ticker"] == "AAPL"
    assert body["count"] == 0
    assert body["disclosures"] == []


def test_successful_response_carries_the_rate_limit_headers(client, monkeypatch):
    """
    Headers are the reason the limiter is configured with headers_enabled=True:
    they are the only place slowapi emits Retry-After, which is what lets a
    client back off instead of hammering. If they are gone, that decision was
    silently reversed.
    """
    monkeypatch.setattr(edgar, "fetch_recent", lambda limit, on_refresh=None: [])

    r = client.get("/api/feed/disclosures?limit=25")

    assert r.status_code == 200
    assert r.headers.get("x-ratelimit-limit") == "10"
    assert r.headers.get("x-ratelimit-remaining") is not None


def test_rate_limited_response_carries_retry_after(client, monkeypatch):
    monkeypatch.setattr(edgar, "fetch_recent", lambda limit, on_refresh=None: [])

    last = None
    for _ in range(15):
        last = client.get("/api/feed/disclosures?limit=25")

    assert last is not None and last.status_code == 429
    assert last.headers.get("retry-after") is not None


# ── B. no other endpoint can reintroduce the same 500 ─────────────────────────

def test_every_rate_limited_endpoint_declares_a_response_parameter():
    """
    slowapi's sync/async wrapper ends with
    ``self._inject_headers(kwargs.get("response"), ...)`` whenever headers are
    enabled, and ``_inject_headers`` raises on anything that is not a Response.
    So with headers enabled, a decorated endpoint without ``response: Response``
    is a guaranteed 500 on its success path. Catch that statically.
    """
    if not limiter._headers_enabled:
        pytest.skip("headers disabled; slowapi never touches kwargs['response']")

    missing = []
    for route in app.routes:
        endpoint = getattr(route, "endpoint", None)
        if endpoint is None:
            continue
        name = f"{endpoint.__module__}.{endpoint.__name__}"
        if name not in limiter._route_limits:
            continue
        if "response" not in inspect.signature(endpoint).parameters:
            missing.append(f"{name} ({getattr(route, 'path', '?')})")

    assert not missing, (
        "these @limiter.limit endpoints will raise on every successful call "
        "because slowapi has no Response to write headers into: " + ", ".join(missing)
    )


# ── C. the bucket is the route, not the URL ───────────────────────────────────

def test_rate_limit_is_not_bypassable_by_varying_the_path_parameter(client, monkeypatch):
    """
    With slowapi's default key_style="url" the bucket key is request["path"],
    so /api/feed/disclosures/AAA and /api/feed/disclosures/AAB were separate
    10/minute budgets. A caller with a wordlist had no limit at all.
    """
    monkeypatch.setattr(edgar, "fetch_for_ticker", lambda ticker, on_refresh=None: [])

    codes = [client.get(f"/api/feed/disclosures/SYM{n}").status_code for n in range(30)]

    assert codes[0] == 200, f"first call should succeed, got {codes[0]}"
    assert 429 in codes, "30 requests to 30 distinct tickers were never limited"
    # 10/minute: the eleventh distinct path onwards must be refused.
    assert codes[10] == 429, f"limit did not bite at the 11th request: {codes[:12]}"


def test_default_limit_is_not_bypassable_by_varying_the_path_parameter(client):
    """
    Same bug on the routes that have no explicit decorator and rely on the
    120/minute default applied by SlowAPIMiddleware. /api/traders/{id} is the
    enumerable one. The handler itself fails against the stub session; the
    limiter runs in middleware, before the handler, so the status that matters
    here is 429 vs not-429.
    """
    codes = [client.get(f"/api/traders/{n}").status_code for n in range(140)]

    assert 429 in codes, "140 requests to 140 distinct trader ids were never limited"
    assert codes[120] == 429, f"default limit did not bite at request 121: {codes[118:123]}"
