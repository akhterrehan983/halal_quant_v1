"""Normalize raw CSV rows into canonical candle records."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

import pandas as pd

_COLUMN_ALIASES = {
    "symbol": {"symbol", "ticker", "scrip", "sym"},
    "date": {"date", "trading_date", "trade_date", "datetime", "timestamp"},
    "open": {"open", "o"},
    "high": {"high", "h"},
    "low": {"low", "l"},
    "close": {"close", "c", "last", "adj close", "adj_close", "adjusted_close"},
    "volume": {"volume", "vol", "qty", "quantity"},
}


def _canonical_name(name: str) -> str | None:
    key = re.sub(r"[^a-z0-9]+", "_", name.strip().lower()).strip("_")
    for canonical, aliases in _COLUMN_ALIASES.items():
        if key in aliases or key.replace("_", " ") in aliases or key == canonical:
            return canonical
    if key in ("adjclose",):
        return "close"
    return None


def normalize_column_names(columns: list[str]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for col in columns:
        canon = _canonical_name(col)
        if canon and canon not in mapping.values():
            mapping[col] = canon
    return mapping


def normalize_symbol(value: Any, default: str | None = None) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        if not default:
            raise ValueError("Symbol is required for each row or as filename default")
        return default.upper().strip()
    return str(value).upper().strip()


def parse_trading_date(value: Any) -> pd.Timestamp:
    ts = pd.to_datetime(value, errors="coerce", utc=False)
    if pd.isna(ts):
        raise ValueError(f"Invalid date: {value!r}")
    return ts.normalize()


def read_csv_normalized(
    content: bytes,
    *,
    default_symbol: str | None = None,
    max_rows: int = 500_000,
) -> pd.DataFrame:
    """Read CSV bytes and return a normalized DataFrame with canonical columns."""
    buffer = pd.io.common.BytesIO(content)
    # Sniff delimiter from first line when possible
    try:
        df = pd.read_csv(buffer, nrows=max_rows)
    except pd.errors.EmptyDataError as exc:
        raise ValueError("CSV file is empty") from exc

    if df.empty:
        raise ValueError("CSV file contains no data rows")

    rename_map = normalize_column_names(list(df.columns))
    missing_required = {"date", "open", "high", "low", "close", "volume"} - set(rename_map.values())
    if missing_required:
        raise ValueError(f"Missing required columns: {', '.join(sorted(missing_required))}")

    df = df.rename(columns={k: v for k, v in rename_map.items()})
    if "symbol" not in df.columns:
        if not default_symbol:
            raise ValueError("CSV has no symbol column; use single-symbol filename or add symbol column")
        df["symbol"] = default_symbol

    df["symbol"] = df["symbol"].apply(lambda v: normalize_symbol(v, default_symbol))
    df["date"] = df["date"].apply(parse_trading_date)

    for col in ("open", "high", "low", "close"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["volume"] = pd.to_numeric(df["volume"], errors="coerce")
    df["volume"] = df["volume"].fillna(0).astype(int)

    if "adjusted_close" not in df.columns and "adj_close" in df.columns:
        df["adjusted_close"] = pd.to_numeric(df["adj_close"], errors="coerce")

    return df