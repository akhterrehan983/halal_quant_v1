from __future__ import annotations

from decimal import Decimal

import pandas as pd

from app.portfolio.money import D
from app.strategies.indicators import add_indicators


def atr_stop(entry: Decimal, atr: float | None, multiplier: float = 2.0) -> Decimal | None:
    if atr is None or pd.isna(atr) or atr <= 0:
        return None
    stop = D(entry) - D(atr * multiplier)
    return stop if stop > 0 else None


def structure_stop(df: pd.DataFrame, lookback: int = 20, *, eval_index: int = -1) -> Decimal | None:
    if df is None or len(df) < lookback:
        return None
    idx = len(df) + eval_index if eval_index < 0 else eval_index
    window = df.iloc[max(0, idx - lookback + 1) : idx + 1]
    if window.empty:
        return None
    low = float(window["low"].min())
    return D(low)


def resolve_stop_reference(
    entry: Decimal,
    signal_stop: float | None,
    df: pd.DataFrame | None,
    *,
    atr_multiplier: float = 2.0,
) -> tuple[Decimal | None, str]:
    if signal_stop and signal_stop > 0 and signal_stop < float(entry):
        return D(signal_stop), "signal_reference"
    if df is not None and len(df) >= 60:
        x = add_indicators(df)
        row = x.iloc[-1]
        atr_val = float(row.atr14) if pd.notna(row.atr14) else None
        atr_s = atr_stop(entry, atr_val, atr_multiplier)
        if atr_s is not None and atr_s < entry:
            return atr_s, "atr"
        struct = structure_stop(df)
        if struct is not None and struct < entry:
            return struct, "structure"
    return None, "missing"


def trailing_stop_update(current_stop: Decimal, candidate: Decimal) -> Decimal:
    """Long-only: stop never moves down."""
    if candidate <= current_stop:
        return current_stop
    return candidate