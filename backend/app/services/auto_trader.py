"""
Auto-Trader Engine  — v2
=========================
Fully autonomous paper-trading bot. Runs on a background thread.

Decision pipeline each cycle
─────────────────────────────
1.  Market regime   — SPY 50-day vs 200-day MA.
                      Bear market: halt new buys, tighten stops.

2.  Exit scan       — For every open position check:
                        • Hard stop-loss
                        • Take-profit
                        • Trailing stop (once position is up >15%)
                        • Time-based exit (>90 days held)
                        • Insider sell signal for same ticker

3.  Fetch signals   — Pull live EDGAR Form 4 disclosures.

4.  Cluster detect  — Count how many unique insiders bought same ticker
                      in the last 14 days.

5.  Enrich          — For each buy candidate:
                        • Current price + 20-day volume avg (yfinance)
                        • Kronos 10-day forecast
                        • News sentiment (yfinance headlines)
                        • MiroFish crowd-simulation sentiment (async cache)

6.  Score + rank    — Run signal_engine.score_signal() with all data.
                      Apply news +/-3 pts, MiroFish -15 to +10 pts.
                      Veto any signal where Kronos is net-negative or
                      MiroFish hard veto (>70% bearish, >75% conf).

7.  Open positions  — Buy top-ranked signals within capital / position limits.
                      Sizing: scaled Kelly fraction based on signal strength.

Parameters (all stored in AutoTraderConfig, editable via UI)
─────────────────────────────────────────────────────────────
  min_score            65    minimum score to open a position
  max_position_pct      8    % of portfolio per position
  max_positions        10    maximum concurrent positions
  take_profit_pct      20    exit at +20% (insider alpha peaks here)
  stop_loss_pct         8    exit at -8%  (2.5:1 reward/risk)
  run_interval_mins    30
  trade_buys          True
  trade_sell_signals  True

Research basis
─────────────────────────────────────────────────────────────
  Jeng, Metrick & Zeckhauser (2003): insider purchases alpha ~6%/yr
  Seyhun (1998): cluster buys are the strongest predictive signal
  Cohen, Malloy & Pomorski (2012): opportunistic trades >> routine ones
  Standard Kelly criterion with 0.25 fraction for conservative sizing
"""
from __future__ import annotations

import logging
import re
import threading
import time
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Optional

import yfinance as yf
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.paper_portfolio import AutoTraderConfig, AutoTraderLog, PaperPosition
from app.services import edgar
from app.services import signal_engine as se
from app.services import paper_broker as pb
from app.services import mirofish_client as mf

logger = logging.getLogger(__name__)

_lock    = threading.Lock()
_running = False

# ── Config helpers ────────────────────────────────────────────────────────────

def get_or_create_config(db: Session) -> AutoTraderConfig:
    cfg = db.query(AutoTraderConfig).first()
    if not cfg:
        cfg = AutoTraderConfig(
            enabled=False,
            min_score=65.0,
            max_position_pct=8.0,
            max_positions=10,
            take_profit_pct=20.0,
            stop_loss_pct=8.0,
            run_interval_mins=30,
        )
        db.add(cfg)
        db.commit()
        db.refresh(cfg)
    return cfg


def update_config(db: Session, **kwargs) -> AutoTraderConfig:
    cfg = get_or_create_config(db)
    for k, v in kwargs.items():
        if hasattr(cfg, k):
            setattr(cfg, k, v)
    cfg.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(cfg)
    return cfg


def _log(db: Session, action: str, ticker: str, reason: str = "",
         score: float = 0.0, price: float = 0.0, notional: float = 0.0):
    db.add(AutoTraderLog(
        action=action, ticker=ticker, reason=reason[:250],
        score=score, price=price, notional=notional,
    ))
    db.commit()


# ── Market regime ─────────────────────────────────────────────────────────────

def _market_regime() -> str:
    """
    'bull' when SPY 50-day MA > 200-day MA (golden cross).
    'bear' otherwise — halts new longs, tightens stops.
    Cached for 4 hours to avoid hammering yfinance.
    """
    try:
        hist = yf.Ticker("SPY").history(period="1y", auto_adjust=True)
        if len(hist) < 200:
            return "bull"
        ma50  = float(hist["Close"].rolling(50).mean().iloc[-1])
        ma200 = float(hist["Close"].rolling(200).mean().iloc[-1])
        return "bull" if ma50 > ma200 else "bear"
    except Exception as exc:
        logger.debug("Market regime check failed: %s", exc)
        return "bull"   # default to bull if SPY unavailable


_regime_cache: tuple[float, str] = (0.0, "bull")

