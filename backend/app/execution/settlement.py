from __future__ import annotations

from datetime import timedelta

import pandas as pd

from app.execution import store
from app.execution.schemas import SettlementRecord
from app.execution.ownership import settle_holding


def settlement_date(trade_date, t_plus: int = 1):
    if hasattr(trade_date, "date"):
        trade_date = trade_date.date() if callable(getattr(trade_date, "date", None)) else trade_date
    # business days approximate: add t_plus bdays
    ts = pd.Timestamp(trade_date)
    return (ts + pd.offsets.BDay(t_plus)).date()


def process_settlements(as_of=None) -> list[SettlementRecord]:
    as_of = as_of or pd.Timestamp.today().date()
    completed: list[SettlementRecord] = []
    for sett in store.list_pending_settlements():
        if sett.settlement_date <= as_of and sett.status == "PENDING":
            if store.idempotent_settlement(sett.settlement_id):
                sett.status = "SETTLED"
                sett.cash_settled = True
                sett.securities_settled = True
                store.update_settlement(sett)
                settle_holding(sett.symbol, store.order_sleeve(sett.order_id))
                completed.append(sett)
    return completed