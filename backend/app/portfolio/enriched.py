"""Holdings enriched with execution overlay (ownership, sell limits)."""

from __future__ import annotations

from app.execution import store
from app.execution.reconcile import sync_overlay_from_book
from app.portfolio import store as portfolio_store
from app.portfolio.money import D, money


def enriched_holdings(*, sync: bool = False) -> list[dict]:
    state = portfolio_store.load_book()
    prices = portfolio_store.mark_prices()
    rows: list[dict] = []
    for h in state.all_holdings():
        if sync:
            sync_overlay_from_book(h.symbol, h.sleeve)
        ov = store.get_holding(h.symbol, h.sleeve)
        px = prices.get(h.symbol.upper(), h.average_entry)
        row = {
            **h.model_dump(mode="json"),
            "last_price": str(px),
            "market_value": str(money(D(h.quantity) * D(px))),
            "ownership_state": ov.ownership_state.value if ov else None,
            "sellable_quantity": ov.sellable_quantity if ov else h.quantity,
            "authorized_sell_qty": ov.authorized_sell_qty if ov else 0,
            "reserved_for_sell": ov.reserved_for_sell if ov else 0,
            "quantity_source": "research_book",
        }
        rows.append(row)
    return rows