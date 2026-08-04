"""
Signal Engine  — v3
====================
Research-backed scoring that produces a realistic distribution of signals,
not a pile of strong-buys.

Score 0–100 across five independent factors:

  1. Insider conviction   0–30   role × size × cluster count
  2. Recency              0–20   exponential decay on disclosure age
  3. Kronos forecast      0–25   AI-predicted price direction + magnitude
  4. Price momentum       0–15   post-disclosure drift (entry quality)
  5. Volume anomaly       0–10   unusual volume ≈ news catalyst proxy

Thresholds (buy side):
  strong_buy  ≥ 75
  buy         ≥ 58
  watch       ≥ 42
  skip        <  42

Sell side is the mirror image (strong_sell / sell / watch / skip).

Sources:
  Jeng, Metrick & Zeckhauser (2003) — insider purchase alpha ~6%/yr
  Lakonishok & Lee (2001) — officer buys >> director buys
  Seyhun (1998) — cluster buying = strongest signal
  Cohen, Malloy & Pomorski (2012) — routine vs opportunistic insider trades
"""
from __future__ import annotations

import logging
import math
from datetime import date, datetime
from typing import Optional

logger = logging.getLogger(__name__)

# ── Thresholds ─────────────────────────────────────────────────────────────────
STRONG_BUY_THRESHOLD  = 75.0
BUY_THRESHOLD         = 58.0
WATCH_THRESHOLD       = 42.0


# ── 1. Insider conviction (0–30) ───────────────────────────────────────────────
# Based on Lakonishok & Lee: officers > directors; size matters; clusters >> single

_ROLE_BASE: dict[str, float] = {
    "ceo":        18.0,
    "cfo":        17.0,
    "coo":        16.0,
    "cto":        15.0,
    "president":  16.0,
    "officer":    13.0,
    "director":    9.0,
    "10%":         8.0,
    "insider":     7.0,
}


def _conviction_score(
    trader_role: str,
    amount_est: Optional[float],
    cluster_count: int = 1,
) -> float:
    role_lower = (trader_role or "").lower()
    base = 7.0
    for key, val in _ROLE_BASE.items():
        if key in role_lower:
            base = val
            break

    # Size tier (research: $100k+ is where alpha is significant)
    amt = amount_est or 0.0
    if amt >= 1_000_000:
        size_mult = 1.50
    elif amt >= 500_000:
        size_mult = 1.30
    elif amt >= 100_000:
        size_mult = 1.15
    elif amt >= 50_000:
        size_mult = 1.00
    else:
        size_mult = 0.65   # sub-$50k: negligible signal

    # Cluster boost (Seyhun 1998: 3+ insiders buying = strongest predictor)
    cluster_mult = 1.0 + min(cluster_count - 1, 4) * 0.12

    return min(30.0, base * size_mult * cluster_mult)


# ── 2. Recency (0–20) ─────────────────────────────────────────────────────────
# Half-life ~8 days: after 30 days the signal is effectively dead

def _recency_score(disclosure_date_str: Optional[str]) -> float:
    try:
        disc = _parse_date(disclosure_date_str)
        age  = max(0, (date.today() - disc).days)
        return 20.0 * math.exp(-age / 8.0)
    except Exception:
        return 8.0


# ── 3. Kronos forecast (0–25) ─────────────────────────────────────────────────
# Expected return from Kronos 10-day price prediction

def _kronos_score(
    kronos_expected_return: Optional[float],
    transaction_type: str,
) -> float:
    if kronos_expected_return is None:
        return 10.0   # neutral when unavailable

    ret = kronos_expected_return   # e.g. 0.05 = +5%

    if transaction_type == "buy":
        if ret >= 0.07:   return 25.0
        if ret >= 0.04:   return 20.0
        if ret >= 0.02:   return 15.0
        if ret >= 0.00:   return 10.0
        if ret >= -0.03:  return  5.0
        return 0.0                  # Kronos says down >3% → veto

    else:  # sell signal — inverted
        if ret <= -0.07:  return 25.0
        if ret <= -0.04:  return 20.0
        if ret <= -0.02:  return 15.0
        if ret <= 0.00:   return 10.0
        if ret <=  0.03:  return  5.0
        return 0.0


