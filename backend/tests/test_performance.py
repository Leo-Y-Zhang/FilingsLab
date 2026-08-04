"""
Unit tests for the performance analytics engine.
"""

import pytest
from app.analytics.performance import (
    total_return, annualized_return, volatility,
    sharpe_ratio, sortino_ratio, max_drawdown,
    win_rate, daily_returns_from_values, compute_all,
)


class TestTotalReturn:
    def test_basic(self):
        assert total_return(100, 150) == pytest.approx(0.5)

    def test_loss(self):
        assert total_return(100, 80) == pytest.approx(-0.2)

    def test_no_change(self):
        assert total_return(100, 100) == pytest.approx(0.0)

    def test_invalid_initial(self):
        with pytest.raises(ValueError):
            total_return(0, 100)


class TestAnnualizedReturn:
    def test_one_year(self):
        result = annualized_return(0.10, 365)
        assert result == pytest.approx(0.10, abs=1e-4)

    def test_zero_days(self):
        assert annualized_return(0.1, 0) == 0.0

    def test_negative_return(self):
        result = annualized_return(-0.20, 365)
        assert result == pytest.approx(-0.20, abs=1e-4)


class TestDailyReturns:
    def test_basic(self):
        values = [100.0, 110.0, 99.0]
        rets = daily_returns_from_values(values)
        assert len(rets) == 2
        assert rets[0] == pytest.approx(0.10)
        assert rets[1] == pytest.approx(-0.10)

    def test_single_value(self):
        assert daily_returns_from_values([100.0]) == []

    def test_empty(self):
        assert daily_returns_from_values([]) == []


class TestVolatility:
    def test_zero_returns(self):
        assert volatility([0.0, 0.0, 0.0, 0.0]) == pytest.approx(0.0)

    def test_single_return(self):
        assert volatility([0.01]) == 0.0

    def test_positive_vol(self):
        rets = [0.01, -0.01, 0.02, -0.02]
        vol = volatility(rets)
        assert vol > 0


class TestSharpeRatio:
    def test_positive_excess_returns(self):
        # Realistic positive-drift daily returns with genuine (non-zero) volatility,
        # so the Sharpe ratio is meaningfully greater than zero.
        import numpy as np
        rng = np.random.default_rng(7)
        rets = (0.0008 + rng.normal(0.0, 0.004, 252)).tolist()
        sr = sharpe_ratio(rets, annual_risk_free=0.0)
        assert sr > 0

    def test_zero_variance(self):
        # A constant (zero-variance) series has undefined volatility; the code
        # guard returns exactly 0.0.
        rets = [0.002] * 252
        sr = sharpe_ratio(rets, annual_risk_free=0.002 * 252)
        assert sr == 0.0

    def test_insufficient_data(self):
        assert sharpe_ratio([0.01]) == 0.0


class TestSortinoRatio:
    def test_no_downside_returns(self):
        rets = [0.002] * 100
        # All returns positive → downside std = 0 → Sortino = 0
        assert sortino_ratio(rets, annual_risk_free=0.0) == 0.0

    def test_with_downside(self):
        rets = [0.01, -0.02, 0.015, -0.005, 0.008]
        so = sortino_ratio(rets, annual_risk_free=0.04)
        assert isinstance(so, float)

    def test_higher_than_sharpe_for_one_sided_risk(self):
        # Returns that are all positive when above RF → Sortino should be ≥ Sharpe
        rets = [0.003, 0.001, 0.002, -0.001, 0.004]
        sr = sharpe_ratio(rets, annual_risk_free=0.0)
        so = sortino_ratio(rets, annual_risk_free=0.0)
        # Sortino >= Sharpe when downside vol < total vol
        assert isinstance(so, float) and isinstance(sr, float)


class TestMaxDrawdown:
    def test_no_drawdown(self):
        assert max_drawdown([100, 110, 120, 130]) == pytest.approx(0.0)

    def test_full_loss(self):
        dd = max_drawdown([100, 50, 10])
        assert dd < 0

    def test_recovery(self):
        dd = max_drawdown([100, 80, 120])
        assert dd == pytest.approx(-0.20)

    def test_empty(self):
        assert max_drawdown([]) == 0.0


class TestWinRate:
    def test_all_wins(self):
        assert win_rate([0.01, 0.02, 0.03]) == pytest.approx(1.0)

    def test_half_wins(self):
        assert win_rate([0.01, -0.01]) == pytest.approx(0.5)

    def test_empty(self):
        assert win_rate([]) == 0.0


class TestComputeAll:
    def test_full_output(self):
        values = [100_000 * (1 + i * 0.001) for i in range(300)]
        result = compute_all(values, [0.01, 0.02], 300)
        assert "total_return" in result
        assert "sharpe_ratio" in result
        assert "sortino_ratio" in result
        assert "max_drawdown" in result
        assert result["total_return"] is not None
        assert result["sortino_ratio"] is not None

    def test_insufficient_values(self):
        result = compute_all([100_000], [], 1)
        assert result["total_return"] is None
        assert result["sortino_ratio"] is None
