from datetime import date
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class MarketRegimeLabel(str, Enum):
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    SIDEWAYS = "SIDEWAYS"
    HIGH_VOLATILITY = "HIGH_VOLATILITY"
    MIXED = "MIXED"


class RegimeClassification(BaseModel):
    regime: MarketRegimeLabel
    confidence: float = Field(ge=0, le=1)
    as_of_date: date
    benchmark_symbol: str
    factors: dict[str, Any] = Field(default_factory=dict)
    observations: list[str] = Field(default_factory=list)
    data_quality: str = "ok"
    disclaimer: str | None = None