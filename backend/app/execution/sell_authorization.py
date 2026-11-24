from __future__ import annotations

from app.execution import store
from app.execution.schemas import SellAuthorization
from app.shariah.schemas import OwnershipPossessionState


def evaluate_sell(symbol: str, quantity: int, sleeve: str = "swing") -> SellAuthorization:
    from app.execution.reconcile import sync_overlay_from_book

    sync_overlay_from_book(symbol, sleeve)
    h = store.get_holding(symbol, sleeve)
    reasons: list[str] = []
    if not h or h.quantity < quantity:
        reasons.append("Insufficient holding quantity")
    if not h:
        return SellAuthorization(symbol=symbol.upper(), quantity=quantity, granted=False, reasons=reasons)
    state = h.ownership_state
    if state not in (OwnershipPossessionState.SELL_AUTHORIZED,):
        reasons.append(f"Ownership state {state} does not permit sell (need SELL_AUTHORIZED)")
    available = h.sellable_quantity - h.reserved_for_sell
    if quantity > available:
        reasons.append(f"Sellable quantity {available} less than requested {quantity}")
    if h.authorized_sell_qty and quantity > h.authorized_sell_qty:
        reasons.append(f"Sell authorization caps quantity at {h.authorized_sell_qty}")
    granted = len(reasons) == 0
    return SellAuthorization(
        auth_id=None,
        symbol=symbol.upper(),
        quantity=quantity,
        granted=granted,
        reasons=reasons,
        ownership_state=state,
    )