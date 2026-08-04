from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.analytics.ranking import compute_rankings
from app.schemas.trader import RankedTraderOut

router = APIRouter(prefix="/rankings", tags=["Rankings"])


@router.get("/", response_model=list[RankedTraderOut])
def get_rankings(
    category: str | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """
    Return traders ranked by composite performance score.

    Score = 0.35 × return + 0.30 × sharpe − 0.20 × drawdown + 0.15 × win_rate

    All metrics are min-max normalised across the current trader population.
    Performance computed using 1-day post-disclosure execution model.
    """
    ranked = compute_rankings(db)
    if category:
        ranked = [r for r in ranked if r.category == category.lower()]
    return ranked[:limit]
