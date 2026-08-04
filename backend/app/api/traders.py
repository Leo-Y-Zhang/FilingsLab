from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.trader import Trader
from app.models.trade import Trade
from app.schemas.trader import TraderOut, TraderDetailOut, TradeOut, PerformanceOut

router = APIRouter(prefix="/traders", tags=["Traders"])


@router.get("/", response_model=list[TraderOut])
def list_traders(
    category: str | None = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """List all traders, optionally filtered by category."""
    q = db.query(Trader)
    if category:
        q = q.filter(Trader.category == category.lower())
    traders = q.offset(skip).limit(limit).all()

    result = []
    for t in traders:
        out = TraderOut.model_validate(t)
        out.trade_count = db.query(Trade).filter(Trade.trader_id == t.id).count()
        result.append(out)
    return result


@router.get("/{trader_id}", response_model=TraderDetailOut)
def get_trader(trader_id: int, db: Session = Depends(get_db)):
    """Get a single trader with performance metrics."""
    t = db.query(Trader).filter(Trader.id == trader_id).first()
    if not t:
        raise HTTPException(404, f"Trader {trader_id} not found")
    detail = TraderDetailOut.model_validate(t)
    detail.trade_count = len(t.trades)
    if t.performance:
        detail.performance = PerformanceOut.model_validate(t.performance)
    return detail


@router.get("/{trader_id}/trades", response_model=list[TradeOut])
def get_trader_trades(
    trader_id: int,
    skip: int = Query(0, ge=0),
    limit: int = Query(200, ge=1, le=500),
    db: Session = Depends(get_db),
):
    """Get paginated trade disclosure history for a trader."""
    t = db.query(Trader).filter(Trader.id == trader_id).first()
    if not t:
        raise HTTPException(404, f"Trader {trader_id} not found")

    trades = (
        db.query(Trade)
        .filter(Trade.trader_id == trader_id)
        .order_by(Trade.disclosure_date.desc())
        .offset(skip).limit(limit)
        .all()
    )

    result = []
    for trade in trades:
        out = TradeOut.model_validate(trade)
        out.trader_name = t.name
        if trade.disclosure_date and trade.trade_date:
            out.disclosure_delay_days = (trade.disclosure_date - trade.trade_date).days
        result.append(out)
    return result
