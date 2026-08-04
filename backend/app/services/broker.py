"""
Broker Service — Alpaca Paper / Live Trading
============================================
Wraps Alpaca's REST API for order submission and portfolio queries.

Paper trading is the default and is HARD-ENFORCED. Live order placement
requires an explicit, deliberate two-step opt-in (see get_broker): BOTH
ALPACA_PAPER=false AND ALLOW_LIVE_TRADING=I_UNDERSTAND_THE_RISK. A single
stray env var can never enable real-money trading.

Requirements:
  1. Sign up at alpaca.markets (free)
  2. Get API key + secret from the dashboard
  3. Add to .env:
       ALPACA_API_KEY=your_key
       ALPACA_SECRET_KEY=your_secret
       ALPACA_PAPER=true    ← paper trading (safe; the default)

If no keys are configured the broker is disabled and no orders are placed.
"""
from __future__ import annotations

import logging
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

_PAPER_URL = "https://paper-api.alpaca.markets"
_LIVE_URL  = "https://api.alpaca.markets"


class AlpacaBroker:
    def __init__(self, api_key: str, secret_key: str, paper: bool = True):
        self.enabled = bool(api_key and secret_key)
        self._base = _PAPER_URL if paper else _LIVE_URL
        self._headers = {
            "APCA-API-KEY-ID": api_key,
            "APCA-API-SECRET-KEY": secret_key,
            "Content-Type": "application/json",
        }
        self.paper = paper
        if self.enabled:
            logger.info("Alpaca broker ready — %s trading", "PAPER" if paper else "LIVE")
        else:
            logger.info("Alpaca broker disabled (no API keys configured)")

    # ── Account ───────────────────────────────────────────────────────────────

    def get_account(self) -> Optional[dict]:
        if not self.enabled:
            return None
        try:
            r = httpx.get(f"{self._base}/v2/account", headers=self._headers, timeout=10)
            r.raise_for_status()
            return r.json()
        except Exception as exc:
            logger.warning("Alpaca account fetch failed: %s", exc)
            return None

    def get_positions(self) -> list[dict]:
        if not self.enabled:
            return []
        try:
            r = httpx.get(f"{self._base}/v2/positions", headers=self._headers, timeout=10)
            r.raise_for_status()
            return r.json()
        except Exception as exc:
            logger.warning("Alpaca positions fetch failed: %s", exc)
            return []

    def get_orders(self, status: str = "open") -> list[dict]:
        if not self.enabled:
            return []
        try:
            r = httpx.get(
                f"{self._base}/v2/orders",
                headers=self._headers,
                params={"status": status, "limit": 100},
                timeout=10,
            )
            r.raise_for_status()
            return r.json()
        except Exception as exc:
            logger.warning("Alpaca orders fetch failed: %s", exc)
            return []

    # ── Orders ────────────────────────────────────────────────────────────────

    def market_buy(
        self,
        ticker: str,
        notional: Optional[float] = None,
        qty: Optional[float] = None,
    ) -> Optional[dict]:
        """
        Submit a market buy order.
        Specify either notional (dollar amount) or qty (shares).
        """
        return self._order(ticker, "buy", notional=notional, qty=qty)

    def market_sell(
        self,
        ticker: str,
        notional: Optional[float] = None,
        qty: Optional[float] = None,
    ) -> Optional[dict]:
        return self._order(ticker, "sell", notional=notional, qty=qty)

    def close_position(self, ticker: str) -> Optional[dict]:
        if not self.enabled:
            return None
        try:
            r = httpx.delete(
                f"{self._base}/v2/positions/{ticker.upper()}",
                headers=self._headers,
                timeout=10,
            )
            r.raise_for_status()
            return r.json()
        except Exception as exc:
            logger.warning("Alpaca close position failed %s: %s", ticker, exc)
            return None

    def _order(
        self,
        ticker: str,
        side: str,
        notional: Optional[float] = None,
        qty: Optional[float] = None,
    ) -> Optional[dict]:
        if not self.enabled:
            logger.info("Broker disabled — simulated %s %s", side, ticker)
            return {"simulated": True, "ticker": ticker, "side": side, "notional": notional}
        body: dict = {
            "symbol": ticker.upper(),
            "side": side,
            "type": "market",
            "time_in_force": "day",
        }
        if notional:
            body["notional"] = str(round(notional, 2))
        elif qty:
            body["qty"] = str(qty)
        else:
            logger.warning("Order skipped — no qty or notional specified")
            return None
        try:
            r = httpx.post(
                f"{self._base}/v2/orders",
                headers=self._headers,
                json=body,
                timeout=10,
            )
            r.raise_for_status()
            logger.info("Order placed: %s %s %s", side.upper(), ticker, body)
            return r.json()
        except Exception as exc:
            logger.warning("Alpaca order failed %s %s: %s", side, ticker, exc)
            return None


# ── Singleton ──────────────────────────────────────────────────────────────────

_broker: Optional[AlpacaBroker] = None


_LIVE_CONFIRM_PHRASE = "I_UNDERSTAND_THE_RISK"


def get_broker() -> AlpacaBroker:
    global _broker
    if _broker is None:
        from app.core.config import get_settings
        s = get_settings()
        paper = s.alpaca_paper
        # Safety lock: LIVE trading requires an explicit, deliberate opt-in.
        # ALPACA_PAPER=false alone is NOT enough — allow_live_trading must also
        # equal the confirmation phrase, otherwise we force PAPER mode.
        if not paper and s.allow_live_trading != _LIVE_CONFIRM_PHRASE:
            logger.warning(
                "LIVE trading requested (ALPACA_PAPER=false) but ALLOW_LIVE_TRADING is "
                "not set to the required confirmation phrase — forcing PAPER trading for "
                "safety. No real-money orders will be placed."
            )
            paper = True
        _broker = AlpacaBroker(s.alpaca_api_key, s.alpaca_secret_key, paper)
    return _broker