# ── 4. Price momentum (0–15) ──────────────────────────────────────────────────
# Better entry when stock pulled back after disclosure

def _momentum_score(
    transaction_type: str,
    current_price: Optional[float],
    price_at_disclosure: Optional[float],
) -> float:
    if not current_price or not price_at_disclosure or price_at_disclosure == 0:
        return 7.0

    chg = (current_price - price_at_disclosure) / price_at_disclosure

    if transaction_type == "buy":
        if chg <= -0.08:  return 15.0   # pulled back hard — great entry
        if chg <= -0.03:  return 12.0
        if chg <=  0.05:  return  9.0
        if chg <=  0.10:  return  6.0
        return 3.0                       # already ran — chasing

    else:  # sell
        if chg >=  0.08:  return 15.0   # still elevated — good exit
        if chg >=  0.03:  return 12.0
        if chg >= -0.05:  return  9.0
        if chg >= -0.10:  return  6.0
        return 3.0


# ── 5. Volume anomaly (0–10) ──────────────────────────────────────────────────
# Unusual volume is a proxy for undisclosed news / market awareness

def _volume_score(volume_ratio: float) -> float:
    if volume_ratio >= 3.0:   return 10.0
    if volume_ratio >= 2.0:   return  8.0
    if volume_ratio >= 1.5:   return  6.0
    if volume_ratio >= 1.0:   return  4.0
    return 2.0


# ── Action mapping ─────────────────────────────────────────────────────────────

def action_for_score(score: float, transaction_type: str = "buy") -> str:
    if transaction_type == "sell":
        if score >= STRONG_BUY_THRESHOLD: return "strong_sell"
        if score >= BUY_THRESHOLD:        return "sell"
        if score >= WATCH_THRESHOLD:      return "watch"
        return "skip"
    else:
        if score >= STRONG_BUY_THRESHOLD: return "strong_buy"
        if score >= BUY_THRESHOLD:        return "buy"
        if score >= WATCH_THRESHOLD:      return "watch"
        return "skip"


# ── Main entry ─────────────────────────────────────────────────────────────────

def score_signal(
    trader_name:             str,
    ticker:                  str,
    transaction_type:        str,
    trade_date:              Optional[str],
    disclosure_date:         Optional[str],
    amount_est:              Optional[float],
    trader_role:             str              = "",
    current_price:           Optional[float]  = None,
    price_at_disclosure:     Optional[float]  = None,
    volume_ratio:            float            = 1.0,
    kronos_expected_return:  Optional[float]  = None,
    cluster_count:           int              = 1,
) -> tuple[float, str]:
    """
    Returns (score 0–100, human-readable reason string).
    Higher = stronger actionable signal.
    """
    c1 = _conviction_score(trader_role, amount_est, cluster_count)
    c2 = _recency_score(disclosure_date)
    c3 = _kronos_score(kronos_expected_return, transaction_type)
    c4 = _momentum_score(transaction_type, current_price, price_at_disclosure)
    c5 = _volume_score(volume_ratio)

    total = c1 + c2 + c3 + c4 + c5

    parts = []
    if c2 < 4:
        parts.append("signal is stale (>25 days old)")
    if c3 == 0.0:
        parts.append("Kronos forecast is bearish — vetoed")
    elif kronos_expected_return is not None:
        parts.append(f"Kronos: {kronos_expected_return*100:+.1f}% expected")
    if volume_ratio >= 2.0:
        parts.append(f"volume {volume_ratio:.1f}× avg (possible catalyst)")
    if cluster_count > 1:
        parts.append(f"{cluster_count} insiders buying")
    if current_price and price_at_disclosure:
        chg = (current_price - price_at_disclosure) / price_at_disclosure * 100
        parts.append(f"price {chg:+.1f}% since filing")

    reason = "; ".join(parts) if parts else "within acceptable parameters"
    return round(total, 1), reason


# ── Helpers ────────────────────────────────────────────────────────────────────

def _parse_date(s: Optional[str]) -> date:
    if not s:
        raise ValueError("empty date")
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    raise ValueError(f"unrecognised date: {s!r}")


# Legacy shim — feed.py calls this with old signature
def update_trader_scores(scores: dict) -> None:
    pass   # no longer used — role-based scoring replaces history lookup
