"""Volatility: ATR, Bollinger, historical volatility."""

import numpy as np
import pandas as pd


def add_volatility_features(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    h, l, c = out["high"], out["low"], out["close"]
    prev_close = c.shift(1)
    tr = pd.concat([(h - l), (h - prev_close).abs(), (l - prev_close).abs()], axis=1).max(axis=1)
    out["atr14"] = tr.rolling(14).mean()
    if "sma20" not in out.columns:
        out["sma20"] = c.rolling(20).mean()
    out["std20"] = c.rolling(20).std()
    out["bb_lower"] = out["sma20"] - 2 * out["std20"]
    out["bb_upper"] = out["sma20"] + 2 * out["std20"]
    daily_ret = c.pct_change()
    out["hist_vol_20"] = daily_ret.rolling(20, min_periods=10).std() * np.sqrt(252)
    return out