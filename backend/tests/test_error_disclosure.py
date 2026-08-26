"""
Error disclosure
================
Eight handlers turned an unexpected exception into
``HTTPException(500, f"...: {e}")``, so whatever the exception said went
straight to an anonymous caller. That text is not neutral: SQLAlchemy quotes
the failing statement and the column names back, yfinance quotes the URL it
called, and an ``AttributeError`` names the attribute of an internal object.
It is free reconnaissance, and none of it helps the caller, who cannot act on
any of it.

``app/api/feed.py`` already had the pattern the rest of the API should use --
``logger.exception(...)`` so the operator gets the traceback, a fixed string
so the caller gets nothing but the fact of the failure. These tests pin it on
every remaining site.

Each case drives the real route through TestClient with the one call that does
the work replaced by a raiser, and asserts the sentinel reaches the log and
never reaches the response body. Written against the pre-fix code and watched
failing first: all eight returned the sentinel verbatim.
"""
from __future__ import annotations

import os

# Must be set before app.core.config is imported anywhere.
os.environ.setdefault("API_TOKEN", "test-token-not-a-real-secret")

import pytest
from fastapi.testclient import TestClient

from app.core.database import get_db
from app.core.limiter import limiter
from app.main import app

# Shaped like a real SQLAlchemy failure, because that is the one an operator
# would actually hit: it names a table and a column that are not the caller's
# business.
SENTINEL = "OperationalError: no such column: trades.disclosure_dt"


class UnexpectedFailure(Exception):
    """
    Stands in for the class of exception nobody planned for, which is the only
    one at issue here. RuntimeError and ValueError are deliberately NOT used:
    ``/api/forecast/{symbol}`` maps those onto 503 and 422 with the message
    attached on purpose -- "Kronos is not set up", "no OHLCV data for AAA" --
    and those messages are the caller's business. Only the trailing
    ``except Exception`` leaked.
    """


def _boom(*args, **kwargs):
    raise UnexpectedFailure(SENTINEL)


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


# (dotted target to replace, method, path, request body)
CASES = [
    ("app.api.research.run_all_experiments",   "get",  "/api/research/experiments",     None),
    ("app.api.research.compute_alpha_decay",   "get",  "/api/research/alpha-decay/1",   None),
    ("app.api.research.test_h1_excess_returns", "get", "/api/research/hypothesis/h1",   None),
    ("app.api.research.test_h2_early_vs_late", "get",  "/api/research/hypothesis/h2",   None),
    ("app.api.simulation.sim_run",             "post", "/api/simulate/",                {"trader_id": 1}),
    ("app.api.simulation.run_monte_carlo",     "post", "/api/simulate/monte-carlo",     {"trader_id": 1, "n_runs": 10}),
    ("app.api.comparison.sim_run",             "post", "/api/compare/",                 {"trader_ids": [1, 2]}),
    ("app.kronos.service.get_forecast",        "get",  "/api/forecast/AAPL",            None),
]


@pytest.mark.parametrize(
    "target,method,path,body", CASES, ids=[f"{c[1]}:{c[2]}" for c in CASES]
)
def test_handler_does_not_return_the_exception_text(
    client, monkeypatch, target, method, path, body
):
    monkeypatch.setattr(target, _boom)

    r = getattr(client, method)(path, **({"json": body} if body else {}))

    assert r.status_code == 500, f"{path} answered {r.status_code}: {r.text[:200]}"
    assert SENTINEL not in r.text, f"{path} returned the exception text: {r.text[:200]}"
    assert "UnexpectedFailure" not in r.text
    assert "Traceback" not in r.text


@pytest.mark.parametrize(
    "target,method,path,body", CASES, ids=[f"{c[1]}:{c[2]}" for c in CASES]
)
def test_handler_still_says_something_useful(
    client, monkeypatch, target, method, path, body
):
    """
    A fixed string is only the right answer if it is still a string: replacing
    the leak with an empty detail, or with a bare 500 from Starlette's default
    error middleware, would pass the test above and leave the caller unable to
    tell a server fault from a bad request.
    """
    monkeypatch.setattr(target, _boom)

    r = getattr(client, method)(path, **({"json": body} if body else {}))

    detail = r.json().get("detail")
    assert isinstance(detail, str) and detail.strip(), f"{path} detail was {detail!r}"


def test_the_exception_reaches_the_server_log(client, monkeypatch, caplog):
    """The detail is not discarded, it is redirected: the operator still gets it."""
    monkeypatch.setattr("app.api.research.run_all_experiments", _boom)

    with caplog.at_level("ERROR"):
        r = client.get("/api/research/experiments")

    assert r.status_code == 500
    assert SENTINEL not in r.text
    assert SENTINEL in caplog.text, "the traceback was dropped instead of logged"
