"""
The auto-trader's Kronos input must not depend on its own HTTP rate limit
=========================================================================
``_kronos_expected_return`` used to fetch its forecast by calling the app's own
API back over the loopback: ``GET http://localhost:8000/api/forecast/{ticker}``.
That was survivable only while the rate-limit bucket key was the concrete URL,
because every ticker then had its own 10/minute budget.

Round 2 fixed a real enumeration hole by switching the limiter to
``key_style="endpoint"``, so the bucket is now (client IP, route template). The
loopback caller is one client IP hitting one route template, so the whole
auto-trader cycle shares a single 10/minute budget. Cycle 11 onwards got HTTP
429, the bare ``except Exception`` swallowed it, and ``None`` was returned.

``None`` is not an error here — it is a valid value meaning "no forecast", and
it disables the Kronos veto at ``auto_trader._run_cycle``. So a rate limit on an
internal call silently turned off a trading safety check. That is a
financial-correctness bug, not a rate-limit nuisance.

The fix is the one round 2 already identified as correct: call the forecaster
in-process. There is then no HTTP boundary, no limiter, and no budget to
exhaust. What is left of the failure path is made loud rather than silent.

Watched failing against the loopback implementation — the recorded results are
in the assertion messages.
"""
from __future__ import annotations

import logging

import httpx
import pytest

from app.kronos import service as kronos
from app.services import auto_trader as at


def _forecast(start: float, end: float) -> dict:
    """A Kronos payload shaped exactly like the /api/forecast/{symbol} body."""
    return {
        "source": "kronos",
        "model": "Kronos-mini",
        "device": "cpu",
        "symbol": "TEST",
        "predictions": [
            {"date": "2026-08-04", "open": start, "high": start, "low": start, "close": start},
            {"date": "2026-08-05", "open": end,   "high": end,   "low": end,   "close": end},
        ],
    }


@pytest.fixture(autouse=True)
def _no_loopback(monkeypatch):
    """
    Any HTTP call at all fails the test. The old implementation issued one per
    ticker; the new one must issue none.
    """
    at._kronos_cache.clear()

    def _forbidden(*args, **kwargs):
        raise AssertionError(f"the auto-trader made an HTTP call: {args!r}")

    monkeypatch.setattr(httpx, "get", _forbidden)
    yield
    at._kronos_cache.clear()


def test_expected_return_is_computed_in_process(monkeypatch):
    monkeypatch.setattr(kronos, "get_forecast", lambda sym, days: _forecast(100.0, 110.0))

    got = at._kronos_expected_return("AAPL")

    assert got == pytest.approx(0.10), (
        f"expected +10% from a 100 -> 110 forecast, got {got!r} "
        "(the loopback implementation returned None here, because the stubbed "
        "HTTP call raised and the bare except swallowed it)"
    )


def test_a_whole_cycle_of_tickers_all_get_a_forecast(monkeypatch):
    """
    The defect in one assertion: a cycle scores every buy candidate, and 30
    candidates is an ordinary cycle. Over the loopback the 11th onwards got 429
    -> None within the same minute. In process there is no such cliff.
    """
    monkeypatch.setattr(kronos, "get_forecast", lambda sym, days: _forecast(50.0, 55.0))

    results = {f"T{i:02d}": at._kronos_expected_return(f"T{i:02d}") for i in range(30)}
    missing = [t for t, v in results.items() if v is None]

    assert not missing, (
        f"{len(missing)} of 30 tickers silently got no forecast: {missing[:5]}"
    )
    assert all(v == pytest.approx(0.10) for v in results.values())


def test_the_result_is_cached_per_ticker(monkeypatch):
    calls: list[str] = []

    def _counted(sym, days):
        calls.append(sym)
        return _forecast(10.0, 12.0)

    monkeypatch.setattr(kronos, "get_forecast", _counted)

    for _ in range(5):
        assert at._kronos_expected_return("MSFT") == pytest.approx(0.2)

    assert calls == ["MSFT"], f"the 1-hour cache was bypassed: {len(calls)} calls"


def test_an_unexpected_forecast_failure_is_logged_loudly(monkeypatch, caplog):
    """
    A trading input that becomes None must never do so quietly. If it is going
    to degrade the Kronos veto, the operator gets to see it in the log.
    """
    def _explode(sym, days):
        raise ZeroDivisionError("model blew up")

    monkeypatch.setattr(kronos, "get_forecast", _explode)

    with caplog.at_level(logging.DEBUG, logger=at.logger.name):
        assert at._kronos_expected_return("NVDA") is None

    loud = [r for r in caplog.records if r.levelno >= logging.WARNING and "NVDA" in r.getMessage()]
    assert loud, (
        "a Kronos failure produced no WARNING; records were "
        f"{[(r.levelname, r.getMessage()) for r in caplog.records]}"
    )


def test_kronos_not_being_installed_is_not_an_alarm(monkeypatch, caplog):
    """
    The opposite failure. Kronos is an optional extra (~2 GB of torch) and the
    app is documented to run without it, so "not set up" is the expected state
    on most deployments and must not cry wolf once per ticker per cycle — that
    is how a real warning gets ignored.
    """
    def _absent(sym, days):
        raise RuntimeError("Kronos is not set up.")

    monkeypatch.setattr(kronos, "get_forecast", _absent)

    with caplog.at_level(logging.DEBUG, logger=at.logger.name):
        assert at._kronos_expected_return("TSLA") is None

    warnings = [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert not warnings, (
        f"an unconfigured optional model logged {len(warnings)} warning(s): "
        f"{[r.getMessage() for r in warnings]}"
    )


def test_a_junk_symbol_never_reaches_the_forecaster(monkeypatch):
    """
    The ticker comes from an EDGAR filing, not from a validated request, and the
    HTTP route used to be the thing that validated it. Removing the route must
    not remove the check.
    """
    seen: list[str] = []
    monkeypatch.setattr(
        kronos,
        "get_forecast",
        lambda sym, days: (seen.append(sym), _forecast(1.0, 2.0))[1],
    )

    assert at._kronos_expected_return("../../etc/passwd") is None
    assert at._kronos_expected_return("") is None
    assert seen == [], f"unvalidated symbols reached the forecaster: {seen}"
