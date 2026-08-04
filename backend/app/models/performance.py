from sqlalchemy import Column, Integer, Numeric, ForeignKey, DateTime, Date
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.core.database import Base


class PerformanceMetric(Base):
    __tablename__ = "performance_metrics"

    id = Column(Integer, primary_key=True, index=True)
    trader_id = Column(Integer, ForeignKey("traders.id"), nullable=False, unique=True, index=True)

    # Return metrics
    total_return = Column(Numeric(12, 6), nullable=True)
    annualized_return = Column(Numeric(12, 6), nullable=True)
    benchmark_return = Column(Numeric(12, 6), nullable=True)

    # Risk metrics
    sharpe_ratio = Column(Numeric(12, 6), nullable=True)
    sortino_ratio = Column(Numeric(12, 6), nullable=True)    # downside-risk adjusted
    volatility = Column(Numeric(12, 6), nullable=True)
    max_drawdown = Column(Numeric(12, 6), nullable=True)

    # Consistency
    win_rate = Column(Numeric(12, 6), nullable=True)
    trade_count = Column(Integer, nullable=True)

    # Composite score
    ranking_score = Column(Numeric(12, 6), nullable=True)

    # Simulation parameters used for this metric set
    delay_days_used = Column(Integer, nullable=True, default=1)

    computed_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    period_start = Column(Date, nullable=True)
    period_end = Column(Date, nullable=True)

    trader = relationship("Trader", back_populates="performance")
