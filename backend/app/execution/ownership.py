from __future__ import annotations

from app.execution import store
from app.execution.schemas import ExecutionHolding
from app.shariah.ownership import can_transition, transition
from app.shariah.schemas import OwnershipPossessionState


def mark_order_pending(symbol: str, sleeve: str) -> ExecutionHolding:
    h = store.get_holding(symbol, sleeve) or ExecutionHolding(
        symbol=symbol.upper(),
        sleeve=sleeve,
        quantity=0,
        sellable_quantity=0,
        avg_price=0,
        ownership_state=OwnershipPossessionState.NOT_OWNED,
    )
    h.ownership_state = OwnershipPossessionState.ORDER_PENDING
    store.upsert_holding(h)
    current = h.ownership_state if h.quantity >= 0 else OwnershipPossessionState.NOT_OWNED
    store.append_ownership_event(
        transition(
            symbol,
            current,
            OwnershipPossessionState.ORDER_PENDING,
            evidence="order_approved",
            reason="BUY order approved",
        )
    )
    return h


def ownership_transition_after_buy_fill(symbol: str, sleeve: str) -> ExecutionHolding | None:
    """FSM only — quantity comes from book via reconcile.sync_overlay_from_book."""
    from app.execution.reconcile import sync_overlay_from_book

    h = sync_overlay_from_book(symbol, sleeve)
    if not h:
        return None
    current = h.ownership_state
    if current == OwnershipPossessionState.EXECUTED_UNSETTLED:
        return h
    if not can_transition(current, OwnershipPossessionState.EXECUTED_UNSETTLED):
        current = OwnershipPossessionState.ORDER_PENDING
    h.ownership_state = OwnershipPossessionState.EXECUTED_UNSETTLED
    store.upsert_holding(h)
    store.append_ownership_event(
        transition(symbol, current, OwnershipPossessionState.EXECUTED_UNSETTLED, evidence="fill", reason="trade executed")
    )
    return h


def advance_after_fill(symbol: str, sleeve: str, quantity: int, avg_price) -> ExecutionHolding:
    """Backward-compatible alias — ignores quantity; book is authoritative."""
    return ownership_transition_after_buy_fill(symbol, sleeve) or store.get_holding(symbol, sleeve)


def settle_holding(symbol: str, sleeve: str) -> ExecutionHolding:
    h = store.get_holding(symbol, sleeve)
    if not h:
        raise ValueError("No holding")
    current = h.ownership_state
    if not can_transition(current, OwnershipPossessionState.SETTLED_PENDING_VERIFICATION):
        raise ValueError(f"Cannot settle from {current}")
    h.ownership_state = OwnershipPossessionState.SETTLED_PENDING_VERIFICATION
    store.upsert_holding(h)
    store.append_ownership_event(
        transition(
            symbol,
            current,
            OwnershipPossessionState.SETTLED_PENDING_VERIFICATION,
            evidence="settlement",
            reason="T+1 settlement complete",
        )
    )
    return h


def verify_ownership(record_id: int, *, to_state: OwnershipPossessionState, evidence: str, verifier: str = "manual") -> dict:
    rec = store.get_ownership_record(record_id)
    if not rec:
        raise ValueError("Record not found")
    symbol = rec["symbol"]
    sleeve = rec.get("sleeve", "swing")
    h = store.get_holding(symbol, sleeve)
    if not h:
        raise ValueError("No holding")
    current = h.ownership_state
    if not can_transition(current, to_state):
        raise ValueError(f"Invalid verify {current} -> {to_state}")
    ev = transition(symbol, current, to_state, evidence=evidence, verifier=verifier)
    h.ownership_state = to_state
    if to_state == OwnershipPossessionState.SELL_AUTHORIZED:
        h.authorized_sell_qty = h.quantity
        h.sellable_quantity = max(0, h.quantity - h.reserved_for_sell)
    store.upsert_holding(h)
    ev_payload = ev.model_dump(mode="json")
    ev_payload["sleeve"] = sleeve
    store.append_ownership_event(ev)
    return ev_payload