from sqlalchemy import Column, Integer, String, Date, Numeric, UniqueConstraint, DateTime
from sqlalchemy.sql import func
from app.core.database import Base


class Price(Base):
    __tablename__ = "prices"

    id = Column(Integer, primary_key=True, index=True)
    asset_symbol = Column(String(20), nullable=False, index=True)
    date = Column(Date, nullable=False, index=True)
    closing_price = Column(Numeric(20, 4), nullable=False)
    open_price = Column(Numeric(20, 4), nullable=True)
    high_price = Column(Numeric(20, 4), nullable=True)
    low_price = Column(Numeric(20, 4), nullable=True)
    volume = Column(Numeric(20, 0), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("asset_symbol", "date", name="uq_price_symbol_date"),
    )
