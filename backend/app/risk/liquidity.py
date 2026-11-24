from __future__ import annotations

from decimal import Decimal

import pandas as pd

from app.portfolio.money import D


def average_daily_volume(df: pd.DataFrame, window: int = 20) -> float | None:
    if df is None or len(df) < window:
        return None
    vol = df["volume"].tail(window)
    if vol.isna().all():
        return None
    return float(vol.mean())


def liquidity_check(
    quantity: int,
    entry_price: Decimal,
    df: pd.DataFrame | None,
    max_adv_participation_pct: Decimal,
) -> tuple[bool, list[str], dict]:
    warnings: list[str] = []
    if df is None or len(df) < 20:
        return False, ["Missing volume history — conservative reject"], {"adv": None}
    adv = average_daily_volume(df)
    if adv is None or adv <= 0:
        return False, ["Average daily volume unavailable"], {"adv": None}
    participation = quantity / adv if adv else 1.0
    order_value = float(D(quantity) * D(entry_price))
    avg_value = adv * float(df.iloc[-1]["close"])
    metrics = {
        "adv_shares": round(adv, 0),
        "participation_pct": round(participation * 100, 3),
        "order_value": round(order_value, 2),
        "avg_traded_value_est": round(avg_value, 2),
    }
    if Decimal(str(participation)) > max_adv_participation_pct:
        return False, [f"Order size {participation:.2%} of ADV exceeds limit {max_adv_participation_pct:.2%}"], metrics
    if participation > float(max_adv_participation_pct) * 0.8:
        warnings.append("Participation near ADV limit")
    return True, warnings, metrics