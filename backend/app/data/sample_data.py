"""Deterministic synthetic OHLCV data for local development only."""
import numpy as np
import pandas as pd

SYMBOLS = ["TCS", "INFY", "RELIANCE", "HDFCBANK", "SUNPHARMA", "TATAMOTORS", "BEL", "COALINDIA"]


def make_history(symbol: str, periods: int = 520) -> pd.DataFrame:
    seed = sum(ord(c) for c in symbol)
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=periods)
    drift = 0.00035 + ((seed % 7) - 3) * 0.00008
    shocks = rng.normal(drift, 0.016, periods)
    # Add a mild regime shift and occasional pullbacks so the demo is not a straight line.
    shocks[int(periods * .35):int(periods * .48)] -= 0.0018
    shocks[int(periods * .72):int(periods * .78)] += 0.0012
    close = (100 + seed % 180) * np.exp(np.cumsum(shocks))
    open_ = close * (1 + rng.normal(0, 0.004, periods))
    high = np.maximum(open_, close) * (1 + rng.uniform(0.001, 0.018, periods))
    low = np.minimum(open_, close) * (1 - rng.uniform(0.001, 0.018, periods))
    volume = rng.integers(150_000, 2_500_000, periods).astype(float)
    # Create occasional volume expansion days.
    volume[rng.choice(periods, size=max(5, periods // 35), replace=False)] *= rng.uniform(1.5, 3.0)
    return pd.DataFrame({"date": dates, "open": open_, "high": high, "low": low, "close": close, "volume": volume})

HISTORIES = {symbol: make_history(symbol) for symbol in SYMBOLS}
