"""Adjusted price calculations — separate from raw OHLCV storage."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import CorporateAction, OHLCVCandle


def apply_adjustments(
    df: pd.DataFrame,
    actions: list[CorporateAction],
) -> pd.DataFrame:
    """Return a copy with optional adjusted_close column; raw OHLCV unchanged in DB."""
    if not actions or df.empty:
        out = df.copy()
        out["adjusted_close"] = out["close"]
        return out

    out = df.copy().sort_values("date")
    factor = Decimal("1")
    # Multiplicative factors applied chronologically (simplified; document in architecture)
    adj_factors: dict[date, Decimal] = {}
    for action in sorted(actions, key=lambda a: a.effective_date):
        if action.factor is not None:
            factor *= Decimal(action.factor)
        elif action.ratio is not None and action.action_type in ("split", "bonus"):
            factor *= Decimal(action.ratio)
        adj_factors[action.effective_date] = factor

    closes = []
    running = Decimal("1")
    for row in out.itertuples():
        td = row.date.date() if hasattr(row.date, "date") else row.date
        if td in adj_factors:
            running = adj_factors[td]
        closes.append(float(Decimal(str(row.close)) * running))
    out["adjusted_close"] = closes
    return out


def fetch_corporate_actions(session: Session, symbol: str) -> list[CorporateAction]:
    return list(
        session.execute(
            select(CorporateAction)
            .where(CorporateAction.symbol == symbol.upper())
            .order_by(CorporateAction.effective_date)
        ).scalars()
    )


def load_candles_with_adjusted(
    session: Session,
    symbol: str,
    *,
    use_adjusted: bool = False,
) -> pd.DataFrame:
    candles = list(
        session.execute(
            select(OHLCVCandle)
            .where(OHLCVCandle.symbol == symbol.upper())
            .order_by(OHLCVCandle.trading_date)
        ).scalars()
    )
    rows = [
        {
            "date": pd.Timestamp(c.trading_date),
            "open": float(c.open),
            "high": float(c.high),
            "low": float(c.low),
            "close": float(c.close),
            "volume": int(c.volume),
        }
        for c in candles
    ]
    df = pd.DataFrame(rows)
    if use_adjusted:
        actions = fetch_corporate_actions(session, symbol)
        return apply_adjustments(df, actions)
    return df