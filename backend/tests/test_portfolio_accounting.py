"""Cash, share and cost conservation with hand-calculated fills."""

import pytest

from app.simulation.portfolio import Portfolio


def test_buy_caps_spend_to_cash_and_charges_fee_once():
    portfolio = Portfolio(1000)
    assert portfolio.buy("ACME", 2000, 20, 0.01) == pytest.approx(49.5)
    assert portfolio.cash == 0
    assert portfolio.positions["ACME"].shares == pytest.approx(49.5)
    assert portfolio.positions["ACME"].avg_cost == 20
    assert portfolio.total_value({"ACME": 20}) == pytest.approx(990)


def test_repeated_buys_use_share_weighted_cost_and_missing_quote_uses_cost():
    portfolio = Portfolio(1000)
    portfolio.buy("ACME", 200, 10, 0)
    portfolio.buy("ACME", 300, 30, 0)
    assert portfolio.cash == 500
    assert portfolio.positions["ACME"].shares == 30
    assert portfolio.positions["ACME"].avg_cost == pytest.approx(500 / 30)
    assert portfolio.equity_value({}) == pytest.approx(500)
    assert portfolio.snapshot({"ACME": 20}) == {"cash": 500, "invested": 600, "total": 1100}
    assert portfolio.position_value("ACME", 20) == 600
    assert portfolio.position_value("MISSING", 20) == 0


def test_partial_sell_then_oversized_sell_conserves_shares_and_cash():
    portfolio = Portfolio(1000)
    portfolio.buy("ACME", 600, 20, 0)
    assert portfolio.sell("ACME", 250, 25, 0.02) == pytest.approx(245)
    assert portfolio.cash == pytest.approx(645)
    assert portfolio.positions["ACME"].shares == 20
    assert portfolio.positions["ACME"].avg_cost == 20
    assert portfolio.sell("ACME", 10000, 25, 0.02) == pytest.approx(490)
    assert portfolio.cash == pytest.approx(1135)
    assert portfolio.positions == {}
    assert portfolio.snapshot({}) == {"cash": 1135, "invested": 0, "total": 1135}


@pytest.mark.parametrize("allocation,price", [(100, 0), (100, -1), (0, 10), (-1, 10)])
def test_invalid_buy_does_not_change_state(allocation, price):
    portfolio = Portfolio(1000)
    assert portfolio.buy("ACME", allocation, price, 0) == 0
    assert portfolio.cash == 1000
    assert portfolio.positions == {}


def test_unfunded_and_sub_precision_buys_do_not_change_state():
    portfolio = Portfolio(100)
    portfolio.buy("ACME", 100, 10, 0)
    assert portfolio.buy("BETA", 100, 10, 0) == 0
    assert portfolio.cash == 0
    assert set(portfolio.positions) == {"ACME"}
    tiny = Portfolio(100)
    assert tiny.buy("ACME", 1e-10, 10, 0) == 0
    assert tiny.cash == 100
    assert tiny.positions == {}


@pytest.mark.parametrize("symbol,price", [("MISSING", 10), ("ACME", 0), ("ACME", -1)])
def test_invalid_sell_does_not_change_state(symbol, price):
    portfolio = Portfolio(1000)
    portfolio.buy("ACME", 500, 10, 0)
    assert portfolio.sell(symbol, 100, price, 0) == 0
    assert portfolio.cash == 500
    assert portfolio.positions["ACME"].shares == 50
