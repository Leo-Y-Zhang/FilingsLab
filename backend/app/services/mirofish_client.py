"""
MiroFish Client
===============
Integrates MiroFish (github.com/666ghj/MiroFish) — a swarm-intelligence
engine that simulates thousands of AI agents (traders, analysts, retail
investors) reacting to news and market events.

Output used by the auto-trader
───────────────────────────────
  bullish_probability  0–1   fraction of agents who turned bullish
  bearish_probability  0–1   fraction of agents who turned bearish
  confidence           0–1   how strongly the crowd agreed
  sentiment_score     -1–1   net sentiment (bullish - bearish)

Integration design
───────────────────
• MiroFish simulations take 15-20 minutes — they run in a background
  thread, result cached for 4 hours per ticker.
• Auto-trader checks cache before each buy; if result exists it adjusts
  the signal score (+10 for strong bullish consensus, -15 to veto if
  bearish consensus outweighs the insider signal).
• If MiroFish is not running the function returns None and auto-trader
  proceeds unaffected — fully graceful degradation.

Running MiroFish
─────────────────
  git clone https://github.com/666ghj/MiroFish.git
  cd MiroFish
  cp .env.example .env          # add GEMINI_API_KEY (free tier works)
  docker compose up -d          # starts on http://localhost:5001

Environment variable (optional):
  MIROFISH_URL=http://localhost:5001   (default)
"""
from __future__ import annotations

import logging
import os
import threading
import time
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

_BASE = os.getenv("MIROFISH_URL", "http://localhost:5001")

# ── Per-ticker cache: {ticker: (timestamp, result_dict | None)} ───────────────
_cache: dict[str, tuple[float, Optional[dict]]] = {}
_CACHE_TTL = 4 * 3600   # 4 hours
_pending: set[str] = set()
_lock = threading.Lock()


def _is_available() -> bool:
    try:
        r = httpx.get(f"{_BASE}/health", timeout=3)
        return r.status_code == 200
    except Exception:
        return False


def _build_context(ticker: str, news_headlines: list[str],
                   edgar_summary: str) -> str:
    """Compose a short document for MiroFish to reason about."""
    lines = [
        f"Stock ticker: {ticker}",
        f"Insider event: {edgar_summary}",
        "",
        "Recent news headlines:",
    ]
    for h in news_headlines[:8]:
        lines.append(f"  • {h}")
    return "\n".join(lines)


def _run_simulation(ticker: str, context_doc: str) -> Optional[dict]:
    """
    Synchronous — call from a background thread only.
    Returns the parsed MiroFish summary dict or None on failure.
    """
    try:
        # 1. Build knowledge graph
        graph_resp = httpx.post(
            f"{_BASE}/api/graph/build",
            json={"documents": [context_doc], "chunk_size": 500, "chunk_overlap": 50},
            timeout=120,
        )
        if graph_resp.status_code != 200:
            logger.debug("MiroFish graph/build failed for %s: %s", ticker, graph_resp.text[:200])
            return None
        graph_id = graph_resp.json()["graph_id"]

        # 2. Create simulation
        sim_resp = httpx.post(
            f"{_BASE}/api/simulation/create",
            json={
                "graph_id":    graph_id,
                "requirement": (
                    f"Given the insider purchase and recent news for {ticker}, "
                    "will the stock price increase over the next 10 trading days? "
                    "What is the crowd sentiment?"
                ),
                "platforms":   ["twitter", "reddit"],
                "num_agents":  300,   # balance speed vs accuracy
            },
            timeout=30,
        )
        if sim_resp.status_code != 200:
            return None
        sim_id = sim_resp.json()["simulation_id"]

        # 3. Start simulation
        httpx.post(f"{_BASE}/api/simulation/{sim_id}/start", timeout=10)

        # 4. Poll until complete (max 25 min)
        deadline = time.time() + 1500
        while time.time() < deadline:
            status = httpx.get(f"{_BASE}/api/simulation/{sim_id}/status", timeout=10).json()
            if status.get("completed"):
                break
            time.sleep(30)
        else:
            logger.warning("MiroFish simulation timed out for %s", ticker)
            return None

        # 5. Fetch results
        results = httpx.get(f"{_BASE}/api/simulation/{sim_id}/results", timeout=20).json()
        summary = results.get("report", {}).get("summary", {})
        dist    = summary.get("agent_sentiment_distribution", {})

        bullish = float(dist.get("bullish", 0.33))
        bearish = float(dist.get("bearish", 0.33))
        neutral = float(dist.get("neutral",  1 - bullish - bearish))
        conf    = float(summary.get("confidence", 0.5))

        parsed = {
            "bullish_probability": round(bullish, 3),
            "bearish_probability": round(bearish, 3),
            "neutral_probability": round(neutral, 3),
            "confidence":          round(conf, 3),
            "sentiment_score":     round(bullish - bearish, 3),
            "prediction":          summary.get("prediction", ""),
        }
        logger.info("MiroFish %s: bullish=%.0f%% bearish=%.0f%% conf=%.0f%%",
                    ticker, bullish*100, bearish*100, conf*100)
        return parsed

    except Exception as exc:
        logger.debug("MiroFish simulation error for %s: %s", ticker, exc)
        return None


