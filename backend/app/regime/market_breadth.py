"""Cross-section breadth — no fabricated index breadth."""

from __future__ import annotations

from datetime import date

import pandas as pd

from app.market_data.repository import iter_symbol_histories
from app.strategies.indicators import add_indicators


def _slice_on_or_before(df: pd.DataFrame, as_of_date: date) -> pd.DataFrame:
    mask = pd.to_datetime(df["date"]).dt.date <= as_of_date
    return df.loc[mask].sort_values("date").reset_index(drop=True)


def compute_universe_breadth(as_of_date: date | None = None) -> dict:
    """Fraction of universe symbols above SMA50 as of ``as_of_date`` (or latest if None)."""
    above_sma50 = 0
    total = 0
    skipped_insufficient = 0
    for _symbol, df in iter_symbol_histories():
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