"""Data quality reports per symbol."""

from __future__ import annotations

from datetime import date

import pandas as pd

from app.core.config import settings
from app.core.database import SessionLocal
from app.market_data.persistence import fetch_candles, symbol_date_range
from app.market_data.repository import get_history_dataframe, list_universe_symbols
from app.market_data.validation import detect_outliers, validate_dataframe


def quality_report_for_symbol(symbol: str) -> dict:
    symbol = symbol.upper()
    try:
        df = get_history_dataframe(symbol, limit=5000)
    except KeyError:
        return {"symbol": symbol, "status": "not_found"}
    df = df.copy()
    df["symbol"] = symbol
    _, report = validate_dataframe(df)
    return {
        "symbol": symbol,
        "status": "ok",
        "candle_count": len(df),
        "date_range": {
            "start": df["date"].iloc[0].strftime("%Y-%m-%d") if len(df) else None,
            "end": df["date"].iloc[-1].strftime("%Y-%m-%d") if len(df) else None,
        },
        "validation": report.to_summary_dict(),
        "missing_sessions": report.missing_sessions.get(symbol, []),
        "missing_sessions_approximate": report.missing_sessions_approximate,
        "warnings": [w.model_dump() for w in report.warnings[:50]],
        "errors": [e.model_dump() for e in report.issues[:50]],
        "data_source": "postgresql" if settings.database_enabled else "demo_memory",
    }


def quality_report_universe() -> dict:
    symbols = list_universe_symbols()
    return {"symbols": [quality_report_for_symbol(s) for s in symbols], "total": len(symbols)}