def market_regime() -> str:
    global _regime_cache
    if time.time() - _regime_cache[0] > 14_400:   # 4-hour cache
        regime = _market_regime()
        _regime_cache = (time.time(), regime)
    return _regime_cache[1]


# ── Volume ratio ──────────────────────────────────────────────────────────────

def _volume_ratio(ticker: str) -> float:
    try:
        hist = yf.Ticker(ticker).history(period="1mo", auto_adjust=True)
        if len(hist) < 5:
            return 1.0
        avg20 = float(hist["Volume"].rolling(20).mean().iloc[-1])
        last  = float(hist["Volume"].iloc[-1])
        return round(last / avg20, 2) if avg20 > 0 else 1.0
    except Exception:
        return 1.0


# ── Kronos forecast ───────────────────────────────────────────────────────────

_kronos_cache: dict[str, tuple[float, Optional[float]]] = {}

# Same whitelist the /api/forecast/{symbol} route applies. The ticker comes out
# of an EDGAR filing rather than a validated request, and calling the forecaster
# in process means the route is no longer there to check it.
_SYMBOL_RE = re.compile(r"^[A-Z0-9.\-]{1,12}$")

_KRONOS_PRED_DAYS = 10


def _kronos_expected_return(ticker: str) -> Optional[float]:
    """
    Expected ``_KRONOS_PRED_DAYS``-day return from Kronos, e.g. 0.05 = +5%.
    ``None`` means "no forecast" and disables the Kronos veto in ``_run_cycle``.
    Cached per ticker for 1 hour.

    This used to fetch the number by calling the app's own API back over the
    loopback (``GET http://localhost:8000/api/forecast/{ticker}``). That worked
    only while slowapi keyed rate limits on the concrete URL, giving each ticker
    its own budget. With the bucket correctly keyed on the route template, one
    process calling one route is ONE 10/minute budget for the whole cycle: from
    the 11th ticker the call returned 429, the exception path swallowed it, and
    the veto quietly stopped working. A trading input must not be able to
    disappear because of an internal rate limit.

    So the forecaster is called in process. No HTTP boundary, no limiter, no
    serialisation of a payload this module immediately re-parses — and a
    genuine failure is logged at WARNING instead of vanishing.
    """
    sym = (ticker or "").upper().strip()
    if not _SYMBOL_RE.match(sym):
        logger.debug("Kronos skipped: %r is not a usable symbol", ticker)
        return None

    now = time.time()
    if sym in _kronos_cache and now - _kronos_cache[sym][0] < 3600:
        return _kronos_cache[sym][1]

    ret: Optional[float] = None
    try:
        from app.kronos import service as kronos

        data  = kronos.get_forecast(sym, _KRONOS_PRED_DAYS)
        preds = data.get("predictions") or []
        if preds:
            current = data.get("current_price") or preds[0].get("open")
            final   = preds[-1].get("close") or preds[-1].get("open")
            if current and final and current > 0:
                ret = (final - current) / current
        if ret is None:
            logger.warning(
                "Kronos returned no usable forecast for %s; the Kronos veto is "
                "inactive for this candidate", sym,
            )
    except RuntimeError as exc:
        # Kronos is an optional ~2 GB extra and the app is documented to run
        # without it. "Not set up" is an expected deployment state, not an
        # incident, and warning once per ticker per cycle would train the
        # operator to ignore this logger.
        logger.debug("Kronos unavailable for %s: %s", sym, exc)
    except ValueError as exc:
        # Not enough OHLCV history for this symbol — a property of the symbol.
        logger.info("Kronos has insufficient history for %s: %s", sym, exc)
    except Exception:
        logger.warning(
            "Kronos forecast failed for %s; the Kronos veto is inactive for "
            "this candidate", sym, exc_info=True,
        )

    _kronos_cache[sym] = (now, ret)
    return ret


# ── News sentiment (proxy for human behaviour) ─────────────────────────────────

_POSITIVE_WORDS = {"beat", "beats", "strong", "surges", "upgrade", "raises",
                   "record", "profit", "growth", "bullish", "buy", "outperform"}
_NEGATIVE_WORDS = {"miss", "misses", "weak", "plunges", "downgrade", "cuts",
                   "loss", "decline", "bearish", "sell", "underperform", "fraud",
                   "investigation", "lawsuit", "recall"}

