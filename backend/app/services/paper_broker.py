"""
Paper Broker — Internal Paper Trading Engine
=============================================
Simulates paper trading with a PostgreSQL-backed virtual portfolio.
No external broker account needed. Prices come from yfinance.

Starting balance: $100,000 virtual cash.
"""
from __future__ import annotations

import logging
from typing import Optional

import yfinance as yf
from sqlalchemy.orm import Session

from app.models.paper_portfolio import PaperAccount, PaperOrder, PaperPosition

logger = logging.getLogger(__name__)

STARTING_CASH = 100_000.0


# ── Price helper ──────────────────────────────────────────────────────────────

def _get_price(ticker: str) -> Optional[float]:
    try:
        info = yf.Ticker(ticker).fast_info
        return float(info.last_price or info.previous_close or 0) or None
    except Exception:
        return None


# ── Account ───────────────────────────────────────────────────────────────────

def get_or_create_account(db: Session) -> PaperAccount:
    acc = db.query(PaperAccount).first()
    if not acc:
        acc = PaperAccount(cash=STARTING_CASH)
        db.add(acc)
        db.commit()
        db.refresh(acc)
    return acc


# ── Portfolio ─────────────────────────────────────────────────────────────────

def get_portfolio(db: Session) -> dict:
    account = get_or_create_account(db)
    rows = (
        db.query(PaperPosition)
        .filter(PaperPosition.account_id == account.id, PaperPosition.qty > 0.0001)
        .all()
    )

    positions = []
    total_market_value = 0.0

    for pos in rows:
        price = _get_price(pos.ticker) or pos.avg_cost
        market_value = pos.qty * price
        cost_basis   = pos.qty * pos.avg_cost
        unreal_pl    = market_value - cost_basis
        unreal_plpc  = unreal_pl / cost_basis if cost_basis else 0.0
        total_market_value += market_value
        positions.append({
            "symbol":          pos.ticker,
            "qty":             round(pos.qty, 4),
            "avg_entry_price": round(pos.avg_cost, 4),
            "current_price":   round(price, 4),
            "market_value":    round(market_value, 2),
            "unrealized_pl":   round(unreal_pl, 2),
            "unrealized_plpc": round(unreal_plpc, 4),
        })

    portfolio_value  = account.cash + total_market_value
    total_return_pct = (portfolio_value - STARTING_CASH) / STARTING_CASH * 100

    return {
        "account": {
            "cash":            round(account.cash, 2),
            "portfolio_value": round(portfolio_value, 2),
            "buying_power":    round(account.cash, 2),
            "starting_value":  STARTING_CASH,
            "total_return_pct": round(total_return_pct, 2),
            "currency":        "USD",
        },
        "positions":      positions,
        "open_orders":    [],
        "broker_enabled": True,
        "paper":          True,
    }


def get_status(db: Session) -> dict:
    account = get_or_create_account(db)
    portfolio = get_portfolio(db)
    return {
        "connected":       True,
        "paper":           True,
        "buying_power":    str(round(account.cash, 2)),
        "portfolio_value": str(round(portfolio["account"]["portfolio_value"], 2)),
        "cash":            str(round(account.cash, 2)),
        "currency":        "USD",
        "total_return_pct": portfolio["account"]["total_return_pct"],
    }


# ── Trades ────────────────────────────────────────────────────────────────────

def execute_trade(
    db: Session,
    ticker: str,
    side: str,
    notional: Optional[float] = None,
    qty: Optional[float] = None,
) -> dict:
    account = get_or_create_account(db)

    price = _get_price(ticker)
    if not price:
        raise ValueError(f"Cannot get current price for {ticker}")

    shares = (notional / price) if notional else (float(qty) if qty else None)
    if not shares:
        raise ValueError("Provide notional (dollars) or qty (shares)")

    actual_notional = shares * price

    if side == "buy":
        if account.cash < actual_notional:
            raise ValueError(
                f"Insufficient cash — have ${account.cash:,.2f}, need ${actual_notional:,.2f}"
            )
        account.cash -= actual_notional

        pos = (
            db.query(PaperPosition)
            .filter(PaperPosition.account_id == account.id, PaperPosition.ticker == ticker)
            .first()
        )
        if pos:
            total_cost = pos.qty * pos.avg_cost + actual_notional
            pos.qty   += shares
            pos.avg_cost = total_cost / pos.qty
        else:
            db.add(PaperPosition(account_id=account.id, ticker=ticker, qty=shares, avg_cost=price))

    else:  # sell
        pos = (
            db.query(PaperPosition)
            .filter(PaperPosition.account_id == account.id, PaperPosition.ticker == ticker)
            .first()
        )
        if not pos or pos.qty < shares - 0.0001:
            have = pos.qty if pos else 0
            raise ValueError(f"Insufficient shares — have {have:.4f}, need {shares:.4f}")
        pos.qty  -= shares
        account.cash += actual_notional

    db.add(PaperOrder(
        account_id=account.id,
        ticker=ticker,
        side=side,
        qty=shares,
        price=price,
        notional=actual_notional,
    ))
    db.commit()
    logger.info("Paper %s: %s %.4f @ $%.2f = $%.2f", side.upper(), ticker, shares, price, actual_notional)

    return {
        "ticker":    ticker,
        "side":      side,
        "qty":       round(shares, 4),
        "price":     round(price, 4),
        "notional":  round(actual_notional, 2),
        "simulated": False,
        "paper":     True,
    }


def close_position(db: Session, ticker: str) -> Optional[dict]:
    account = get_or_create_account(db)
    pos = (
        db.query(PaperPosition)
        .filter(PaperPosition.account_id == account.id, PaperPosition.ticker == ticker, PaperPosition.qty > 0.0001)
        .first()
    )
    if not pos:
        return None
    return execute_trade(db, ticker, "sell", qty=pos.qty)
