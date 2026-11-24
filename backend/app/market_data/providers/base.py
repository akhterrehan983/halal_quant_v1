from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date
from typing import Any


@dataclass
class CandleRecord:
    symbol: str
    exchange: str
    trading_date: date
    open: float
    high: float
    low: float
    close: float
    volume: int
    adjusted_close: float | None = None
    data_source: str = "unknown"
    is_synthetic: bool = False


class MarketDataProvider(ABC):
    """Provider interface for licensed, CSV, or demo data sources."""

    @abstractmethod
    def fetch_history(self, symbol: str, exchange: str = "NSE") -> list[CandleRecord]:
        raise NotImplementedError

    @abstractmethod
    def list_symbols(self) -> list[dict[str, Any]]:
        raise NotImplementedError