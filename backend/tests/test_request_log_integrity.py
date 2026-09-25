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
