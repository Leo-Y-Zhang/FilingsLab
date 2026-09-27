"""
Auto-trader API contract
========================
Behind the operator token, so these run with it. Each test here was watched
failing first.
"""
from __future__ import annotations

import os

# Must be set before app.core.config is imported anywhere.
os.environ["API_TOKEN"] = "test-token-not-a-real-secret"

from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings
from app.core.database import Base, get_db
from app.main import app
from app.models.paper_portfolio import AutoTraderConfig, AutoTraderLog

AUTH = {"Authorization": f"Bearer {os.environ['API_TOKEN']}"}
RAN_AT = datetime(2026, 9, 25, 20, 0, 0)   # naive, as datetime.utcnow() stores it


@pytest.fixture()
def client():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    with Session() as seed:
        seed.add(AutoTraderConfig(enabled=False, last_run_at=RAN_AT, last_run_summary="ok"))
        seed.add(AutoTraderLog(action="buy", ticker="AAPL", reason="r", score=70.0,
                               price=100.0, notional=1_000.0, created_at=RAN_AT))
        seed.commit()

    def _db():
        with Session() as session:
            yield session

    app.dependency_overrides[get_db] = _db
    get_settings.cache_clear()
    app.state.limiter.reset()
    yield TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.clear()


def test_last_run_is_sent_as_utc(client):
    """
    The auto-trader stamps rows with naive datetime.utcnow(). Sent bare, a
    browser parses "2026-09-25T20:00:00" as local time, so the Feed page's
    "Last run" read 20:00 in New York for a run at 16:00 there.
    """
    r = client.get("/api/feed/auto-trader/config", headers=AUTH)
    assert r.status_code == 200
    assert r.json()["last_run_at"] == "2026-09-25T20:00:00+00:00"


def test_activity_log_times_are_sent_as_utc(client):
    r = client.get("/api/feed/auto-trader/log", headers=AUTH)
    assert r.status_code == 200
    assert [row["created_at"] for row in r.json()["log"]] == ["2026-09-25T20:00:00+00:00"]
