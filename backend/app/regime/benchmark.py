"""Benchmark series from repository or equal-weight universe proxy."""

from __future__ import annotations

from datetime import date

import pandas as pd

from app.data import sample_data
from app.market_data.repository import SymbolNotFoundError, get_history_dataframe, list_universe_symbols


def ensure_benchmark_history() -> pd.DataFrame:
    symbol = "NIFTY500_PROXY"
    try:
        return get_history_dataframe(symbol, limit=5000)
    except SymbolNotFoundError:
        pass
    if symbol in sample_data.HISTORIES:
        return sample_data.HISTORIES[symbol]
    return _build_equal_weight_proxy()


def _build_equal_weight_proxy() -> pd.DataFrame:
    symbols = list_universe_symbols()
    frames = []
    for sym in symbols:
        try:
            df = get_history_dataframe(sym, limit=5000)
            df = df[["date", "close"]].copy()
            df["ret"] = df["close"].pct_change()
            df["symbol"] = sym
            frames.append(df)
        except SymbolNotFoundError:
            continue
    if not frames:
        return sample_data.make_history("NIFTY500_PROXY", periods=520)
    merged = pd.concat(frames, ignore_index=True)
    avg_ret = merged.groupby("date")["ret"].mean()
    dates = pd.Series(avg_ret.index).sort_values()
    close = (1 + avg_ret.fillna(0)).cumprod() * 1000
    out = pd.DataFrame(
        {
            "date": dates.values,
            "open": close.values,
            "high": close.values * 1.005,
            "low": close.values * 0.995,
            "close": close.values,
            "volume": 1_000_000,
        }
    )
    sample_data.HISTORIES["NIFTY500_PROXY"] = out
    if "NIFTY500_PROXY" not in sample_data.SYMBOLS:
        sample_data.SYMBOLS.append("NIFTY500_PROXY")
    return out


def _filter_on_or_before(df: pd.DataFrame, as_of_date: date) -> pd.DataFrame:
    mask = pd.to_datetime(df["date"]).dt.date <= as_of_date
    return df.loc[mask].sort_values("date").reset_index(drop=True)


def benchmark_slice(
    as_of_index: int = -1,
    *,
    as_of_date: date | None = None,
) -> tuple[pd.DataFrame, int]:
    """Return benchmark rows up to index, optionally capped at calendar ``as_of_date``.

    When ``as_of_date`` is set, no bar after that date is visible — including for ``as_of_index=-1``.
    An empty frame is returned (idx -1) if nothing exists on or before ``as_of_date``.
    """
    df = ensure_benchmark_history().sort_values("date").reset_index(drop=True)
    if as_of_date is not None:
        df = _filter_on_or_before(df, as_of_date)
    if df.empty:
        return df, -1
    idx = len(df) + as_of_index if as_of_index < 0 else as_of_index
    idx = max(0, min(idx, len(df) - 1))
    return df.iloc[: idx + 1].copy(), idx