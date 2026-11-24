"""Idempotent simulated fill pipeline.

Consistency model: portfolio book (PostgreSQL or memory) and execution_state JSON are persisted
separately. Steps are idempotent via order event markers; reconcile_all() repairs overlay drift.
This is not a single database transaction across both stores.
"""

from __future__ import annotations

from datetime import datetime

from app.execution import store
from app.execution.costs import transaction_costs
from app.execution.matching import simulate_limit_fill, simulate_market_fill
from app.execution.ownership import ownership_transition_after_buy_fill
from app.execution.reconcile import sync_overlay_from_book
from app.execution.schemas import FillRecord, OrderSide, OrderState, OrderType, PaperOrder, SettlementRecord
from app.execution.settlement import settlement_date
from app.portfolio.money import D


def _event_applied(order: PaperOrder, reason: str) -> bool:
    return any(e.get("reason") == reason for e in order.events)


def _mark_event(order: PaperOrder, reason: str) -> None:
    order.events.append({"state": order.state.value, "reason": reason, "at": datetime.utcnow().isoformat()})


def apply_fill_to_book(order: PaperOrder, fill: FillRecord) -> None:
    if _event_applied(order, "book_fill_applied"):
        return
    if order.side == OrderSide.BUY:
        store.apply_buy_fill(order, fill, fill.fees)
    else:
        store.apply_sell_fill(order, fill, fill.fees)
    _mark_event(order, "book_fill_applied")


def apply_overlay_sync(order: PaperOrder) -> None:
    if _event_applied(order, "overlay_synced"):
        return
    sync_overlay_from_book(order.symbol, order.sleeve)
    if order.side == OrderSide.BUY:
        ownership_transition_after_buy_fill(order.symbol, order.sleeve)
        sync_overlay_from_book(order.symbol, order.sleeve)
    else:
        overlay = store.get_holding(order.symbol, order.sleeve)
        if overlay:
            overlay.reserved_for_sell = max(0, overlay.reserved_for_sell - order.filled_quantity)
            if overlay.authorized_sell_qty:
                overlay.authorized_sell_qty = max(0, overlay.authorized_sell_qty - order.filled_quantity)
            store.upsert_holding(overlay)
        sync_overlay_from_book(order.symbol, order.sleeve)
    _mark_event(order, "overlay_synced")


def process_simulated_fill(
    order: PaperOrder,
    *,
    skip_book: bool = False,
    skip_overlay: bool = False,
    raise_before_persist: bool = False,
) -> PaperOrder:
    if order.state == OrderState.FILLED and _event_applied(order, "fill_persisted"):
        return order

    if order.order_type == OrderType.MARKET:
        result = simulate_market_fill(order)
    else:
        result = simulate_limit_fill(order)
    if not result:
        order.state = OrderState.SUBMITTED
        _mark_event(order, "no_fill_on_session")
        return store.save_order(order)

    qty, price, trade_date = result
    fill = FillRecord(
        order_id=order.order_id or 0,
        quantity=qty,
        price=price,
        slippage=D(0),
        fees=D(0),
        trade_date=trade_date,
    )
    costs = transaction_costs(D(qty) * D(price), order.side.value)
    fill.fees = D(costs["total"])

    if not _event_applied(order, "fill_recorded"):
        store.add_fill(fill)
        order.filled_quantity = qty
        order.avg_fill_price = price
        _mark_event(order, "fill_recorded")

    if not skip_book:
        apply_fill_to_book(order, fill)

    if not skip_overlay:
        apply_overlay_sync(order)

    if order.side == OrderSide.BUY and not _event_applied(order, "settlement_created"):
        store.add_settlement(
            SettlementRecord(
                fill_id=fill.fill_id or 0,
                order_id=order.order_id or 0,
                symbol=order.symbol,
                trade_date=trade_date,
                settlement_date=settlement_date(trade_date),
            )
        )
        _mark_event(order, "settlement_created")

    order.state = OrderState.FILLED
    _mark_event(order, "simulated")

    if raise_before_persist:
        raise RuntimeError("raise_before_persist")

    _mark_event(order, "fill_persisted")
    return store.save_order(order)