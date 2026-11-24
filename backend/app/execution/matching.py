"""Deterministic next-session fill rules — no same-bar signal close fill."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pandas as pd

from app.execution.schemas import OrderType, PaperOrder
from app.portfolio.money import D
from app.market_data.repository import SymbolNotFoundError, get_history_dataframe


def next_session_index(df: pd.DataFrame, signal_date: date | None) -> int | None:
    if signal_date is None:
        return len(df) if len(df) > 0 else None
    dates = pd.to_datetime(df["date"]).dt.date
    for i, d in enumerate(dates):
        if d > signal_date:
            return i
    return None


def simulate_market_fill(order: PaperOrder, *, slippage_bps: int = 10) -> tuple[int, Decimal, date] | None:
    df = get_history_dataframe(order.symbol, limit=520)
    idx = next_session_index(df, order.signal_date)
    if idx is None:
        return None
    if order.signal_date:
        sig_idx = next((i for i, d in enumerate(pd.to_datetime(df["date"]).dt.date) if d == order.signal_date), None)
        if sig_idx is not None and idx <= sig_idx:
            return None
    row = df.iloc[idx]
    open_px = D(row["open"])
    slip = open_px * D(slippage_bps) / D(10000)
    fill_px = open_px + slip if order.side.value == "BUY" else open_px - slip
    trade_date = pd.to_datetime(row["date"]).date()
    return order.quantity, fill_px.quantize(Decimal("0.01")), trade_date


def simulate_limit_fill(order: PaperOrder) -> tuple[int, Decimal, date] | None:
    if order.limit_price is None:
        return None
    df = get_history_dataframe(order.symbol, limit=520)
    idx = next_session_index(df, order.signal_date)
    if idx is None:
        return None
    row = df.iloc[idx]
    limit = D(order.limit_price)
    trade_date = pd.to_datetime(row["date"]).date()
    low = D(row["low"])
    open_px = D(row["open"])
    if order.side.value == "BUY":
        if open_px <= limit:
            return order.quantity, min(open_px, limit), trade_date
        if low <= limit:
            return order.quantity, limit, trade_date
    else:
        high = D(row["high"])
        if open_px >= limit:
            return order.quantity, max(open_px, limit), trade_date
        if high >= limit:
            return order.quantity, limit, trade_date
    return None