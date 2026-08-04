"""
FilingsLab — FastAPI Application
============================
Intelligent platform for tracking, scoring, and acting on public trading disclosures.
Combines real-time STOCK Act / SEC Form-4 feed with backtesting and AI forecasting.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.core.config import get_settings
from app.core.database import engine, Base, SessionLocal
from app.core.limiter import limiter
from app.core.request_log import RequestLogMiddleware
from app.api import traders, rankings, simulation, research, comparison
from app.api import forecast as forecast_router
from app.api import feed as feed_router
import app.models.paper_portfolio  # noqa: F401 — ensure tables are created

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)
settings = get_settings()


def _background_seed():
    """
    Runs in a daemon thread: waits 10 s for the DB to settle, then tries
    real EDGAR seeding (slow, respects rate limits) with a synthetic fallback.
    """
    import threading
    threading.current_thread().name = "seeder"

    import time as _time
    _time.sleep(60)   # let SEC rate-limit window clear before hitting Archives

    from app.core.seed_data import seed_database
    with SessionLocal() as db:
        seed_database(db)


@asynccontextmanager
async def lifespan(app: FastAPI):
    import threading
    logger.info("Starting %s v%s", settings.app_name, settings.app_version)
    Base.metadata.create_all(bind=engine)

    t = threading.Thread(target=_background_seed, daemon=True)
    t.start()
    logger.info("Database seeder started in background thread.")

    # Start auto-trader loop (only runs when cfg.enabled = True)
    from app.services.auto_trader import start_background_loop
    start_background_loop()

    yield
    logger.info("Shutdown complete.")


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description=(
        "**FilingsLab**\n\n"
        "A quantitative research system for analysing whether publicly disclosed "
        "trading activity contains statistically exploitable signals.\n\n"
        "> ⚠️ **DISCLAIMER**: This platform is for **educational and research purposes "
        "only** and is not financial advice. Trading runs in **paper (simulated) mode by "
        "default**; live order placement is hard-disabled unless deliberately enabled."
    ),
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Applies the default per-IP limit to every route that has no explicit one.
app.add_middleware(SlowAPIMiddleware)

# Added last, so it is the OUTERMOST middleware and therefore also logs the
# 429s produced by the rate limiter above.
app.add_middleware(RequestLogMiddleware)

app.include_router(feed_router.router,     prefix="/api")
app.include_router(traders.router,         prefix="/api")
app.include_router(rankings.router,        prefix="/api")
app.include_router(simulation.router,      prefix="/api")
app.include_router(research.router,        prefix="/api")
app.include_router(comparison.router,      prefix="/api")
app.include_router(forecast_router.router, prefix="/api")


@app.get("/api/health", tags=["Health"])
def health():
    return {
        "status": "ok",
        "app": settings.app_name,
        "version": settings.app_version,
        "disclaimer": (
            "This platform is for educational and research purposes only. "
            "It does not provide financial advice or enable real trading."
        ),
    }
