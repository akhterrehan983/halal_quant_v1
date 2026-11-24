import pandas as pd

from app.strategies.indicators import add_indicators


def benchmark_features(df: pd.DataFrame) -> pd.DataFrame:
    return add_indicators(df)