import numpy as np
import pandas as pd

from app.data.sample_data import make_history
from app.features.momentum import add_macd, add_rsi
from app.features.pipeline import add_all_features
from app.strategies.indicators import add_indicators


def test_add_indicators_matches_pipeline():
    df = make_history("FEAT", periods=300)
    a = add_indicators(df)
    b = add_all_features(df)
    for col in ("rsi14", "ema20", "atr14", "return_3m", "bb_lower", "relative_volume"):
        assert col in a.columns and col in b.columns
        assert np.allclose(a[col].dropna(), b[col].dropna(), rtol=1e-9, equal_nan=True)


def test_rsi_no_lookahead():
    close = pd.Series(np.linspace(100, 150, 100))
    rsi = add_rsi(close)
    assert rsi.iloc[-1] >= 50
    assert rsi.isna().sum() < len(rsi)


def test_macd_columns():
    close = pd.Series(np.linspace(100, 120, 80) + np.random.default_rng(1).normal(0, 0.5, 80))
    macd = add_macd(close)
    assert {"macd", "macd_signal", "macd_histogram"}.issubset(macd.columns)


def test_insufficient_history_does_not_crash():
    df = make_history("SHORT", periods=30)
    out = add_all_features(df)
    assert len(out) == 30