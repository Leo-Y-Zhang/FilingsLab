"""
Request-log integrity
=====================
SECURITY.md finding 4 made the request log the app's only detection: one line
per request, plus an ``auth_failed`` WARNING naming the path that was probed.
That only works if a caller cannot choose what those lines say.

Starlette before 1.0.1 rebuilt ``request.url`` from the ``Host`` header without
validating it (CVE-2026-48710), and both log lines take their path from
``request.url.path``. Against starlette 0.41.3 this request to
``/api/feed/portfolio`` was logged as

    auth_failed reason=missing_token ... method=GET path=/api/other
    request_id=... method=GET path=/api/other status=401 ...

so a token-probing client could file every attempt under any path it liked.
Port 8000 is published directly (see SECURITY.md), so no proxy normalises the
header first. Watched failing on 0.41.3; passes on the pinned 1.7.0.

The same two lines were also the one sink ``logsafe.scrub`` never reached, and
the only one every anonymous request hits. The path arrives percent-decoded,
so ``%1b%5b2J`` is a raw ESC-[2J (clear screen) in the record; and uvicorn with
httptools accepts header bytes 0x80-0xFF, which decode to C1 controls such as
NEL (a line break to some readers) and CSI. Measured against a live uvicorn
before the fix:

    ... path=/api/nothing^[[31mRED<NEL><U+2028>x status=404 ...
    ... forwarded_for=1.2.3.4<NEL>FORGED ua="a<NEL>b<CSI>2Jc"

The control-character tests below were watched failing against that code.
"""
from __future__ import annotations

import os

# Must be set before app.core.config is imported anywhere.
os.environ.setdefault("API_TOKEN", "test-token-not-a-real-secret")

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.database import get_db
from app.main import app

_LOGGERS = ("app.request", "app.security")


class _FakeSession:
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
    # Not a context manager: that would run the lifespan and start the seeder
    # and auto-trader threads.
    yield TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.clear()


def _records(caplog) -> list[str]:
    return [r.getMessage() for r in caplog.records if r.name in _LOGGERS]


def test_a_hostile_host_header_cannot_rename_the_path_in_the_log(client, caplog):
    with caplog.at_level("INFO"):
        r = client.get("/api/feed/portfolio", headers={"Host": "evil.example/api/other?"})

    assert r.status_code == 401
    lines = _records(caplog)
    assert any("auth_failed" in line for line in lines), lines
    for line in lines:
        assert "path=/api/feed/portfolio" in line, line
        assert "/api/other" not in line, f"the Host header renamed the path: {line!r}"


# ── Control characters a caller can put into a log line ──────────────────────

_HOSTILE_SUFFIX = "x%1b%5b2J%C2%85%E2%80%A8forged"   # ESC [ 2 J, NEL, U+2028


def _assert_printable(line: str) -> None:
    bad = [ch for ch in line if not ch.isprintable()]
    assert not bad, f"control characters {bad!r} reached the log: {line!r}"


def test_control_characters_in_the_path_stay_out_of_the_request_log(client, caplog):
    with caplog.at_level("INFO"):
        client.get("/api/" + _HOSTILE_SUFFIX)

    lines = [line for line in _records(caplog) if "forged" in line]
    assert lines, "the request was not logged, so this proves nothing"
    for line in lines:
        _assert_printable(line)


def test_control_characters_in_the_path_stay_out_of_the_auth_failure_log(client, caplog):
    """The token check runs before the ticker allow-list, so the raw path gets here."""
    with caplog.at_level("WARNING", logger="app.security"):
        r = client.delete("/api/feed/position/" + _HOSTILE_SUFFIX)

    assert r.status_code == 401
    lines = [line for line in _records(caplog) if "auth_failed" in line]
    assert lines, "the failed auth was not logged, so this proves nothing"
    for line in lines:
        _assert_printable(line)


def test_c1_controls_in_headers_stay_out_of_the_request_log(client, caplog):
    headers = {
        "user-agent": b"agent\x85WARNING forged\x9b2J",
        "x-forwarded-for": b"203.0.113.9\x85WARNING forged",
    }
    with caplog.at_level("INFO", logger="app.request"):
        client.get("/api/health", headers=headers)

    lines = [line for line in _records(caplog) if "/api/health" in line]
    assert lines, "the request was not logged, so this proves nothing"
    for line in lines:
        _assert_printable(line)
        assert "forged" in line, "the values should be escaped, not dropped"
