"""
Statistical Analysis Module
============================
Bootstrap confidence intervals, hypothesis tests, and distributional
summaries for use in the Research layer.

Uses numpy when available; falls back to pure Python otherwise.
"""

import math
import random
from typing import Optional
import logging

logger = logging.getLogger(__name__)

try:
    import numpy as np
    _HAS_NUMPY = True
except ImportError:
    _HAS_NUMPY = False
    logger.warning("numpy not installed; falling back to pure-Python statistics")


# ── Bootstrap CI ──────────────────────────────────────────────────────────────

def bootstrap_mean_ci(
    data: list[float],
    n_bootstrap: int = 2000,
    ci: float = 0.95,
    seed: Optional[int] = None,
) -> tuple[float, float, float]:
    """
    Bootstrap confidence interval on the mean.

    Returns (mean, ci_lower, ci_upper) where the interval covers `ci` of the
    bootstrap distribution.
    """
    if not data:
        return 0.0, 0.0, 0.0

    alpha = 1 - ci
    lo_pct = alpha / 2 * 100
    hi_pct = (1 - alpha / 2) * 100

    mean_val = sum(data) / len(data)

    if _HAS_NUMPY:
        rng = np.random.default_rng(seed)
        arr = np.array(data)
        boot_means = [rng.choice(arr, size=len(arr), replace=True).mean() for _ in range(n_bootstrap)]
        lo = float(np.percentile(boot_means, lo_pct))
        hi = float(np.percentile(boot_means, hi_pct))
    else:
        rng = random.Random(seed)
        n = len(data)
        boot_means = []
        for _ in range(n_bootstrap):
            sample = [rng.choice(data) for _ in range(n)]
            boot_means.append(sum(sample) / n)
        boot_means.sort()
        lo_idx = int(lo_pct / 100 * n_bootstrap)
        hi_idx = int(hi_pct / 100 * n_bootstrap)
        lo = boot_means[max(0, lo_idx)]
        hi = boot_means[min(n_bootstrap - 1, hi_idx)]

    return mean_val, lo, hi


def bootstrap_percentile(
    data: list[float],
    percentiles: list[float],
    n_bootstrap: int = 1000,
    seed: Optional[int] = None,
) -> list[float]:
    """Return the requested percentiles of the data distribution."""
    if not data:
        return [0.0] * len(percentiles)
    if _HAS_NUMPY:
        return [float(np.percentile(data, p)) for p in percentiles]
    sorted_data = sorted(data)
    n = len(sorted_data)
    result = []
    for p in percentiles:
        idx = p / 100 * (n - 1)
        lo_i = int(math.floor(idx))
        hi_i = min(lo_i + 1, n - 1)
        frac = idx - lo_i
        result.append(sorted_data[lo_i] * (1 - frac) + sorted_data[hi_i] * frac)
    return result


# ── One-sample t-test (against benchmark) ─────────────────────────────────────

def one_sample_t_test(
    data: list[float],
    mu0: float,
) -> tuple[float, float]:
    """
    Tests H0: mean(data) == mu0 against H1: mean(data) != mu0.

    Returns (t_statistic, two-tailed p_value).
    Uses normal approximation for large n (valid for the research use case).
    """
    n = len(data)
    if n < 2:
        return 0.0, 1.0

    mean = sum(data) / n
    var = sum((x - mean) ** 2 for x in data) / (n - 1)
    std = math.sqrt(var) if var > 0 else 1e-10
    se = std / math.sqrt(n)
    t_stat = (mean - mu0) / se

    p_val = 2 * _normal_sf(abs(t_stat))

    return t_stat, p_val


def _normal_sf(z: float) -> float:
    """Survival function of the standard normal (P(Z > z))."""
    return 0.5 * math.erfc(z / math.sqrt(2))


# ── Distributional summaries ─────────────────────────────────────────────────

def distribution_stats(data: list[float]) -> dict:
    """Compute common descriptive statistics for a numeric list."""
    if not data:
        return {}
    n = len(data)
    mean = sum(data) / n
    sorted_data = sorted(data)
    median = sorted_data[n // 2] if n % 2 == 1 else (sorted_data[n // 2 - 1] + sorted_data[n // 2]) / 2
    var = sum((x - mean) ** 2 for x in data) / (n - 1) if n > 1 else 0
    std = math.sqrt(var)
    return {
        "n": n,
        "mean": round(mean, 6),
        "median": round(median, 6),
        "std": round(std, 6),
        "min": round(sorted_data[0], 6),
        "max": round(sorted_data[-1], 6),
        "p5":  round(_percentile(sorted_data,  5), 6),
        "p25": round(_percentile(sorted_data, 25), 6),
        "p75": round(_percentile(sorted_data, 75), 6),
        "p95": round(_percentile(sorted_data, 95), 6),
    }


def _percentile(sorted_data: list[float], pct: float) -> float:
    n = len(sorted_data)
    idx = pct / 100 * (n - 1)
    lo = int(math.floor(idx))
    hi = min(lo + 1, n - 1)
    frac = idx - lo
    return sorted_data[lo] * (1 - frac) + sorted_data[hi] * frac
