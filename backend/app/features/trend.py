"""Trend moving averages and slopes."""

import pandas as pd


def add_trend_features(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    c = out["close"]
    out["ema20"] = c.ewm(span=20, adjust=False).mean()
    out["ema50"] = c.ewm(span=50, adjust=False).mean()
    out["sma50"] = c.rolling(50, min_periods=20).mean()
    out["sma100"] = c.rolling(100, min_periods=30).mean()
    out["sma200"] = c.rolling(200, min_periods=50).mean()
    out["sma20"] = c.rolling(20).mean()
    out["ema20_slope"] = out["ema20"].diff(5) / 5
    out["ema50_slope"] = out["ema50"].diff(5) / 5
    out["high_20"] = out["high"].shift(1).rolling(20).max()
    out["high_55"] = out["high"].shift(1).rolling(55).max()
    out["low_20"] = out["low"].shift(1).rolling(20).min()
    out["high_52w"] = out["high"].rolling(252, min_periods=60).max()
    out["low_52w"] = out["low"].rolling(252, min_periods=60).min()
    return out