from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.portfolio.money import D


@dataclass(frozen=True)
class CostConfig:
    zero_cost_demo: bool = True
    brokerage_pct: Decimal = D("0")
    stt_sell_pct: Decimal = D("0.001")
    exchange_pct: Decimal = D("0.0000325")
    sebi_per_crore: Decimal = D("10")
    gst_pct: Decimal = D("0.18")
    stamp_duty_buy_pct: Decimal = D("0.00015")


DEFAULT_COSTS = CostConfig()


def transaction_costs(notional: Decimal, side: str, cfg: CostConfig = DEFAULT_COSTS) -> dict:
    n = D(notional)
    if cfg.zero_cost_demo:
        return {"total": D("0"), "components": {"mode": "zero_cost_demo"}, "notice": "Demo zero-cost config"}
    brokerage = (n * cfg.brokerage_pct).quantize(Decimal("0.01"))
    exchange = (n * cfg.exchange_pct).quantize(Decimal("0.01"))
    stt = (n * cfg.stt_sell_pct).quantize(Decimal("0.01")) if side == "SELL" else D("0")
    stamp = (n * cfg.stamp_duty_buy_pct).quantize(Decimal("0.01")) if side == "BUY" else D("0")
    gst = ((brokerage + exchange) * cfg.gst_pct).quantize(Decimal("0.01"))
    total = brokerage + exchange + stt + stamp + gst
    return {
        "total": total,
        "components": {
            "brokerage": brokerage,
            "exchange": exchange,
            "stt": stt,
            "stamp_duty": stamp,
            "gst": gst,
        },
    }