from __future__ import annotations

from datetime import date

import pandas as pd

from app.market_data.repository import get_history_dataframe, iter_symbol_histories


def slice_as_of(df: pd.DataFrame, as_of: date) -> pd.DataFrame:
    x = df.copy()
    x["_d"] = pd.to_datetime(x["date"]).dt.date
    return x[x["_d"] <= as_of].drop(columns="_d")


def index_as_of(df: pd.DataFrame, as_of: date) -> int:
    s = slice_as_of(df, as_of)
    if s.empty:
        return -1
    return len(s) - 1


def trading_dates(symbols: list[str], start: date, end: date) -> list[date]:
    all_dates: set[date] = set()
    for sym in symbols:
        try:
            df = get_history_dataframe(sym, limit=2000)
        except Exception:
            continue
        dts = pd.to_datetime(df["date"]).dt.date
        all_dates.update(d for d in dts if start <= d <= end)
    return sorted(all_dates)


def next_session_row(df: pd.DataFrame, signal_date: date) -> pd.Series | None:
    dts = pd.to_datetime(df["date"]).dt.date
    for i, d in enumerate(dts):
        if d > signal_date:
            return df.iloc[i]
    return None