"""Return features (no look-ahead)."""

import pandas as pd


def add_return_features(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    c = out["close"]
    out["return_1m"] = c.pct_change(21)
    out["return_3m"] = c.pct_change(63)
    out["return_6m"] = c.pct_change(126)
    out["return_12m"] = c.pct_change(252)
    out["daily_return"] = c.pct_change()
    return out