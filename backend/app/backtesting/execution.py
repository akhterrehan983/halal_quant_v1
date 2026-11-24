from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pandas as pd

from app.backtesting.data import next_session_row
from app.market_data.repository import get_history_dataframe
from app.portfolio.money import D


def fill_market_next_session(symbol: str, signal_date: date, slippage_bps: int) -> tuple[Decimal, date] | None:
    df = get_history_dataframe(symbol, limit=520)
    row = next_session_row(df, signal_date)
    if row is None:
        return None
    open_px = D(row["open"])
    fill = open_px * (D(1) + D(slippage_bps) / D(10000))
    td = pd.to_datetime(row["date"]).date()
    if td <= signal_date:
        return None
    return fill.quantize(Decimal("0.01")), td


def earliest_sell_date(entry_date: date, settlement_t_plus: int = 1) -> date:
    ts = pd.Timestamp(entry_date) + pd.offsets.BDay(settlement_t_plus + 2)
    return ts.date()


def exit_signal_price(symbol: str, as_of: date) -> Decimal | None:
    df = get_history_dataframe(symbol, limit=520)
    sub = df[pd.to_datetime(df["date"]).dt.date <= as_of]
    if sub.empty:
        return None
    return D(sub.iloc[-1]["close"])