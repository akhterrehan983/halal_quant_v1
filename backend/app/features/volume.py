"""Volume features."""

import pandas as pd


def add_volume_features(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    v = out["volume"]
    out["volume_sma20"] = v.rolling(20).mean()
    out["relative_volume"] = v / out["volume_sma20"].replace(0, pd.NA)
    return out