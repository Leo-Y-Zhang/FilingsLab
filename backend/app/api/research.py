import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.limiter import limiter
from app.core.logsafe import scrub
from app.research.experiments import run_all_experiments
from app.research.alpha_decay import compute_alpha_decay, TraderNotFoundError
from app.research.hypothesis import test_h1_excess_returns, test_h2_early_vs_late
from app.schemas.research import ExperimentsBundle, AlphaDecayResult, HypothesisTestResult

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/research", tags=["Research"])

# Each delay is a full simulation run, so an unbounded `delays` list was a
# free amplification factor: "1,1,1,..." x N cost N simulations per request.
_MAX_DELAYS     = 20
_MAX_DELAY_DAYS = 365


@router.get("/experiments", response_model=ExperimentsBundle)
@limiter.limit("5/minute")
def get_experiments(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    """
    Run all structured research experiments and return results.

    Experiment 1: Trader vs S&P 500 benchmark (1-day delay)
    Experiment 2: Return and risk-adjusted decay across delays [0, 3, 7, 14 days]
    Experiment 3: Proportional vs equal-weight allocation comparison

    Note: computation may take 10–60 seconds on first run.
    """
    try:
        return run_all_experiments(db)
    except Exception:
        logger.exception("Experiments failed")
        raise HTTPException(500, "Experiments failed; see server log.")


@router.get("/alpha-decay/{trader_id}", response_model=AlphaDecayResult)
@limiter.limit("20/minute")
def get_alpha_decay(
    request: Request,
    response: Response,
    trader_id: int,
    delays: str = Query(
        default=None,
        description="Comma-separated list of delays to test (e.g. '0,1,3,7,14'). "
                    "Defaults to platform-configured delays.",
    ),
    db: Session = Depends(get_db),
):
    """
    Compute how simulated excess return decays as execution delay increases.

    Returns one data point per delay with return, Sharpe, Sortino, excess return,
    and an interpolated half-life estimate (days until excess return halves).
    """
    parsed_delays = None
    if delays:
        try:
            parsed_delays = [int(d.strip()) for d in delays.split(",") if d.strip()]
        except ValueError:
            raise HTTPException(422, "Invalid delays format. Use comma-separated integers.")
        if len(parsed_delays) > _MAX_DELAYS:
            raise HTTPException(422, f"At most {_MAX_DELAYS} delays per request.")
        if any(d < 0 or d > _MAX_DELAY_DAYS for d in parsed_delays):
            raise HTTPException(422, f"Each delay must be between 0 and {_MAX_DELAY_DAYS} days.")
        parsed_delays = parsed_delays or None

    try:
        return compute_alpha_decay(db, trader_id, parsed_delays)
    except TraderNotFoundError as e:
        # Only the lookup means 404. A plain ValueError from anywhere below --
        # "No trades found", "start_date must precede end_date", "Simulation
        # produced no data points" -- is a computation that went wrong, and it
        # takes the same fixed-string path as any other unexpected failure.
        raise HTTPException(404, str(e))
    except Exception:
        logger.exception("Alpha decay computation failed for trader %s", trader_id)
        raise HTTPException(500, "Alpha decay computation failed; see server log.")


@router.get("/hypothesis/h1", response_model=HypothesisTestResult)
@limiter.limit("5/minute")
def hypothesis_h1(
    request: Request,
    response: Response,
    category: str = Query(default="politician"),
    db: Session = Depends(get_db),
):
    """
    Test H1: Do traders of a given category generate statistically significant
    excess returns relative to the market benchmark?

    One-sample t-test on daily portfolio returns minus benchmark daily return.
    """
    try:
        return test_h1_excess_returns(db, category)
    except ValueError as e:
        raise HTTPException(422, str(e))
    except Exception:
        logger.exception("H1 hypothesis test failed for category %r", scrub(category))
        raise HTTPException(500, "Hypothesis test failed; see server log.")


@router.get("/hypothesis/h2", response_model=HypothesisTestResult)
@limiter.limit("5/minute")
def hypothesis_h2(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    """
    Test H2: Does acting within 3 days of disclosure produce significantly
    higher returns than waiting 14 days?

    Paired t-test on return differences across traders.
    """
    try:
        return test_h2_early_vs_late(db)
    except ValueError as e:
        raise HTTPException(422, str(e))
    except Exception:
        logger.exception("H2 hypothesis test failed")
        raise HTTPException(500, "Hypothesis test failed; see server log.")
