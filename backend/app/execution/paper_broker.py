from __future__ import annotations

from datetime import datetime

from app.execution import store
from app.execution.fill_processor import process_simulated_fill
from app.execution.schemas import OrderState, PaperOrder
from app.execution.sell_authorization import evaluate_sell


def simulate_order(order_id: int) -> PaperOrder:
    order = store.get_order(order_id)
    if not order or order.state not in (OrderState.APPROVED, OrderState.SUBMITTED):
        raise ValueError("Order not ready for simulation")
    if order.side.value == "SELL":
        auth = evaluate_sell(order.symbol, order.quantity, order.sleeve)
        if not auth.granted:
            order.rejections = auth.reasons
            order.state = OrderState.REJECTED
            return store.save_order(order)

    order.state = OrderState.SUBMITTED
    store.save_order(order)
    return process_simulated_fill(order)