"""Sync execution overlay from canonical research book — book owns quantity and average cost."""

from __future__ import annotations

from app.execution import store
from app.execution.schemas import ExecutionHolding
from app.portfolio import store as portfolio_store
from app.portfolio.money import D
from app.shariah.schemas import OwnershipPossessionState


def _book_holding(symbol: str, sleeve: str):
    state = portfolio_store.load_book()
    sym = symbol.upper()
    for h in state.holdings_for(sleeve):
        if h.symbol == sym:
            return h
    return None


def sync_overlay_from_book(symbol: str, sleeve: str) -> ExecutionHolding | None:
    """Align execution overlay quantity and avg price with book. Never raises authorized_sell_qty."""
    book_h = _book_holding(symbol, sleeve)
    sym = symbol.upper()
    overlay = store.get_holding(sym, sleeve)

    if not book_h or book_h.quantity <= 0:
        if overlay:
            overlay.quantity = 0
            overlay.sellable_quantity = 0
            overlay.reserved_for_sell = min(overlay.reserved_for_sell, 0)
            overlay.authorized_sell_qty = 0
            overlay.ownership_state = OwnershipPossessionState.NOT_OWNED
            store.remove_holding(sym, sleeve)
            return None
        return None

    qty = int(book_h.quantity)
    avg = D(book_h.average_entry)

    if not overlay:
        overlay = ExecutionHolding(
            symbol=sym,
            sleeve=sleeve,
            quantity=qty,
            sellable_quantity=qty,
            avg_price=avg,
            ownership_state=OwnershipPossessionState.EXECUTED_UNSETTLED if qty > 0 else OwnershipPossessionState.NOT_OWNED,
        )
        store.upsert_holding(overlay)
        return overlay

    reserved = max(0, overlay.reserved_for_sell)
    if reserved > qty:
        reserved = qty
    auth = overlay.authorized_sell_qty
    if auth > qty:
        auth = qty

    overlay.quantity = qty
    overlay.avg_price = avg
    overlay.reserved_for_sell = reserved
    overlay.authorized_sell_qty = auth
    overlay.sellable_quantity = max(0, qty - reserved)
    store.upsert_holding(overlay)
    return overlay


def reconcile_all() -> dict:
    """Full book vs execution overlay audit and repair quantity drift (not authorization upgrades)."""
    state = portfolio_store.load_book()
    mismatches: list[dict] = []
    seen: set[tuple[str, str]] = set()

    for h in state.all_holdings():
        key = (h.symbol, h.sleeve)
        seen.add(key)
        overlay = store.get_holding(h.symbol, h.sleeve)
        if not overlay or overlay.quantity != h.quantity:
            mismatches.append(
                {
                    "symbol": h.symbol,
                    "sleeve": h.sleeve,
                    "book_quantity": h.quantity,
                    "overlay_quantity": overlay.quantity if overlay else None,
                }
            )
            sync_overlay_from_book(h.symbol, h.sleeve)

    for ex in store.list_holdings():
        key = (ex.symbol, ex.sleeve)
        if key not in seen and ex.quantity > 0:
            mismatches.append(
                {
                    "symbol": ex.symbol,
                    "sleeve": ex.sleeve,
                    "book_quantity": 0,
                    "overlay_quantity": ex.quantity,
                    "orphan_overlay": True,
                }
            )
            store.remove_holding(ex.symbol, ex.sleeve)

    post = reconcile_report()
    return {
        "repaired": len(mismatches),
        "mismatches_before": mismatches,
        "ok": post["ok"],
        "details": post,
    }


def reconcile_report() -> dict:
    """Read-only consistency check after repair."""
    state = portfolio_store.load_book()
    issues: list[dict] = []
    for h in state.all_holdings():
        ov = store.get_holding(h.symbol, h.sleeve)
        if not ov or ov.quantity != h.quantity:
            issues.append(
                {
                    "type": "quantity_mismatch",
                    "symbol": h.symbol,
                    "sleeve": h.sleeve,
                    "book": h.quantity,
                    "overlay": ov.quantity if ov else None,
                }
            )
    for ex in store.list_holdings():
        bh = _book_holding(ex.symbol, ex.sleeve)
        if not bh or bh.quantity <= 0:
            issues.append({"type": "orphan_overlay", "symbol": ex.symbol, "sleeve": ex.sleeve, "overlay_qty": ex.quantity})
    return {"ok": len(issues) == 0, "issues": issues}