"""Unified market data access — PostgreSQL when configured, else demo memory."""

from __future__ import annotations

import hashlib
from datetime import date

import numpy as np
import pandas as pd
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.exceptions import HalalQuantError
from app.data import sample_data
from app.market_data.benchmarks import benchmark_symbols
from app.market_data.persistence import (
    candle_fingerprints,
    candles_to_dataframe,
    fetch_candles,
    list_db_symbols,
    symbol_date_range,
)


class SymbolNotFoundError(KeyError):
    pass


def list_all_symbols() -> list[str]:
    """Every stored symbol, including registered benchmarks / index proxies (raw, unfiltered)."""
    if settings.database_enabled and SessionLocal is not None:
        with SessionLocal() as session:
            return sorted(set(list_db_symbols(session)))
    return list(sample_data.SYMBOLS)


def list_universe_symbols() -> list[str]:
    """The tradable equity universe: every stored symbol except registered benchmarks (M14 Phase 1.1).

    Benchmarks stay readable by name (``get_history_dataframe``); they are just never part of any
    equity scan, breadth sample, or valuation universe.
    """
    benchmarks = benchmark_symbols()
    return list(dict.fromkeys(s for s in list_all_symbols() if s.upper() not in benchmarks))


def symbol_metadata(symbol: str) -> dict:
    symbol = symbol.upper()
    if settings.database_enabled and SessionLocal is not None:
        with SessionLocal() as session:
            start, end = symbol_date_range(session, symbol)
            if start:
                count = len(fetch_candles(session, symbol))
                return {
                    "symbol": symbol,
                    "source": "postgresql",
                    "is_synthetic": False,
                    "shariah_status": "UNVERIFIED",
                    "candle_count": count,
                    "date_range": {"start": start.isoformat(), "end": end.isoformat() if end else None},
                }
    if symbol in sample_data.HISTORIES:
        df = sample_data.HISTORIES[symbol]
        return {
            "symbol": symbol,
            "source": "synthetic demo data",
            "is_synthetic": True,
            "shariah_status": "UNVERIFIED",
            "candle_count": len(df),
            "date_range": {
                "start": df["date"].iloc[0].strftime("%Y-%m-%d"),
                "end": df["date"].iloc[-1].strftime("%Y-%m-%d"),
            },
        }
    raise SymbolNotFoundError(symbol)


def get_history_dataframe(
    symbol: str,
    *,
    limit: int = 260,
    start: date | None = None,
    end: date | None = None,
    session: Session | None = None,
) -> pd.DataFrame:
    symbol = symbol.upper()
    limit = min(max(limit, 60), 5000)

    if settings.database_enabled:
        own = session is None
        db = session or SessionLocal()
        if db is None:
            raise HalalQuantError("Database not available", status_code=503, code="database_error")
        try:
            candles = fetch_candles(db, symbol, start=start, end=end, limit=None)
            if not candles:
                raise SymbolNotFoundError(symbol)
            df = candles_to_dataframe(candles)
            if start or end:
                pass
            else:
                df = df.tail(limit)
            return df[["date", "open", "high", "low", "close", "volume"]]
        finally:
            if own and db is not None:
                db.close()

    if symbol not in sample_data.HISTORIES:
        raise SymbolNotFoundError(symbol)
    df = sample_data.HISTORIES[symbol]
    return df.tail(limit).reset_index(drop=True)


def history_upto(symbol: str, *, end: date | None = None) -> pd.DataFrame:
    """All OHLCV bars for ``symbol`` with trading date <= ``end`` (all bars when ``end`` is None).

    Unlike ``get_history_dataframe`` this never truncates to the latest N bars. Callers that need a
    lookback must slice explicitly as of a session (M14 Phase 1, finding B-01).
    """
    symbol = symbol.upper()
    if settings.database_enabled:
        db = SessionLocal() if SessionLocal is not None else None
        if db is None:
            raise HalalQuantError("Database not available", status_code=503, code="database_error")
        try:
            candles = fetch_candles(db, symbol, end=end, limit=None)
            if not candles:
                raise SymbolNotFoundError(symbol)
            df = candles_to_dataframe(candles)
        finally:
            db.close()
    else:
        if symbol not in sample_data.HISTORIES:
            raise SymbolNotFoundError(symbol)
        df = sample_data.HISTORIES[symbol]
    out = df[["date", "open", "high", "low", "close", "volume"]].copy()
    out["date"] = pd.to_datetime(out["date"])
    if end is not None:
        out = out[out["date"].dt.date <= end]
    return out.sort_values("date").reset_index(drop=True)


def get_history_window(symbol: str, *, end: date, lookback_bars: int = 520) -> pd.DataFrame:
    """The latest ``lookback_bars`` bars with trading date <= ``end``. Never sees later bars."""
    df = history_upto(symbol, end=end)
    return df.tail(max(int(lookback_bars), 1)).reset_index(drop=True)


def get_next_bar(symbol: str, after: date) -> pd.Series | None:
    """First bar strictly after ``after`` for ``symbol``, or None if the symbol has no later bar."""
    df = history_upto(symbol)
    nxt = df[df["date"].dt.date > after]
    return None if nxt.empty else nxt.iloc[0]


def _frame_fingerprint(df: pd.DataFrame) -> tuple:
    """Identity of an in-memory frame: bar count, first/last date, and a digest of dates and OHLCV values."""
    dates = pd.to_datetime(df["date"])
    digest = hashlib.blake2b(digest_size=16)
    digest.update(np.ascontiguousarray(dates.to_numpy().astype("datetime64[ns]").astype("int64")).tobytes())
    for col in ("open", "high", "low", "close", "volume"):
        if col in df.columns:
            digest.update(np.ascontiguousarray(df[col].to_numpy(dtype="float64")).tobytes())
    return (len(df), dates.min().date().isoformat(), dates.max().date().isoformat(), digest.hexdigest())


def bar_fingerprints(symbols: list[str]) -> dict[str, tuple]:
    """Content-sensitive identity of each symbol's stored bars, in the active storage mode.

    Database mode: one grouped aggregate query (no candles loaded). Memory mode: a digest of the frame.
    Symbols with no stored bars are omitted. Changing any stored bar changes that symbol's fingerprint.
    Used to key caches derived from stored bars so they can never go stale (M14 Phase 1.1).
    """
    wanted = sorted({s.upper() for s in symbols})
    if settings.database_enabled and SessionLocal is not None:
        with SessionLocal() as session:
            return candle_fingerprints(session, wanted)
    return {
        sym: _frame_fingerprint(sample_data.HISTORIES[sym])
        for sym in wanted
        if sym in sample_data.HISTORIES and len(sample_data.HISTORIES[sym]) > 0
    }


def iter_symbol_histories() -> list[tuple[str, pd.DataFrame]]:
    items: list[tuple[str, pd.DataFrame]] = []
    for sym in list_universe_symbols():
        try:
            items.append((sym, get_history_dataframe(sym, limit=520)))
        except (SymbolNotFoundError, ValueError):
            continue
    return items


def last_close_prices() -> dict[str, float]:
    prices: dict[str, float] = {}
    for sym in list_universe_symbols():
        try:
            df = get_history_dataframe(sym, limit=5)
            prices[sym] = float(df.close.iloc[-1])
        except (SymbolNotFoundError, ValueError):
            continue
    return prices