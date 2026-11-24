"""Unified market data access — PostgreSQL when configured, else demo memory."""

from __future__ import annotations

from datetime import date

import pandas as pd
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.exceptions import HalalQuantError
from app.data import sample_data
from app.market_data.persistence import candles_to_dataframe, fetch_candles, list_db_symbols, symbol_date_range


class SymbolNotFoundError(KeyError):
    pass


def list_universe_symbols() -> list[str]:
    if settings.database_enabled and SessionLocal is not None:
        with SessionLocal() as session:
            return sorted(set(list_db_symbols(session)))
    return list(sample_data.SYMBOLS)


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