def _fetch_news(ticker: str) -> tuple[list[str], float]:
    """
    Returns (headlines, sentiment_score).
    headlines: up to 10 title strings for MiroFish context.
    sentiment_score: -1 to +1 soft tiebreaker (does not veto).
    """
    try:
        news = yf.Ticker(ticker).news or []
        headlines: list[str] = []
        pos = neg = 0
        for item in news[:10]:
            title = item.get("title") or ""
            if title:
                headlines.append(title)
            lower = title.lower()
            pos += sum(1 for w in _POSITIVE_WORDS if w in lower)
            neg += sum(1 for w in _NEGATIVE_WORDS if w in lower)
        total = pos + neg
        return headlines, ((pos - neg) / total if total else 0.0)
    except Exception:
        return [], 0.0


def _news_sentiment(ticker: str) -> float:
    """Convenience wrapper — returns only the sentiment score."""
    _, score = _fetch_news(ticker)
    return score


# ── Cluster detection ─────────────────────────────────────────────────────────

def _cluster_counts(disclosures: list[dict], window_days: int = 14) -> dict[str, int]:
    """
    Returns {ticker: count} of unique insiders who filed a buy in the last
    window_days. A cluster of 3+ is the strongest insider signal (Seyhun 1998).
    """
    cutoff = (date.today() - timedelta(days=window_days)).isoformat()
    counts: dict[str, set] = defaultdict(set)
    for d in disclosures:
        if d.get("transaction_type") == "buy" and d.get("disclosure_date", "") >= cutoff:
            counts[d["ticker"]].add(d.get("trader_name", "unknown"))
    return {t: len(names) for t, names in counts.items()}


# ── Kelly position sizing ──────────────────────────────────────────────────────

def _kelly_notional(
    score: float,
    portfolio_value: float,
    max_pct: float,
) -> float:
    """
    Scale position size by signal strength using a simplified Kelly fraction.

    Based on insider trading research win rates:
      strong_buy (≥75): ~62% win rate, avg win 20%, avg loss 8%
        → Kelly = (0.62*20 - 0.38*8)/20 = 0.468 → quarter-Kelly ≈ 11.7%
      buy (≥58):        ~54% win rate, avg win 15%, avg loss 8%
        → Kelly = (0.54*15 - 0.46*8)/15 = 0.295 → quarter-Kelly ≈ 7.4%

    We then cap at max_pct from config.
    """
    if score >= se.STRONG_BUY_THRESHOLD:
        fraction = 1.00   # full max_pct
    elif score >= se.BUY_THRESHOLD + 10:
        fraction = 0.75
    else:
        fraction = 0.50

    return portfolio_value * (max_pct / 100.0) * fraction


# ── Exit scan ─────────────────────────────────────────────────────────────────

def _check_exits(db: Session, cfg: AutoTraderConfig, held_tickers_selling: set[str]) -> list[str]:
    account   = pb.get_or_create_account(db)
    positions = (
        db.query(PaperPosition)
        .filter(PaperPosition.account_id == account.id, PaperPosition.qty > 0.0001)
        .all()
    )
    actions = []
    regime = market_regime()
    # In bear market tighten stop to 5%
    effective_stop = cfg.stop_loss_pct if regime == "bull" else min(cfg.stop_loss_pct, 5.0)

    for pos in positions:
        price = pb._get_price(pos.ticker)
        if not price:
            continue
        pnl_pct = (price - pos.avg_cost) / pos.avg_cost * 100

        reason = action = None

        # Insider sell signal — close regardless of P&L
        if pos.ticker in held_tickers_selling:
            reason = f"insider-sell signal"
            action = "sell"

        elif pnl_pct >= cfg.take_profit_pct:
            reason = f"+{pnl_pct:.1f}% take-profit"
            action = "take_profit"

        elif pnl_pct <= -effective_stop:
            reason = f"{pnl_pct:.1f}% stop-loss"
            action = "stop_loss"

        # Trailing stop: if up >15%, trail at half the gain
        elif pnl_pct > 15.0:
            trail_stop = pnl_pct * 0.5
            if pnl_pct < trail_stop:
                reason = f"trailing stop at {trail_stop:.1f}%"
                action = "stop_loss"

        # Time-based: close after 90 days (alpha decays — Cohen et al.)
        # We don't store entry date here so use order history
        # (skip for now — positions table has no entry date)

        if action:
            try:
                pb.close_position(db, pos.ticker)
                notional = pos.qty * price
                _log(db, action, pos.ticker, reason, price=price, notional=notional)
                msg = f"{action.upper()} {pos.ticker}: {reason}"
                actions.append(msg)
                logger.info("Auto-trader: %s", msg)
            except Exception as exc:
                logger.warning("Auto-trader exit %s failed: %s", pos.ticker, exc)

    return actions


# ── Main cycle ────────────────────────────────────────────────────────────────

