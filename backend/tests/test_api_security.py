"""
API security regression tests
=============================
Each test here corresponds to a confirmed audit finding. They are written to
fail against the pre-fix code:

  1. unauthenticated resource exhaustion on GET /api/feed/disclosures
     (unbounded distinct cache keys + ~18 s of in-request sleeping per miss)
  2. negative `notional` on POST /api/feed/execute fabricating account cash
  3. no authentication on the auto-trader / paper-broker control surface
  4. no request-level detection (no request id, no client IP in the log)
"""
from __future__ import annotations

import os

# Must be set before app.core.config is imported anywhere.
os.environ["API_TOKEN"] = "test-token-not-a-real-secret"

import pytest
from fastapi.testclient import TestClient

from app.api import feed as feed_api
from app.core.config import get_settings
from app.core.database import get_db
from app.main import app
from app.services import auto_trader as at
from app.services import edgar
from app.services import paper_broker as pb

TOKEN = os.environ["API_TOKEN"]
AUTH = {"Authorization": f"Bearer {TOKEN}"}


class _FakeSession:
    """Stands in for a SQLAlchemy session; every route under test is stubbed."""

    def close(self) -> None:  # pragma: no cover - trivial
        pass


def _fake_db():
    yield _FakeSession()


@pytest.fixture()
def client():
    app.dependency_overrides[get_db] = _fake_db
    get_settings.cache_clear()
    limiter = getattr(app.state, "limiter", None)
    if limiter is not None:
        limiter.reset()
    # NOT used as a context manager on purpose: entering it would run the
    # lifespan, which starts the background seeder and the auto-trader thread.
    yield TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.clear()


# ── 1. Resource exhaustion ────────────────────────────────────────────────────

def test_every_limit_maps_into_a_small_fixed_set_of_cache_buckets():
    """N=1..200 must not produce 200 distinct upstream fetches / cache keys."""
    buckets = {feed_api._bucket_limit(n) for n in range(1, 201)}
    assert buckets <= {25, 50, 100, 200}
    assert len(buckets) <= 4


def test_requested_limit_is_bucketed_before_it_reaches_edgar(client, monkeypatch):
    seen: list[int] = []

    def _fetch(limit: int, on_refresh=None):
        seen.append(limit)
        return []

    monkeypatch.setattr(edgar, "fetch_recent", _fetch)
    for n in (1, 7, 26, 51, 101):
        client.get(f"/api/feed/disclosures?limit={n}")
    assert seen == [25, 25, 50, 100, 200]


def test_unauthenticated_disclosure_flood_is_rate_limited(client, monkeypatch):
    monkeypatch.setattr(edgar, "fetch_recent", lambda limit, on_refresh=None: [])
    codes = [
        client.get(f"/api/feed/disclosures?limit={n}").status_code
        for n in range(1, 41)
    ]
    assert 429 in codes, "an unauthenticated loop was never rate limited"


def test_per_ticker_feed_rejects_junk_symbols(client):
    """Arbitrary path segments are arbitrary cache keys and EDGAR searches."""
    r = client.get("/api/feed/disclosures/" + "A" * 300)
    assert r.status_code == 422


# ── 2. Numeric bounds ─────────────────────────────────────────────────────────

def test_negative_notional_is_rejected(client):
    r = client.post(
        "/api/feed/execute",
        json={"ticker": "AAPL", "side": "buy", "notional": -1_000_000},
        headers=AUTH,
    )
    assert r.status_code == 422


def test_zero_and_absurd_notional_are_rejected(client):
    for bad in (0, 1e12):
        r = client.post(
            "/api/feed/execute",
            json={"ticker": "AAPL", "side": "buy", "notional": bad},
            headers=AUTH,
        )
        assert r.status_code == 422, f"notional={bad} was accepted"


def test_negative_qty_is_rejected(client):
    r = client.post(
        "/api/feed/execute",
        json={"ticker": "AAPL", "side": "sell", "qty": -5},
        headers=AUTH,
    )
    assert r.status_code == 422


@pytest.mark.parametrize(
    "payload",
    [
        {"run_interval_mins": 0},        # busy-loops the background thread
        {"run_interval_mins": -30},      # time.sleep(negative) raises
        {"max_positions": -5},
        {"max_position_pct": -1},
        {"max_position_pct": 100_000},
        {"min_score": 5_000},
        {"stop_loss_pct": -10},
        {"take_profit_pct": 0},
    ],
)
def test_auto_trader_config_rejects_out_of_range_numbers(client, payload):
    r = client.post("/api/feed/auto-trader/config", json=payload, headers=AUTH)
    assert r.status_code == 422, f"{payload} was accepted"


