from sqlalchemy import Column, Integer, String, Date, Numeric, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.core.database import Base


class Trade(Base):
    __tablename__ = "trades"

    id = Column(Integer, primary_key=True, index=True)
    trader_id = Column(Integer, ForeignKey("traders.id"), nullable=False, index=True)
    asset_symbol = Column(String(20), nullable=False, index=True)
    asset_name = Column(String(255), nullable=True)
    transaction_type = Column(String(10), nullable=False)   # "buy" | "sell"

    # The actual date the trade occurred (not publicly visible at the time)
    trade_date = Column(Date, nullable=False, index=True)
    # Date the disclosure entered the public record
    disclosure_date = Column(Date, nullable=False, index=True)

    # Raw label from filing (e.g. "$15,001 – $50,000")
    value_range_label = Column(String(100), nullable=True)
    # Range bounds for probabilistic sampling in Monte Carlo
    value_range_low = Column(Numeric(20, 2), nullable=True)
    value_range_high = Column(Numeric(20, 2), nullable=True)
    # Midpoint estimate (pre-computed = (lo + hi) / 2)
    value_estimate = Column(Numeric(20, 2), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    trader = relationship("Trader", back_populates="trades")
