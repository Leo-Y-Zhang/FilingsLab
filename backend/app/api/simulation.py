from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.limiter import limiter
from app.schemas.simulation import SimulationConfig, SimulationResult, MonteCarloConfig, MonteCarloResult
from app.simulation.config import EngineConfig
from app.simulation.engine import run as sim_run
from app.simulation.monte_carlo import run_monte_carlo

router = APIRouter(prefix="/simulate", tags=["Simulation"])

_DISCLAIMER = (
    "DISCLAIMER: Results are a historical simulation for educational/research purposes only. "
    "They do not constitute financial advice or represent real investment returns."
)


@router.post("/", response_model=SimulationResult)
@limiter.limit("20/minute")
def run_simulation(
    request: Request,
    response: Response,
    cfg: SimulationConfig,
    db: Session = Depends(get_db),
):
    """
    Run a single portfolio simulation.

    Execution model: trades executed at disclosure_date + delay_days.
    NOT at trade_date.

    ---
    """ + _DISCLAIMER
    engine_cfg = EngineConfig(
        trader_id=cfg.trader_id,
        initial_capital=cfg.initial_capital,
        delay_days=cfg.delay_days,
        allocation_strategy=cfg.allocation_strategy.value,
        transaction_cost=cfg.transaction_cost,
        slippage=cfg.slippage,
        value_estimation_method=cfg.value_estimation_method.value,
        max_position_pct=cfg.max_position_pct,
        start_date=cfg.start_date,
        end_date=cfg.end_date,
    )
    try:
        return sim_run(db, engine_cfg)
    except ValueError as e:
        raise HTTPException(422, str(e))
    except Exception as e:
        raise HTTPException(500, f"Simulation failed: {e}")


@router.post("/monte-carlo", response_model=MonteCarloResult)
@limiter.limit("5/minute")
def run_mc(
    request: Request,
    response: Response,
    cfg: MonteCarloConfig,
    db: Session = Depends(get_db),
):
    """
    Run a Monte Carlo simulation with stochastic value range sampling.

    Each of the N runs independently samples trade values from their
    disclosed ranges and optionally perturbs the execution delay.

    Returns a full return distribution with confidence intervals.

    ---
    """ + _DISCLAIMER
    try:
        return run_monte_carlo(db, cfg)
    except ValueError as e:
        raise HTTPException(422, str(e))
    except Exception as e:
        raise HTTPException(500, f"Monte Carlo failed: {e}")
