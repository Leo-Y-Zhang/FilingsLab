from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.core.database import Base


class Trader(Base):
    __tablename__ = "traders"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False, index=True)
    category = Column(String(100), nullable=False)   # politician | executive | insider
    party = Column(String(100), nullable=True)
    state = Column(String(100), nullable=True)
    bio = Column(String(1000), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    trades = relationship("Trade", back_populates="trader", cascade="all, delete-orphan")
    performance = relationship(
        "PerformanceMetric", back_populates="trader",
        uselist=False, cascade="all, delete-orphan",
    )
