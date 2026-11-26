"""Benchmark series from repository or equal-weight universe proxy.

M14 Phase 1.1 (F-1): building the proxy has no side effects. It never adds the proxy to the stored
symbol list or to the history store, so the tradable universe cannot change depending on whether (or
in which order) earlier runs triggered the lazy build. The proxy is a pure function of the stored
equity histories and is cached by a content fingerprint of those inputs (symbols and their stored bars,
in both database and memory mode), so it can neither depend on run order nor go stale.
"""

from __future__ import annotations

from datetime import date

import pandas as pd

from app.data import sample_data
from app.market_data.benchmarks import DEFAULT_BENCHMARK_SYMBOL
from app.market_data.repository import (
    SymbolNotFoundError,
    bar_fingerprints,
    get_history_dataframe,
    list_universe_symbols,
)

# Latest proxy only; keyed by the fingerprint of its inputs, so changed data forces a rebuild.
_PROXY_CACHE: dict[tuple, pd.DataFrame] = {}


def clear_benchmark_cache() -> None:
    _PROXY_CACHE.clear()


def _inputs_fingerprint(symbols: list[str]) -> tuple:
    """Identity of everything the proxy is computed from: which symbols have bars, and those bars.

    The storage mode (database or memory) is decided inside ``repository.bar_fingerprints``; this
    module deliberately reads no settings. Symbols with no bars are not proxy inputs and are omitted.
    Both modes fingerprint bar content, so a changed bar with an identical symbol set rebuilds the proxy.
    """
    ordered = sorted({s.upper() for s in symbols})
    prints = bar_fingerprints(ordered)
    return tuple((sym, prints[sym]) for sym in ordered if sym in prints)


def ensure_benchmark_history() -> pd.DataFrame:
    """A stored benchmark series if one exists under the registered symbol, else the equal-weight proxy."""
    try:
        return get_history_dataframe(DEFAULT_BENCHMARK_SYMBOL, limit=5000)
    except SymbolNotFoundError:
        pass
    symbols = list_universe_symbols()  # equity universe: registered benchmarks are excluded
    key = _inputs_fingerprint(symbols)
    cached = _PROXY_CACHE.get(key)
    if cached is None:
        cached = _build_equal_weight_proxy(symbols)
        _PROXY_CACHE.clear()
        _PROXY_CACHE[key] = cached
    return cached.copy()


def _build_equal_weight_proxy(symbols: list[str]) -> pd.DataFrame:
    frames = []
    for sym in sorted(symbols):  # fixed order: the result must not depend on list order
        try:
            df = get_history_dataframe(sym, limit=5000)
            df = df[["date", "close"]].copy()
            df["ret"] = df["close"].pct_change()
            df["symbol"] = sym
            frames.append(df)
        except SymbolNotFoundError:
            continue
    if not frames:
        return sample_data.make_history(DEFAULT_BENCHMARK_SYMBOL, periods=520)
    merged = pd.concat(frames, ignore_index=True)
    avg_ret = merged.groupby("date")["ret"].mean()
    dates = pd.Series(avg_ret.index).sort_values()
    close = (1 + avg_ret.fillna(0)).cumprod() * 1000
    return pd.DataFrame(
        {
            "date": dates.values,
            "open": close.values,
            "high": close.values * 1.005,
            "low": close.values * 0.995,
            "close": close.values,
            "volume": 1_000_000,
        }
    )


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
