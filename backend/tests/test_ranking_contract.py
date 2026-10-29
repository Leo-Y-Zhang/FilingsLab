"""Leaderboard arithmetic, drawdown penalties, missing data and rank numbers."""

from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.analytics import ranking
from app.core.database import Base
from app.models.performance import PerformanceMetric
from app.models.price import Price  # noqa: F401 - table registration
from app.models.trade import Trade  # noqa: F401 - mapper registration
from app.models.trader import Trader


@pytest.fixture()
def db(monkeypatch):
    monkeypatch.setattr(ranking, "settings", SimpleNamespace(
        rank_w_return=0.35, rank_w_sharpe=0.30,
        rank_w_drawdown=0.20, rank_w_consistency=0.15,
    ))
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


@pytest.mark.parametrize("values,expected", [
    ([], []), ([7], [0.5]), ([7, 7], [0.5, 0.5]),
    ([-10, 0, 30], [0, 0.25, 1]), ([10, 20, 50], [0, 0.25, 1]),
])
def test_population_normalization(values, expected):
    assert ranking._minmax(values) == expected


def add_trader(db, trader_id, **metrics):
    trader = Trader(id=trader_id, name=f"Example {trader_id}", category="insider")
    db.add(trader)
    perf = PerformanceMetric(trader_id=trader_id, **metrics)
    db.add(perf)
    db.commit()
    return perf


def test_score_weights_sorting_excess_return_and_persisted_score(db):
    first = add_trader(db, 1, total_return=10, sharpe_ratio=1, max_drawdown=-10,
                       win_rate=20, benchmark_return=4)
    second = add_trader(db, 2, total_return=20, sharpe_ratio=3, max_drawdown=-30,
                        win_rate=80, benchmark_return=5)
    rows = ranking.compute_rankings(db)
    assert [r.trader_id for r in rows] == [2, 1]
    assert [r.rank for r in rows] == [1, 2]
    assert [r.ranking_score for r in rows] == pytest.approx([0.6, 0])
    assert [r.excess_return for r in rows] == pytest.approx([15, 6])
    db.expire_all()
    assert float(first.ranking_score) == 0
    assert float(second.ranking_score) == pytest.approx(0.6)


def test_drawdown_magnitude_is_a_penalty_and_scores_cannot_be_negative(db):
    add_trader(db, 1, total_return=0, sharpe_ratio=0, max_drawdown=-10, win_rate=0)
    add_trader(db, 2, total_return=0, sharpe_ratio=0, max_drawdown=-30, win_rate=0)
    ranking.settings.rank_w_return = 0
    ranking.settings.rank_w_sharpe = 0
    ranking.settings.rank_w_consistency = 0
    ranking.settings.rank_w_drawdown = 1
    rows = ranking.compute_rankings(db)
    assert [r.ranking_score for r in rows] == [0, 0]


def test_empty_population_and_missing_performance_are_supported(db):
    assert ranking.compute_rankings(db) == []
    db.add(Trader(id=1, name="Example", category="insider"))
    db.commit()
    row, = ranking.compute_rankings(db)
    assert row.rank == 1
    assert row.ranking_score == pytest.approx(0.3)
    assert row.total_return is None
    assert row.excess_return is None


def test_zero_benchmark_is_a_real_benchmark(db):
    add_trader(db, 1, total_return=10, benchmark_return=0)
    row, = ranking.compute_rankings(db)
    assert row.excess_return == 10
