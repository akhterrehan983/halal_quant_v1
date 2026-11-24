import pandas as pd

from app.features.pipeline import add_all_features


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Backward-compatible facade over feature pipeline."""
    return add_all_features(df)