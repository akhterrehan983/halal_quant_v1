"""Cross-section breadth — no fabricated index breadth."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import date

import pandas as pd

from app.market_data.benchmarks import benchmark_symbols
from app.market_data.repository import (
    SymbolNotFoundError,
    bar_fingerprints,
    get_history_window,
    iter_symbol_histories,
    list_universe_symbols,
)
from app.strategies.indicators import add_indicators

# As-of breadth memo, active only inside ``breadth_cache_scope`` (one backtest run). Separate from the
# benchmark proxy cache. Nothing survives the scope, so results can never depend on earlier runs.
_SCOPED_CACHE: ContextVar[dict | None] = ContextVar("breadth_scoped_cache", default=None)


@contextmanager
def breadth_cache_scope() -> Iterator[None]:
    """Memoise as-of breadth for the duration of the block (M14 F-4). Nested scopes share the outer memo.

    Key: (as-of date, sorted equity universe with benchmarks excluded, each equity's stored-bar
    fingerprint). Any added, removed, or edited equity bar, any universe change, and any benchmark
    registry change therefore misses and recomputes. Latest-bar breadth (``as_of_date=None``) is never cached.
    """
    if _SCOPED_CACHE.get() is not None:
        yield
        return
    token = _SCOPED_CACHE.set({})
    try:
        yield
    finally:
        _SCOPED_CACHE.reset(token)


def _slice_on_or_before(df: pd.DataFrame, as_of_date: date) -> pd.DataFrame:
    mask = pd.to_datetime(df["date"]).dt.date <= as_of_date
    return df.loc[mask].sort_values("date").reset_index(drop=True)


def _cache_key(as_of_date: date) -> tuple:
    benchmarks = benchmark_symbols()
    equities = sorted({s.upper() for s in list_universe_symbols() if s.upper() not in benchmarks})
    fingerprints = bar_fingerprints(equities)
    return (as_of_date, tuple(equities), tuple(sorted(fingerprints.items())))


def compute_universe_breadth(as_of_date: date | None = None) -> dict:
    """Fraction of universe symbols above SMA50 as of ``as_of_date`` (or latest if None)."""
    cache = _SCOPED_CACHE.get()
    if cache is None or as_of_date is None:
        return _compute_universe_breadth(as_of_date)
    key = _cache_key(as_of_date)
    if key not in cache:
        cache[key] = _compute_universe_breadth(as_of_date)
    return dict(cache[key])


def _compute_universe_breadth(as_of_date: date | None) -> dict:
    above_sma50 = 0
    total = 0
    skipped_insufficient = 0
    # Registered benchmarks / index proxies are never breadth constituents (M14 Phase 1.1, F-2).
    benchmarks = benchmark_symbols()
    if as_of_date is None:
        pairs = [(sym, df) for sym, df in iter_symbol_histories() if sym.upper() not in benchmarks]
    else:
        # Point-in-time: 520 bars ending at ``as_of_date``, not the latest 520 bars (M14 B-01).
        pairs = []
        for sym in list_universe_symbols():
            if sym.upper() in benchmarks:
                continue
            try:
                pairs.append((sym, get_history_window(sym, end=as_of_date, lookback_bars=520)))
            except (SymbolNotFoundError, ValueError):
                continue
    for _symbol, df in pairs:
        work = _slice_on_or_before(df, as_of_date) if as_of_date is not None else df.sort_values("date").reset_index(drop=True)
        if len(work) < 60:
            skipped_insufficient += 1
            continue
        x = add_indicators(work)
        row = x.iloc[-1]
        if pd.isna(row.get("sma50")):
            ema50 = float(row.ema50)
            price = float(row.close)
            if price > ema50:
                above_sma50 += 1
        else:
            if float(row.close) > float(row.sma50):
                above_sma50 += 1
        total += 1
    ratio = above_sma50 / total if total else None
    return {
        "symbols_sampled": total,
        "symbols_skipped_insufficient": skipped_insufficient,
        "pct_above_sma50": round(ratio, 4) if ratio is not None else None,
        "as_of_date": as_of_date.isoformat() if as_of_date else None,
        "approximate": True,
        "disclaimer": "Breadth from eligible research universe, not official NSE breadth.",
    }
