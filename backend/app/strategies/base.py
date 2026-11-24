from __future__ import annotations

from abc import ABC, abstractmethod

from app.strategies.context import StrategyContext
from app.strategies.schemas import StrategyResultModel


class BaseStrategy(ABC):
    strategy_id: str
    legacy_name: str
    description: str

    @property
    @abstractmethod
    def name(self) -> str:
        ...

    @property
    def required_features(self) -> set[str]:
        return {
            "close",
            "ema20",
            "ema50",
            "sma200",
            "rsi14",
            "atr14",
            "adx14",
            "return_3m",
            "return_6m",
            "relative_volume",
        }

    @abstractmethod
    def evaluate(self, context: StrategyContext) -> StrategyResultModel:
        ...