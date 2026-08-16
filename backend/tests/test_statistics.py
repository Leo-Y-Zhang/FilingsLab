"""
Unit tests for the statistical analysis module.
"""

import pytest
import math
from app.analytics.statistics import (
    bootstrap_mean_ci,
    bootstrap_percentile,
    one_sample_t_test,
    distribution_stats,
)


class TestBootstrapMeanCI:
    def test_empty(self):
        mean, lo, hi = bootstrap_mean_ci([])
        assert mean == 0.0 and lo == 0.0 and hi == 0.0

    def test_single_value(self):
        mean, lo, hi = bootstrap_mean_ci([5.0])
        assert mean == pytest.approx(5.0)

    def test_ci_ordering(self):
        data = [1.0, 2.0, 3.0, 4.0, 5.0] * 20
        mean, lo, hi = bootstrap_mean_ci(data, n_bootstrap=500, seed=42)
        assert lo <= mean <= hi

    def test_width_narrows_with_more_data(self):
        # Draw both samples from the SAME seeded distribution so that only the
        # sample size differs; a larger sample must give a narrower CI on the mean.
        import numpy as np
        rng = np.random.default_rng(1)
        population = rng.normal(0.0, 1.0, 300)
        small = population[:30].tolist()
        large = population.tolist()
        _, lo_s, hi_s = bootstrap_mean_ci(small, n_bootstrap=200, seed=1)
        _, lo_l, hi_l = bootstrap_mean_ci(large, n_bootstrap=200, seed=1)
        assert (hi_s - lo_s) >= (hi_l - lo_l)


class TestBootstrapPercentile:
    def test_empty(self):
        result = bootstrap_percentile([], [25, 50, 75])
        assert result == [0.0, 0.0, 0.0]

    def test_known_values(self):
        data = list(range(100))
        result = bootstrap_percentile(data, [0, 50, 100])
        assert result[0] == pytest.approx(0.0, abs=1)
        assert result[1] == pytest.approx(49.5, abs=2)
        assert result[2] == pytest.approx(99.0, abs=1)


class TestOneSampleTTest:
    def test_clear_rejection(self):
        # mean = 1.0, mu0 = 0 → should reject H0
        data = [1.0] * 100
        t, p = one_sample_t_test(data, 0.0)
        assert t > 0
        assert p < 0.05

    def test_fail_to_reject(self):
        # data centred on mu0
        import random
        rng = random.Random(99)
        data = [rng.gauss(0, 1) for _ in range(50)]
        t, p = one_sample_t_test(data, 0.0)
        # p-value should not consistently reject (probabilistic — just check types)
        assert isinstance(t, float)
        assert 0 <= p <= 1

    def test_insufficient_data(self):
        t, p = one_sample_t_test([1.0], 0.0)
        assert t == 0.0 and p == 1.0

    def test_small_sample_uses_t_distribution(self):
        # H2 runs this test on at most six traders, so df = 5 — nowhere near
        # the large-n regime where the normal tail is a usable approximation.
        # These are per-trader (early - late) return differences in percent.
        diffs = [1.0, -0.5, 2.0, 1.2, 0.1, 2.2]
        t, p = one_sample_t_test(diffs, 0.0)
        assert t == pytest.approx(2.3271, abs=1e-3)
        # Two-tailed area beyond |t| = 2.3271 under Student's t with df = 5.
        # The standard normal gives 0.0200 for the same statistic, which would
        # have H2 announce significant outperformance from six observations.
        assert p == pytest.approx(0.0675, abs=1e-3)
        assert p > 0.05

    def test_two_observations_is_cauchy(self):
        # df = 1: the t distribution is Cauchy, so P(|T| >= 1) = 1/2 exactly.
        t, p = one_sample_t_test([0.0, 2.0], 0.0)
        assert t == pytest.approx(1.0)
        assert p == pytest.approx(0.5, abs=1e-6)

    def test_large_sample_approaches_normal(self):
        # The fix must not disturb the large-n case: with n = 2000 the t tail
        # and the normal tail agree to well inside a percent of each other.
        data = [0.05] * 1000 + [-0.03] * 1000
        t, p = one_sample_t_test(data, 0.0)
        normal_p = math.erfc(abs(t) / math.sqrt(2))
        assert p == pytest.approx(normal_p, rel=0.01)


class TestDistributionStats:
    def test_empty(self):
        assert distribution_stats([]) == {}

    def test_basic(self):
        data = [1.0, 2.0, 3.0, 4.0, 5.0]
        stats = distribution_stats(data)
        assert stats["n"] == 5
        assert stats["mean"] == pytest.approx(3.0)
        assert stats["min"] == pytest.approx(1.0)
        assert stats["max"] == pytest.approx(5.0)

    def test_single_element(self):
        stats = distribution_stats([42.0])
        assert stats["mean"] == pytest.approx(42.0)
        assert stats["std"] == pytest.approx(0.0)
