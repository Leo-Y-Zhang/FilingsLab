from pydantic import BaseModel, Field
from typing import Optional


class ForecastPoint(BaseModel):
    date: str
    open: float
    high: float
    low: float
    close: float


class ForecastResult(BaseModel):
    source: str             # "kronos" | "cache"
    model: str
    device: str
    symbol: str
    predictions: list[ForecastPoint]


class HistoricalPoint(BaseModel):
    date: str
    open: float
    high: float
    low: float
    close: float


class KronosStatus(BaseModel):
    available: bool
    model: str
    device: str
    gpu: Optional[str]
    kronos_lib_path: str
    setup_required: bool
    setup_instructions: Optional[str]
