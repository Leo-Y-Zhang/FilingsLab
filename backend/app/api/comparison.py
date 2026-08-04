"""
Multi-Trader Comparison API
============================
Runs the simulation engine for multiple traders in parallel using the same
configuration and returns side-by-side metrics for comparison.
"""

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.config import get_settings
from app.core.limiter import limiter
from app.simulation.config import EngineConfig
from app.simulation.engine import run as sim_run
from app.schemas.comparison import ComparisonRequest, ComparisonResult, ComparisonEntry

router = APIRouter(prefix="/compare", tags=["Comparison"])
settings = get_settings()


@router.post("/", response_model=ComparisonResult)
@limiter.limit("10/minute")
def compare_traders(
    request: Request,
    response: Response,
    req: ComparisonRequest,
    db: Session = Depends(get_db),
):
    """
    Run simulations for multiple traders using identical configuration and
    return side-by-side performance metrics.

    Max {max_compare} traders per request.

    All simulations use:
    - Same delay_days, initial_capital, start/end dates
    - Proportional allocation, standard transaction costs
    - Midpoint value estimation for deterministic comparison

    Results include portfolio histories for chart overlay rendering.
    """.format(max_compare=settings.max_compare_traders)
    if len(req.trader_ids) > settings.max_compare_traders:
        raise HTTPException(
            422,
            f"Maximum {settings.max_compare_traders} traders per comparison request."
        )

    entries: list[ComparisonEntry] = []
    bench_ret_pct = None

    for trader_id in req.trader_ids:
        cfg = EngineConfig(
            trader_id=trader_id,
            initial_capital=req.initial_capital,
            delay_days=req.delay_days,
            allocation_strategy="proportional",
            transaction_cost=0.001,
            slippage=0.0005,
            value_estimation_method="midpoint",
            max_position_pct=0.20,
            start_date=req.start_date,
            end_date=req.end_date,
        )

        try:
            result = sim_run(db, cfg)
        except ValueError as e:
            raise HTTPException(422, f"Trader {trader_id}: {e}")
        except Exception as e:
            raise HTTPException(500, f"Simulation failed for trader {trader_id}: {e}")

        if bench_ret_pct is None and result.benchmark_return_pct is not None:
            bench_ret_pct = result.benchmark_return_pct

        entries.append(
            ComparisonEntry(
                trader_id=result.trader_id,
                name=result.trader_name,
                category=_get_category(db, trader_id),
                total_return_pct=result.total_return_pct,
                annualized_return_pct=result.annualized_return_pct,
                sharpe_ratio=result.sharpe_ratio,
                sortino_ratio=result.sortino_ratio,
                max_drawdown_pct=result.max_drawdown_pct,
                volatility_pct=result.volatility_pct,
                win_rate=result.win_rate,
                excess_return_pct=result.excess_return_pct,
                benchmark_return_pct=result.benchmark_return_pct,
                trade_count=result.trade_count,
                executed_trade_count=result.executed_trade_count,
                portfolio_history=result.portfolio_history,
            )
        )

    if not entries:
        raise HTTPException(422, "No valid simulation results returned.")

    best_id = max(entries, key=lambda e: e.total_return_pct).trader_id
    best_sharpe_id = max(entries, key=lambda e: e.sharpe_ratio).trader_id
    best_sortino_id = max(entries, key=lambda e: e.sortino_ratio).trader_id

    return ComparisonResult(
        delay_days=req.delay_days,
        initial_capital=req.initial_capital,
        benchmark_return_pct=bench_ret_pct,
        entries=entries,
        best_trader_id=best_id,
        best_sharpe_trader_id=best_sharpe_id,
        best_sortino_trader_id=best_sortino_id,
    )


def _get_category(db: Session, trader_id: int) -> str:
    from app.models.trader import Trader
    t = db.query(Trader).filter(Trader.id == trader_id).first()
    return t.category if t else "unknown"


