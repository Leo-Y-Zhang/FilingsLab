"""
Application configuration via Pydantic Settings.
All values can be overridden by environment variables or a .env file.
"""

from functools import lru_cache
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "FilingsLab"
    app_version: str = "2.0.0"
    debug: bool = False

    # Database
    database_url: str = "postgresql://postgres:postgres@localhost:5432/filingslab"

    # CORS
    allowed_origins: list[str] = ["http://localhost:5173", "http://localhost:3000"]

    # ── API authentication ────────────────────────────────────────────────────
    # Shared operator token for every mutating and admin route. Empty means the
    # admin surface is DISABLED (503), never open — see app/core/security.py.
    api_token: str = ""

    # ── Rate limiting ─────────────────────────────────────────────────────────
    # Peers inside these networks may have their X-Real-IP / X-Forwarded-For
    # believed; everyone else is keyed on their real socket address. Defaults
    # cover the Docker bridge and loopback so the bundled nginx works, while a
    # caller reaching port 8000 directly from the internet cannot spoof a key.
    trusted_proxy_networks: list[str] = [
        "127.0.0.0/8",
        "10.0.0.0/8",
        "172.16.0.0/12",
        "192.168.0.0/16",
        "::1/128",
    ]

    # Risk-free rate (annual, decimal) for Sharpe / Sortino ratios
    risk_free_rate: float = 0.04

    # Monte Carlo defaults
    default_mc_runs: int = 500
    max_mc_runs: int = 2000

    # Alpha decay: delays to test (days)
    alpha_decay_delays: list[int] = [0, 1, 3, 5, 7, 10, 14, 21, 30, 45]

    # Ranking weights (must sum to 1.0)
    rank_w_return: float = 0.35
    rank_w_sharpe: float = 0.30
    rank_w_drawdown: float = 0.20
    rank_w_consistency: float = 0.15

    # Comparison: maximum traders per request
    max_compare_traders: int = 6

    # ── Signal engine thresholds ──────────────────────────────────────────────
    signal_min_score: float = 40.0      # only highlight signals above this score

    # ── Broker (Alpaca) — PAPER trading only by default ───────────────────────
    # Live order placement is HARD-DISABLED unless BOTH of these hold:
    #   alpaca_paper = False  AND  allow_live_trading == "I_UNDERSTAND_THE_RISK"
    # A single stray ALPACA_PAPER=false can never enable live trading on its own.
    alpaca_api_key: str = ""
    alpaca_secret_key: str = ""
    alpaca_paper: bool = True
    allow_live_trading: str = ""

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
