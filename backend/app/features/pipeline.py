"""
Compose technical features in chronological order (no look-ahead in rolling windows).

Preserves legacy column names consumed by `evaluate_all`.
"""

import numpy as np
import pandas as pd

from app.features.momentum import add_momentum_features
from app.features.returns import add_return_features
from app.features.trend import add_trend_features
from app.features.volatility import add_volatility_features
from app.features.volume import add_volume_features


def add_all_features(df: pd.DataFrame) -> pd.DataFrame:
    x = df.copy().sort_values("date").reset_index(drop=True)
    x = add_trend_features(x)
    x = add_volatility_features(x)
    x = add_momentum_features(x)
    x = add_return_features(x)
    x = add_volume_features(x)
    return x.replace([np.inf, -np.inf], np.nan)