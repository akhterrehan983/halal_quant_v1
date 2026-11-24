"""Map canonical research book to legacy portfolio snapshot shape (read-only compat)."""

from __future__ import annotations

from app.portfolio import manager


def legacy_portfolio_snapshot() -> dict:
    snap = manager.summary()
    prices = {}
    holdings = []
    from app.portfolio import store

    state = store.load_book()
    px = store.mark_prices()
    for h in state.all_holdings():
        last = float(px.get(h.symbol, h.average_entry))
        qty = h.quantity
        avg = float(h.average_entry)
        value = qty * last
        holdings.append(
            {
                "symbol": h.symbol,
                "quantity": qty,
                "average_price": round(avg, 2),
                "last_price": round(last, 2),
                "market_value": round(value, 2),
                "unrealized_pnl": round((last - avg) * qty, 2),
            }
        )
    return {
        "starting_cash": float(snap.total_capital),
        "cash": float(snap.available_cash),
        "market_value": float(snap.market_value),
        "equity": float(snap.portfolio_value),
        "pnl": float(snap.realized_pnl + snap.unrealized_pnl),
        "positions": holdings,
        "trades": [],
        "scope": "research_book",
        "notice": "Legacy snapshot from research book. Trades use /api/v1/execution/orders only.",
    }