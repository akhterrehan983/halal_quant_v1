from __future__ import annotations

from datetime import date, datetime

from app.execution import store
from app.execution.schemas import OrderSide, OrderState, OrderType, PaperOrder
from app.portfolio import store as portfolio_store
from app.portfolio.money import D
from app.risk import manager as risk_manager
from app.portfolio.schemas import AllocationProposal
from app.shariah.screening import eligibility_for_order


def _transition(order: PaperOrder, new_state: OrderState, reason: str) -> PaperOrder:
    from app.execution.schemas import ALLOWED_ORDER_TRANSITIONS

    if new_state not in ALLOWED_ORDER_TRANSITIONS.get(order.state, set()) and order.state != new_state:
        order.rejections.append(f"Invalid transition {order.state} -> {new_state}")
        order.state = OrderState.REJECTED
    else:
        order.state = new_state
    order.events.append({"state": new_state.value, "reason": reason, "at": datetime.utcnow().isoformat()})
    return store.save_order(order)


def validate_buy(order: PaperOrder, proposal: AllocationProposal | None) -> list[str]:
    errs: list[str] = []
    if order.quantity <= 0:
        errs.append("Quantity must be positive")
    ok, sh = eligibility_for_order(order.symbol)
    if not ok:
        errs.extend(sh)
    if proposal is None:
        errs.append("Allocation proposal required")
    else:
        if proposal.status.value not in ("PENDING", "APPROVED"):
            errs.append("Proposal not eligible")
        elif proposal.quantity < order.quantity:
            errs.append("Order quantity exceeds proposal")
        val = risk_manager.validate_proposal(proposal)
        if not val.approved:
            errs.extend(val.rejections)
    book = portfolio_store.load_book()
    sleeve = order.sleeve
    available = book.balances.get(sleeve, D(0)) - book.reserved.get(sleeve, D(0))
    est = D(order.quantity) * (order.limit_price or D(proposal.entry_reference if proposal else 0))
    if est > available:
        errs.append("Insufficient available cash")
    for o in store.list_orders():
        if (
            o.symbol == order.symbol
            and o.side == OrderSide.BUY
            and o.state in (OrderState.SUBMITTED, OrderState.APPROVED, OrderState.PARTIALLY_FILLED)
        ):
            errs.append("Duplicate active BUY order")
            break
    return errs


def validate_sell(order: PaperOrder) -> list[str]:
    from app.execution.sell_authorization import evaluate_sell

    auth = evaluate_sell(order.symbol, order.quantity, order.sleeve)
    return auth.reasons if not auth.granted else []


def create_order(
    *,
    symbol: str,
    sleeve: str,
    side: OrderSide,
    order_type: OrderType,
    quantity: int,
    limit_price=None,
    proposal_id: int | None = None,
    signal_date: date | None = None,
) -> PaperOrder:
    order = PaperOrder(
        order_id=store.next_order_id(),
        symbol=symbol.upper(),
        sleeve=sleeve,
        side=side,
        order_type=order_type,
        quantity=quantity,
        limit_price=limit_price,
        proposal_id=proposal_id,
        signal_date=signal_date or date.today(),
        state=OrderState.PENDING_APPROVAL,
        created_at=datetime.utcnow(),
    )
    proposal = None
    if proposal_id:
        proposal = portfolio_store.get_proposal(proposal_id)
    if side == OrderSide.BUY:
        order.rejections = validate_buy(order, proposal)
    else:
        order.rejections = validate_sell(order)
    if order.rejections:
        order.state = OrderState.REJECTED
    else:
        if side == OrderSide.BUY and proposal:
            notional = D(quantity) * D(proposal.entry_reference)
            order.reserved_cash = notional
            store.reserve_cash(sleeve, notional)
        elif side == OrderSide.SELL:
            from app.execution.reconcile import sync_overlay_from_book

            sync_overlay_from_book(symbol, sleeve)
            h = store.get_holding(symbol, sleeve)
            if h:
                h.reserved_for_sell += quantity
                h.sellable_quantity = max(0, h.quantity - h.reserved_for_sell)
                store.upsert_holding(h)
            order.reserved_quantity = quantity
    order.events.append({"state": order.state.value, "reason": "created", "at": datetime.utcnow().isoformat()})
    return store.save_order(order)


def approve_order(order_id: int) -> PaperOrder:
    from app.execution.ownership import mark_order_pending

    order = store.get_order(order_id)
    if not order:
        raise ValueError("Order not found")
    if order.rejections:
        return _transition(order, OrderState.REJECTED, "Cannot approve rejected validation")
    order = _transition(order, OrderState.APPROVED, "manual approve")
    if order.side.value == "BUY":
        mark_order_pending(order.symbol, order.sleeve)
    return order


def cancel_order(order_id: int) -> PaperOrder:
    order = store.get_order(order_id)
    if not order:
        raise ValueError("Order not found")
    if order.reserved_cash > 0:
        store.release_cash(order.sleeve, order.reserved_cash)
        order.reserved_cash = D(0)
    if order.side == OrderSide.SELL and order.reserved_quantity > 0:
        h = store.get_holding(order.symbol, order.sleeve)
        if h:
            h.reserved_for_sell = max(0, h.reserved_for_sell - order.reserved_quantity)
            h.sellable_quantity = max(0, h.quantity - h.reserved_for_sell)
            store.upsert_holding(h)
        order.reserved_quantity = 0
    return _transition(order, OrderState.CANCELLED, "cancelled")