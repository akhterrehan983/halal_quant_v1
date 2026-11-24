"""Extensible correlation risk — warnings only in M5."""

from __future__ import annotations

import pandas as pd


def rolling_return_correlation(series_a: pd.Series, series_b: pd.Series, window: int = 63) -> float | None:
    if len(series_a) < window + 5 or len(series_b) < window + 5:
        return None
    ra = series_a.pct_change().tail(window).dropna()
    rb = series_b.pct_change().tail(window).dropna()
    idx = ra.index.intersection(rb.index)
    if len(idx) < window // 2:
        return None
    return float(ra.loc[idx].corr(rb.loc[idx]))


def correlated_pairs(symbols: list[str], histories: dict[str, pd.DataFrame], threshold: float = 0.65) -> list[tuple[str, str, float]]:
    pairs: list[tuple[str, str, float]] = []
    for i, a in enumerate(symbols):
        for b in symbols[i + 1 :]:
            da = histories.get(a)
            db = histories.get(b)
            if da is None or db is None:
                continue
            ca = da.set_index("date")["close"]
            cb = db.set_index("date")["close"]
            corr = rolling_return_correlation(ca, cb)
            if corr is not None and corr >= threshold:
                pairs.append((a, b, corr))
    return pairs