def test_auto_trader_log_limit_cannot_be_negative(client):
    r = client.get("/api/feed/auto-trader/log?limit=-1", headers=AUTH)
    assert r.status_code == 422


def test_alpha_decay_delay_list_is_bounded(client):
    r = client.get("/api/research/alpha-decay/1?delays=" + ",".join(["1"] * 500))
    assert r.status_code == 422

    r = client.get("/api/research/alpha-decay/1?delays=99999")
    assert r.status_code == 422


# ── 3. Authentication ─────────────────────────────────────────────────────────

MUTATING_ROUTES = [
    ("get", "/api/feed/auto-trader/config", None),
    ("post", "/api/feed/auto-trader/config", {"enabled": True}),
    ("post", "/api/feed/auto-trader/run", None),
    ("get", "/api/feed/auto-trader/log", None),
    ("post", "/api/feed/execute", {"ticker": "AAPL", "side": "buy", "notional": 100}),
    ("delete", "/api/feed/position/AAPL", None),
    ("get", "/api/feed/portfolio", None),
    ("get", "/api/feed/broker/status", None),
]


@pytest.mark.parametrize("method,path,body", MUTATING_ROUTES)
def test_control_surface_rejects_anonymous_callers(client, method, path, body):
    r = getattr(client, method)(path, **({"json": body} if body else {}))
    assert r.status_code == 401, f"{method.upper()} {path} was open"


@pytest.mark.parametrize("method,path,body", MUTATING_ROUTES)
def test_control_surface_rejects_a_wrong_token(client, method, path, body):
    kwargs = {"headers": {"Authorization": "Bearer wrong-token"}}
    if body:
        kwargs["json"] = body
    r = getattr(client, method)(path, **kwargs)
    assert r.status_code == 401, f"{method.upper()} {path} accepted a bad token"


def test_correct_token_is_accepted(client, monkeypatch):
    monkeypatch.setattr(at, "update_config", lambda db, **kw: _Cfg())
    r = client.post(
        "/api/feed/auto-trader/config", json={"enabled": False}, headers=AUTH
    )
    assert r.status_code == 200
    assert r.json() == {"saved": True, "enabled": False}


class _Cfg:
    enabled = False


def test_admin_surface_fails_closed_when_no_token_is_configured(client, monkeypatch):
    monkeypatch.delenv("API_TOKEN", raising=False)
    get_settings.cache_clear()
    try:
        r = client.post("/api/feed/auto-trader/run", headers=AUTH)
        assert r.status_code == 503, "an unconfigured server left the admin API open"
    finally:
        monkeypatch.setenv("API_TOKEN", TOKEN)
        get_settings.cache_clear()


def test_read_only_research_surface_stays_open(client):
    r = client.get("/api/health")
    assert r.status_code == 200


# ── 4. Detection ──────────────────────────────────────────────────────────────

def test_every_response_carries_a_request_id(client):
    r = client.get("/api/health")
    assert r.headers.get("x-request-id")


def test_request_log_records_id_path_status_and_client_ip(client, caplog):
    with caplog.at_level("INFO", logger="app.request"):
        r = client.get("/api/health")
    line = "\n".join(rec.getMessage() for rec in caplog.records)
    assert r.headers["x-request-id"] in line
    assert "/api/health" in line
    assert "status=200" in line
    assert "client_ip=" in line


def test_failed_auth_is_logged_as_a_warning(client, caplog):
    with caplog.at_level("WARNING", logger="app.security"):
        client.post("/api/feed/auto-trader/run", headers={"Authorization": "Bearer nope"})
    assert any("auth_failed" in rec.getMessage() for rec in caplog.records)


def _request(peer: str, headers: dict[str, str]):
    from starlette.requests import Request

    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "query_string": b"",
            "scheme": "http",
            "server": ("test", 80),
            "client": (peer, 40000),
            "headers": [
                (k.lower().encode(), v.encode()) for k, v in headers.items()
            ],
        }
    )


def test_rate_limit_key_ignores_forwarded_headers_from_an_untrusted_peer():
    """Otherwise a spoofed X-Forwarded-For gives an attacker unlimited buckets."""
    from app.core.limiter import client_key

    req = _request("203.0.113.9", {"X-Forwarded-For": "1.2.3.4", "X-Real-IP": "5.6.7.8"})
    assert client_key(req) == "203.0.113.9"


def test_rate_limit_key_uses_the_real_ip_from_a_trusted_proxy():
    from app.core.limiter import client_key

    req = _request("172.18.0.3", {"X-Forwarded-For": "1.2.3.4, 198.51.100.7", "X-Real-IP": "198.51.100.7"})
    assert client_key(req) == "198.51.100.7"


def test_paper_broker_module_is_importable():
    """Guard against the security refactor breaking the broker import graph."""
    assert hasattr(pb, "execute_trade")
