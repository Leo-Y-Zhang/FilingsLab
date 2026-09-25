"""
Auto-trader exits
=================
Reproduced against PostgreSQL 16 before the fix: a position up 30% took the
take-profit branch of ``_check_exits``, ``close_position`` sold it, and then
the activity-log insert failed with

    psycopg2.errors.StringDataRightTruncation:
    value too long for type character varying(10)

because ``AutoTraderLog.action`` was ``String(10)`` and "take_profit" is eleven
characters. The except branch then touched the rolled-back session, raised
``PendingRollbackError`` and took the rest of the cycle with it: the sale went
through, the log never recorded it, and no buys ran that cycle. SQLite does not
enforce VARCHAR lengths, which is how this passed every test, so the first test
here checks the lengths directly.

The same insert logged the exit at notional $0, because it read ``pos.qty``
after ``close_position`` had sold it to zero.

Both watched failing first.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.models.paper_portfolio import AutoTraderLog, PaperPosition
from app.services import auto_trader as at
from app.services import paper_broker as pb

_AUTO_TRADER = Path(at.__file__)


def _logged_actions() -> set[str]:
    """Every string the auto-trader can write into AutoTraderLog.action."""
    actions: set[str] = set()
    for node in ast.walk(ast.parse(_AUTO_TRADER.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant):
            if any(isinstance(t, ast.Name) and t.id == "action" for t in node.targets):
                actions.add(node.value.value)
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id == "_log" and len(node.args) > 1
                and isinstance(node.args[1], ast.Constant)):
            actions.add(node.args[1].value)
    return {a for a in actions if isinstance(a, str)}


def test_every_action_the_auto_trader_logs_fits_its_column():
    actions = _logged_actions()
    assert {"buy", "skip", "sell", "stop_loss", "take_profit"} <= actions, actions
    width = AutoTraderLog.__table__.c.action.type.length
    too_long = sorted(a for a in actions if len(a) > width)
    assert not too_long, f"{too_long} do not fit String({width})"


@pytest.fixture()
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


def test_an_exit_is_logged_with_the_value_it_sold(db, monkeypatch):
    monkeypatch.setattr(pb, "_get_price", lambda ticker: 130.0)   # +30% on a cost of 100
    monkeypatch.setattr(at, "market_regime", lambda: "bull")
    account = pb.get_or_create_account(db)
    db.add(PaperPosition(account_id=account.id, ticker="AAPL", qty=10, avg_cost=100.0))
    db.commit()

    actions = at._check_exits(db, at.get_or_create_config(db), set())

    assert actions == ["TAKE_PROFIT AAPL: +30.0% take-profit"]
    row = db.query(AutoTraderLog).one()
    assert (row.action, row.price, row.notional) == ("take_profit", 130.0, 1_300.0)
