from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

import pandas as pd

from app.strategies.config import HorizonConfig, get_horizon_config


@dataclass
class StrategyContext:
    symbol: str
    ohlcv: pd.DataFrame
    features: pd.DataFrame
    row: pd.Series
    prev_row: pd.Series | None
    evaluation_date: date
    horizon: str
    regime: str | None = None
    benchmark_features: dict | None = None
    config: HorizonConfig = field(default_factory=lambda: get_horizon_config("swing"))

    @property
    def price(self) -> float:
        return float(self.row.close)

    def feature(self, name: str, default=None):
        val = self.row.get(name, default)
        if pd.isna(val):
            return default
        return val