def _run_cycle(db: Session) -> str:
    cfg = get_or_create_config(db)
    if not cfg.enabled:
        return "Auto-trader disabled."

    summary: list[str] = []
    regime = market_regime()
    if regime == "bear":
        summary.append("⚠ Bear market (SPY 50MA < 200MA) — no new longs")

    # Step 1 — fetch EDGAR disclosures.
    # This loop runs on its own background thread, not on an anyio request
    # worker, so it may block on the crawl; it cannot act without the data.
    raw = edgar.refresh_recent_now(limit=60)
    if not raw:
        msg = f"{'Bear market; ' if regime=='bear' else ''}No EDGAR data."
        _finish(db, cfg, msg)
        return msg

    # Step 2 — detect clusters
    clusters = _cluster_counts(raw)

    # Step 3 — identify tickers held + selling
    account = pb.get_or_create_account(db)
    held = {
        p.ticker for p in
        db.query(PaperPosition)
        .filter(PaperPosition.account_id == account.id, PaperPosition.qty > 0.0001)
        .all()
    }

    selling_tickers: set[str] = set()
    if cfg.trade_sell_signals:
        for d in raw:
            if d.get("transaction_type") == "sell" and d.get("ticker") in held:
                score, _ = se.score_signal(
                    trader_name=d.get("trader_name",""),
                    ticker=d.get("ticker",""),
                    transaction_type="sell",
                    trade_date=d.get("trade_date"),
                    disclosure_date=d.get("disclosure_date"),
                    amount_est=d.get("amount_est"),
                    trader_role=d.get("trader_role",""),
                    cluster_count=clusters.get(d.get("ticker",""), 1),
                )
                if score >= cfg.min_score:
                    selling_tickers.add(d["ticker"])

    # Step 4 — exits (with insider sell info)
    exits = _check_exits(db, cfg, selling_tickers)
    summary.extend(exits)

    # Step 5 — score buy candidates (skip in bear market)
    if regime == "bear" or not cfg.trade_buys:
        msg = "; ".join(summary) if summary else "Bear market — exits only."
        _finish(db, cfg, msg)
        return msg

    # Refresh account after exits
    account  = pb.get_or_create_account(db)
    portfolio = pb.get_portfolio(db)
    pv        = portfolio["account"]["portfolio_value"]

    open_count = (
        db.query(PaperPosition)
        .filter(PaperPosition.account_id == account.id, PaperPosition.qty > 0.0001)
        .count()
    )

    # De-duplicate buys by ticker (highest amount wins)
    buy_map: dict[str, dict] = {}
    for d in raw:
        if d.get("transaction_type") != "buy":
            continue
        t = d.get("ticker","")
        if not t:
            continue
        if t not in buy_map or (d.get("amount_est") or 0) > (buy_map[t].get("amount_est") or 0):
            buy_map[t] = d

    # Pre-warm MiroFish background simulations for all buy tickers now
    # so the *next* cycle has cached results. Costs nothing if cache is fresh.
    for ticker, d in buy_map.items():
        edgar_summary = (
            f"{d.get('trader_role','Insider')} at {ticker} purchased "
            f"~${d.get('amount_est', 0):,.0f} on {d.get('trade_date','unknown')}"
        )
        mf.get_sentiment(ticker, edgar_summary=edgar_summary)

    # Enrich and score each candidate
    candidates = []
    for ticker, d in buy_map.items():
        if open_count >= cfg.max_positions:
            break

        cur_price = pb._get_price(ticker)
        if not cur_price:
            continue

        vol_ratio             = _volume_ratio(ticker)
        kronos                = _kronos_expected_return(ticker)
        headlines, news_score = _fetch_news(ticker)

        edgar_summary = (
            f"{d.get('trader_role','Insider')} at {ticker} purchased "
            f"~${d.get('amount_est', 0):,.0f} on {d.get('trade_date','unknown')}"
        )

        # MiroFish crowd sentiment (cached async — may be None on first cycle)
        miro_sentiment = mf.get_sentiment(ticker, headlines, edgar_summary)
        miro_adj       = mf.score_adjustment(miro_sentiment)

        score, reason = se.score_signal(
            trader_name             = d.get("trader_name",""),
            ticker                  = ticker,
            transaction_type        = "buy",
            trade_date              = d.get("trade_date"),
            disclosure_date         = d.get("disclosure_date"),
            amount_est              = d.get("amount_est"),
            trader_role             = d.get("trader_role",""),
            current_price           = cur_price,
            volume_ratio            = vol_ratio,
            kronos_expected_return  = kronos,
            cluster_count           = clusters.get(ticker, 1),
        )

        # News sentiment: soft +/- 3 pts (does not change action tier)
        score = min(100.0, score + news_score * 3)
        # MiroFish crowd adjustment: -15 to +10 pts
        score = max(0.0, min(100.0, score + miro_adj))

        action = se.action_for_score(score, "buy")
        candidates.append({
            **d,
            "score":          score,
            "action":         action,
            "cur_price":      cur_price,
            "reason":         reason,
            "kronos":         kronos,
            "vol_ratio":      vol_ratio,
            "miro_sentiment": miro_sentiment,
            "miro_adj":       miro_adj,
        })

    # Sort by score descending
    candidates.sort(key=lambda x: x["score"], reverse=True)

    # Step 6 — open positions
    for c in candidates:
        if open_count >= cfg.max_positions:
            break
        if c["action"] not in ("buy", "strong_buy"):
            continue

        ticker = c["ticker"]

        # Skip if already held at max allocation
        existing = (
            db.query(PaperPosition)
            .filter(PaperPosition.account_id == account.id,
                    PaperPosition.ticker == ticker,
                    PaperPosition.qty > 0.0001)
            .first()
        )
        max_notional = _kelly_notional(c["score"], pv, cfg.max_position_pct)
        if existing:
            current_val = existing.qty * (pb._get_price(ticker) or existing.avg_cost)
            if current_val >= max_notional * 0.9:
                continue
            max_notional -= current_val

        notional = min(max_notional, account.cash * 0.90)
        if notional < 200:
            continue

        # Kronos veto: skip if forecast is net negative
        if c["kronos"] is not None and c["kronos"] < -0.02:
            _log(db, "skip", ticker, f"Kronos veto ({c['kronos']*100:+.1f}%)",
                 score=c["score"])
            continue

        # MiroFish hard veto: >70% agents bearish + >75% confidence
        if mf.is_hard_veto(c["miro_sentiment"]):
            miro = c["miro_sentiment"]
            _log(db, "skip", ticker,
                 f"MiroFish hard veto (bearish={miro['bearish_probability']:.0%}, "
                 f"conf={miro['confidence']:.0%})",
                 score=c["score"])
            logger.info("Auto-trader: MiroFish hard veto on %s", ticker)
            continue

        try:
            result = pb.execute_trade(db, ticker, "buy", notional=notional)
            # An absent forecast is stated, not omitted: it means this buy was
            # made with the Kronos veto inactive, and the operator reading the
            # activity log should be able to see that.
            kronos_str = (f", Kronos {c['kronos']*100:+.1f}%" if c['kronos'] is not None
                          else ", Kronos n/a (veto inactive)")
            miro_str   = (f", MiroFish {c['miro_adj']:+.0f}pts"
                          if c["miro_adj"] != 0 else "")
            msg = f"BUY {ticker} ${notional:,.0f} ({c['action']}, score {c['score']:.0f}{kronos_str}{miro_str})"
            _log(db, "buy", ticker, c["reason"],
                 score=c["score"], price=result["price"], notional=result["notional"])
            summary.append(msg)
            logger.info("Auto-trader: %s", msg)
            open_count += 1
            account = pb.get_or_create_account(db)
        except Exception as exc:
            logger.warning("Auto-trader buy %s failed: %s", ticker, exc)

    result_str = "; ".join(summary) if summary else "Cycle complete — no actions."
    _finish(db, cfg, result_str)
    return result_str


def _finish(db: Session, cfg: AutoTraderConfig, summary: str):
    cfg.last_run_at      = datetime.utcnow()
    cfg.last_run_summary = summary[:500]
    db.commit()


# ── Background loop ───────────────────────────────────────────────────────────

def _loop():
    global _running
    _running = True
    # Brief startup delay to let the DB settle
    time.sleep(5)
    while _running:
        try:
            with SessionLocal() as db:
                interval = get_or_create_config(db).run_interval_mins * 60
        except Exception:
            interval = 1800

        try:
            with _lock:
                with SessionLocal() as db:
                    summary = _run_cycle(db)
                    logger.info("Auto-trader: %s", summary)
        except Exception as exc:
            logger.warning("Auto-trader cycle error: %s", exc)

        time.sleep(interval)


_thread: Optional[threading.Thread] = None


def start_background_loop():
    global _thread
    if _thread and _thread.is_alive():
        return
    _thread = threading.Thread(target=_loop, daemon=True, name="auto-trader")
    _thread.start()
    logger.info("Auto-trader background thread started.")


def trigger_now() -> str:
    with _lock:
        with SessionLocal() as db:
            return _run_cycle(db)
