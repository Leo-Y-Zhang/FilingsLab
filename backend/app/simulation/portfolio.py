"""
Portfolio State
===============
Mutable object that tracks cash and equity positions during a simulation.
No database dependency — pure Python.
"""

from dataclasses import dataclass, field


@dataclass
class Position:
    symbol: str
    shares: float
    avg_cost: float     # average purchase price (for P&L reporting)


@dataclass
class Portfolio:
    initial_capital: float
    cash: float = 0.0
    positions: dict[str, Position] = field(default_factory=dict)

    def __post_init__(self):
        if self.cash == 0.0:
            self.cash = self.initial_capital

    # ── Valuation ─────────────────────────────────────────────────────────────

    def equity_value(self, current_prices: dict[str, float]) -> float:
        """Sum of market value of all open positions."""
        return sum(
            pos.shares * current_prices.get(sym, pos.avg_cost)
            for sym, pos in self.positions.items()
        )

    def total_value(self, current_prices: dict[str, float]) -> float:
        return self.cash + self.equity_value(current_prices)

    def position_value(self, symbol: str, price: float) -> float:
        if symbol not in self.positions:
            return 0.0
        return self.positions[symbol].shares * price

    # ── Trade execution ───────────────────────────────────────────────────────

    def buy(
        self,
        symbol: str,
        allocation: float,
        execution_price: float,
        transaction_cost: float,
    ) -> float:
        """
        Execute a buy order.

        allocation        : amount in cash to spend (before costs)
        execution_price   : already adjusted for slippage by the caller
        transaction_cost  : fraction of allocation charged as fee

        Returns shares purchased (0 if insufficient cash or bad price).
        """
        if execution_price <= 0 or allocation <= 0:
            return 0.0

        affordable = min(allocation, self.cash)
        net_spend = affordable * (1 - transaction_cost)
        shares = net_spend / execution_price

        if shares < 1e-8:
            return 0.0

        self.cash -= affordable

        if symbol in self.positions:
            existing = self.positions[symbol]
            total_shares = existing.shares + shares
            total_cost = existing.shares * existing.avg_cost + shares * execution_price
            self.positions[symbol] = Position(symbol, total_shares, total_cost / total_shares)
        else:
            self.positions[symbol] = Position(symbol, shares, execution_price)

        return shares

    def sell(
        self,
        symbol: str,
        target_value: float,
        execution_price: float,
        transaction_cost: float,
    ) -> float:
        """
        Execute a sell order.

        target_value : how much of the position to liquidate (in cash terms).
        Returns actual proceeds received (after costs).
        """
        if symbol not in self.positions or execution_price <= 0:
            return 0.0

        pos = self.positions[symbol]
        max_sell_value = pos.shares * execution_price
        sell_value = min(target_value, max_sell_value)
        shares_to_sell = sell_value / execution_price

        proceeds = shares_to_sell * execution_price * (1 - transaction_cost)
        self.cash += proceeds

        remaining = pos.shares - shares_to_sell
        if remaining < 1e-8:
            del self.positions[symbol]
        else:
            self.positions[symbol] = Position(symbol, remaining, pos.avg_cost)

        return proceeds

    # ── Snapshot ──────────────────────────────────────────────────────────────

    def snapshot(self, current_prices: dict[str, float]) -> dict:
        total = self.total_value(current_prices)
        return {
            "cash":     self.cash,
            "invested": total - self.cash,
            "total":    total,
        }
