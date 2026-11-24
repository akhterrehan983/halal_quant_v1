from __future__ import annotations

from decimal import ROUND_DOWN, Decimal

from app.portfolio.money import D


class PositionSizingResult:
    def __init__(
        self,
        quantity: int,
        *,
        risk_amount: Decimal,
        notional: Decimal,
        rejections: list[str],
        diagnostics: dict,
    ):
        self.quantity = quantity
        self.risk_amount = risk_amount
        self.notional = notional
        self.rejections = rejections
        self.diagnostics = diagnostics


def compute_position_quantity(
    *,
    sleeve_equity: Decimal,
    risk_per_trade_pct: Decimal,
    entry_price: Decimal,
    stop_price: Decimal,
    available_cash: Decimal,
    max_position_value: Decimal | None = None,
    max_shares_by_stock: int | None = None,
    max_shares_by_sector: int | None = None,
) -> PositionSizingResult:
    rejections: list[str] = []
    entry_price = D(entry_price)
    stop_price = D(stop_price)
    if entry_price <= 0:
        rejections.append("Entry price must be positive")
        return PositionSizingResult(0, risk_amount=D(0), notional=D(0), rejections=rejections, diagnostics={})
    if stop_price >= entry_price:
        rejections.append("Stop must be below entry for long-only")
        return PositionSizingResult(0, risk_amount=D(0), notional=D(0), rejections=rejections, diagnostics={})

    risk_per_share = entry_price - stop_price
    if risk_per_share <= D("0.001"):
        rejections.append("Stop too close to entry for meaningful risk sizing")
        return PositionSizingResult(0, risk_amount=D(0), notional=D(0), rejections=rejections, diagnostics={})

    risk_amount = (sleeve_equity * risk_per_trade_pct).quantize(Decimal("0.01"))
    qty_risk = int((risk_amount / risk_per_share).to_integral_value(rounding=ROUND_DOWN))
    qty_cash = int((available_cash / entry_price).to_integral_value(rounding=ROUND_DOWN))

    qty = min(qty_risk, qty_cash)
    diagnostics = {"quantity_by_risk": qty_risk, "quantity_by_cash": qty_cash, "risk_per_share": risk_per_share}

    if max_position_value is not None and entry_price > 0:
        qty_cap = int((max_position_value / entry_price).to_integral_value(rounding=ROUND_DOWN))
        diagnostics["quantity_by_max_position"] = qty_cap
        qty = min(qty, qty_cap)

    if max_shares_by_stock is not None:
        qty = min(qty, max_shares_by_stock)
    if max_shares_by_sector is not None:
        qty = min(qty, max_shares_by_sector)

    if qty <= 0:
        if qty_risk <= 0:
            rejections.append("Risk budget yields zero shares")
        elif qty_cash <= 0:
            rejections.append("Insufficient sleeve cash for one share")
        else:
            rejections.append("Exposure caps yield zero shares")

    notional = (D(qty) * entry_price).quantize(Decimal("0.01"))
    actual_risk = (D(qty) * risk_per_share).quantize(Decimal("0.01"))
    return PositionSizingResult(qty, risk_amount=actual_risk, notional=notional, rejections=rejections, diagnostics=diagnostics)