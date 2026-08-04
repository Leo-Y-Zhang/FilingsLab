"""
Paper Portfolio Models
======================
SQLAlchemy models for the internal paper trading engine.
Tracks virtual cash, positions, order history, and auto-trader config.
"""
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.core.database import Base


class PaperAccount(Base):
    __tablename__ = "paper_accounts"

    id         = Column(Integer, primary_key=True, index=True)
    cash       = Column(Float, default=100_000.0, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    positions = relationship("PaperPosition", back_populates="account", cascade="all, delete-orphan")
    orders    = relationship("PaperOrder",    back_populates="account", cascade="all, delete-orphan")


class PaperPosition(Base):
    __tablename__ = "paper_positions"

    id         = Column(Integer, primary_key=True, index=True)
    account_id = Column(Integer, ForeignKey("paper_accounts.id"), nullable=False)
    ticker     = Column(String(20), nullable=False, index=True)
    qty        = Column(Float, default=0.0, nullable=False)
    avg_cost   = Column(Float, default=0.0, nullable=False)

    account = relationship("PaperAccount", back_populates="positions")


class PaperOrder(Base):
    __tablename__ = "paper_orders"

    id         = Column(Integer, primary_key=True, index=True)
    account_id = Column(Integer, ForeignKey("paper_accounts.id"), nullable=False)
    ticker     = Column(String(20), nullable=False)
    side       = Column(String(4),  nullable=False)   # buy / sell
    qty        = Column(Float, nullable=False)
    price      = Column(Float, nullable=False)
    notional   = Column(Float, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    account = relationship("PaperAccount", back_populates="orders")


class AutoTraderConfig(Base):
    """Single-row table — one config per installation."""
    __tablename__ = "auto_trader_config"

    id                  = Column(Integer, primary_key=True, default=1)
    enabled             = Column(Boolean, default=False, nullable=False)
    # Entry filters
    min_score           = Column(Float, default=60.0, nullable=False)
    trade_buys          = Column(Boolean, default=True,  nullable=False)
    trade_sell_signals  = Column(Boolean, default=True,  nullable=False)  # close on insider sells
    # Position sizing
    max_position_pct    = Column(Float, default=10.0, nullable=False)  # % of portfolio per stock
    max_positions       = Column(Integer, default=8,    nullable=False)
    # Exit rules
    take_profit_pct     = Column(Float, default=15.0, nullable=False)
    stop_loss_pct       = Column(Float, default=7.0,  nullable=False)
    # Schedule
    run_interval_mins   = Column(Integer, default=30, nullable=False)
    last_run_at         = Column(DateTime, nullable=True)
    last_run_summary    = Column(Text, nullable=True)
    updated_at          = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class AutoTraderLog(Base):
    """One row per auto-trader action."""
    __tablename__ = "auto_trader_log"

    id         = Column(Integer, primary_key=True, index=True)
    action     = Column(String(10), nullable=False)   # buy / sell / skip / stop_loss / take_profit
    ticker     = Column(String(20), nullable=False)
    reason     = Column(String(255), nullable=True)
    score      = Column(Float, nullable=True)
    price      = Column(Float, nullable=True)
    notional   = Column(Float, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