def _background_simulate(ticker: str, context_doc: str):
    result = _run_simulation(ticker, context_doc)
    with _lock:
        _cache[ticker]   = (time.time(), result)
        _pending.discard(ticker)
    logger.info("MiroFish cached result for %s: %s", ticker, result)


def get_sentiment(
    ticker: str,
    news_headlines: Optional[list[str]] = None,
    edgar_summary: str = "",
) -> Optional[dict]:
    """
    Returns cached MiroFish result if available, triggers a background
    simulation if not. Returns None immediately if nothing is cached.

    The auto-trader calls this synchronously — it's instant (cache hit or
    returns None while simulation runs in background).
    """
    now = time.time()

    # Return valid cache
    with _lock:
        if ticker in _cache:
            ts, result = _cache[ticker]
            if now - ts < _CACHE_TTL:
                return result
        already_pending = ticker in _pending

    if already_pending:
        return None   # simulation in progress — caller proceeds without it

    # Check MiroFish is reachable before spawning thread
    if not _is_available():
        return None

    # Kick off background simulation
    context = _build_context(ticker, news_headlines or [], edgar_summary)
    with _lock:
        _pending.add(ticker)

    t = threading.Thread(
        target=_background_simulate,
        args=(ticker, context),
        daemon=True,
        name=f"mirofish-{ticker}",
    )
    t.start()
    logger.info("MiroFish simulation started in background for %s", ticker)
    return None   # first call always None; result available next cycle


def score_adjustment(sentiment: Optional[dict]) -> float:
    """
    Convert MiroFish sentiment into a signal score adjustment (-15 to +10).

    Design rationale:
      • Strong bullish consensus (>65% agents bullish, conf>0.7): +10 pts
        — crowd agrees with the insider, amplified conviction
      • Moderate bullish (>55% bullish): +5 pts
      • Neutral: 0 pts
      • Bearish consensus (>55% bearish): -10 pts
        — human behaviour simulation says crowds will sell
      • Strong bearish (>65% bearish, conf>0.7): -15 pts
        — potential veto territory (auto-trader checks separately)

    The adjustment does NOT change action tiers on its own — it nudges
    scores that are near a threshold in the right direction.
    """
    if sentiment is None:
        return 0.0

    bullish = sentiment["bullish_probability"]
    bearish = sentiment["bearish_probability"]
    conf    = sentiment["confidence"]

    if bullish >= 0.65 and conf >= 0.70:
        return 10.0
    if bullish >= 0.55:
        return 5.0
    if bearish >= 0.65 and conf >= 0.70:
        return -15.0
    if bearish >= 0.55:
        return -10.0
    return 0.0


def is_hard_veto(sentiment: Optional[dict]) -> bool:
    """
    Returns True if MiroFish strongly predicts bearish crowd behaviour —
    enough to block a trade even if the insider signal is positive.
    Threshold: >70% agents bearish with >75% confidence.
    """
    if sentiment is None:
        return False
    return (
        sentiment["bearish_probability"] >= 0.70
        and sentiment["confidence"]       >= 0.75
    )
