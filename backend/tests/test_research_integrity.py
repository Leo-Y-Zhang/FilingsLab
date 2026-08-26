"""
Research integrity: a shrunken sample must not be silent
========================================================
Both hypothesis tests iterate over traders and tolerate a per-trader failure:
H1's ``_get_portfolio_daily_returns`` ended ``except Exception: return []`` and
H2's loop ended ``except Exception: continue``. Neither logged anything and
neither told the caller, so a trader whose simulation blew up was removed from
the sample in silence and the p-value was computed on whatever survived.

That is the bug class SECURITY.md finding 9 already describes -- a bare except
swallowing an error and returning a value that looks valid -- except here the
value it corrupts is a published statistic. It bites hardest on H2, which pairs
at most six traders: dropping one takes df from 5 to 4, and commit b115a9a
exists precisely because the difference between those two matters at this
sample size.

The tolerance itself is deliberate and stays: one broken trader should not take
out the whole research page. What changes is that the skip is now logged per
trader and counted in the response, so a caller can see the sample it actually
got. These tests pin both halves; all were watched failing first.
"""
from __future__ import annotations

import os
from datetime import date, timedelta

# Must be set before app.core.config is imported anywhere.
os.environ.setdefault("API_TOKEN", "test-token-not-a-real-secret")

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.models.performance import PerformanceMetric  # noqa: F401 - mapper registration
from app.models.price import Price
from app.models.trade import Trade
from app.models.trader import Trader
from app.research import hypothesis as hyp

START = date(2023, 1, 2)
END = date(2023, 12, 29)

SENTINEL = "engine exploded on this trader"


def _add_trades(session, trader_id: int) -> None:
    for disclosed, kind in (
        (START + timedelta(days=10), "buy"),
        (START + timedelta(days=200), "sell"),
    ):
        session.add(Trade(
            trader_id=trader_id,
            asset_symbol="ACME",
            transaction_type=kind,
            trade_date=disclosed - timedelta(days=20),
            disclosure_date=disclosed,
            value_range_low=10_000,
            value_range_high=20_000,
            value_estimate=15_000,
        ))


@pytest.fixture()
def db():
    """Three politician traders who all trade, on a rising ACME and a flat SPY."""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()

    day, step = START, 0
    while day <= END:
        session.add(Price(asset_symbol="ACME", date=day, closing_price=100.0 + step * 0.05))
        session.add(Price(asset_symbol="SPY", date=day, closing_price=400.0))
        day += timedelta(days=1)
        step += 1

    for name in ("Trader One", "Trader Two", "Trader Three"):
        trader = Trader(name=name, category="politician")
        session.add(trader)
        session.flush()
        _add_trades(session, trader.id)

    session.commit()
    yield session
    session.close()


@pytest.fixture()
def break_one_trader(monkeypatch):
    """Make the simulation raise for exactly one trader id, really run the rest."""
    real_sim_run = hyp.sim_run

    def _install(trader_id: int):
        def _patched(db, cfg):
            if cfg.trader_id == trader_id:
                raise RuntimeError(SENTINEL)
            return real_sim_run(db, cfg)

        monkeypatch.setattr(hyp, "sim_run", _patched)

    return _install


def _ids(session) -> list[int]:
    return [t.id for t in session.query(Trader).order_by(Trader.id).all()]


# -- H1 -----------------------------------------------------------------------

def test_h1_logs_the_trader_whose_simulation_failed(db, break_one_trader, caplog):
    broken = _ids(db)[1]
    break_one_trader(broken)

    with caplog.at_level("WARNING", logger="app.research.hypothesis"):
        hyp.test_h1_excess_returns(db, "politician")

    assert SENTINEL in caplog.text, "the exception was swallowed without a trace"
    assert str(broken) in caplog.text, "the log does not say which trader was dropped"


def test_h1_discloses_the_skipped_trader_in_its_result(db, break_one_trader):
    break_one_trader(_ids(db)[1])

    result = hyp.test_h1_excess_returns(db, "politician")

    assert result.traders_total == 3
    assert result.traders_used == 2
    assert result.traders_skipped == 1


def test_h1_interpretation_admits_the_sample_is_incomplete(db, break_one_trader):
    """The UI renders `interpretation` verbatim, so that is where a human sees it."""
    break_one_trader(_ids(db)[1])

    result = hyp.test_h1_excess_returns(db, "politician")

    assert "incomplete" in result.interpretation.lower()


def test_h1_says_nothing_about_skips_when_the_sample_is_whole(db):
    result = hyp.test_h1_excess_returns(db, "politician")

    assert result.traders_total == 3
    assert result.traders_used == 3
    assert result.traders_skipped == 0
    assert "incomplete" not in result.interpretation.lower()


def test_h1_discloses_a_trader_that_simply_has_no_trades(db):
    """
    No monkeypatching: a trader with an empty trade list is a real data state,
    and it shrinks the sample exactly the same way an exception does.
    """
    extra = Trader(name="Trader Four", category="politician")
    db.add(extra)
    db.commit()

    result = hyp.test_h1_excess_returns(db, "politician")

    assert result.traders_total == 4
    assert result.traders_used == 3
    assert result.traders_skipped == 1


# -- H2 -----------------------------------------------------------------------

def test_h2_logs_the_trader_whose_simulation_failed(db, break_one_trader, caplog):
    broken = _ids(db)[1]
    break_one_trader(broken)

    with caplog.at_level("WARNING", logger="app.research.hypothesis"):
        hyp.test_h2_early_vs_late(db)

    assert SENTINEL in caplog.text, "the exception was swallowed without a trace"
    assert str(broken) in caplog.text, "the log does not say which trader was dropped"


def test_h2_discloses_the_skipped_trader_in_its_result(db, break_one_trader):
    """
    H2 pairs at most six traders, so a silent skip moves df directly. This is
    the number the paired t-test is computed on -- it has to be visible.
    """
    break_one_trader(_ids(db)[1])

    result = hyp.test_h2_early_vs_late(db)

    assert result.traders_total == 3
    assert result.traders_used == 2
    assert result.traders_skipped == 1


def test_h2_interpretation_admits_the_sample_is_incomplete(db, break_one_trader):
    break_one_trader(_ids(db)[1])

    result = hyp.test_h2_early_vs_late(db)

    assert "incomplete" in result.interpretation.lower()


def test_h2_says_nothing_about_skips_when_the_sample_is_whole(db):
    result = hyp.test_h2_early_vs_late(db)

    assert result.traders_total == 3
    assert result.traders_used == 3
    assert result.traders_skipped == 0
    assert "incomplete" not in result.interpretation.lower()
