"""Benchmark-relative returns (stock minus benchmark over same window)."""

from __future__ import annotations

from datetime import date

import pandas as pd

from app.regime.benchmark import ensure_benchmark_history


def _on_or_before(df: pd.DataFrame, as_of_date: date) -> pd.DataFrame:
    mask = pd.to_datetime(df["date"]).dt.date <= as_of_date
    return df.loc[mask].sort_values("date").reset_index(drop=True)


def aligned_relative_returns(
    stock_df: pd.DataFrame,
    *,
    windows: tuple[int, ...] = (21, 63, 126, 252),
    as_of_index: int = -1,
    as_of_date: date | None = None,
) -> dict[str, float | None]:
    stock = stock_df.sort_values("date").reset_index(drop=True)
    bench = ensure_benchmark_history().sort_values("date").reset_index(drop=True)
    if as_of_date is not None:
        stock = _on_or_before(stock, as_of_date)
        bench = _on_or_before(bench, as_of_date)
    merged = pd.merge(stock[["date", "close"]], bench[["date", "close"]], on="date", suffixes=("_s", "_b"))
    if merged.empty:
        return {f"rel_{w}d": None for w in windows}

    idx = len(merged) + as_of_index if as_of_index < 0 else as_of_index
    idx = max(0, min(idx, len(merged) - 1))
    out: dict[str, float | None] = {}
    for w in windows:
        if idx < w:
            out[f"rel_{w}d"] = None
            continue
        s0 = float(merged.iloc[idx - w].close_s)
        s1 = float(merged.iloc[idx].close_s)
        b0 = float(merged.iloc[idx - w].close_b)
        b1 = float(merged.iloc[idx].close_b)
        if s0 <= 0 or b0 <= 0:
            out[f"rel_{w}d"] = None
            continue
        stock_ret = s1 / s0 - 1
        bench_ret = b1 / b0 - 1
        out[f"rel_{w}d"] = round(stock_ret - bench_ret, 6)
    return out