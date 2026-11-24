from __future__ import annotations

from decimal import Decimal

from app.portfolio import store
from app.portfolio.cash import apply_ledger_delta
from app.portfolio.money import D, money
from app.portfolio.schemas import LedgerReason
from app.risk.manager import check_portfolio_controls


def summary():
    state = store.load_book()
    check_portfolio_controls(state)
    prices = store.mark_prices()
    return store.build_summary_from_state(state, prices)


def cash_ledger():
    state = store.load_book()
    return {"entries": [e.model_dump(mode="json") for e in state.ledger[-100:]]}


def holdings():
    state = store.load_book()
    prices = store.mark_prices()
    rows = []
    for h in state.all_holdings():
        px = prices.get(h.symbol.upper(), D(h.average_entry))
        rows.append(
            {
                **h.model_dump(mode="json"),
                "last_price": str(px),
                "market_value": str(money(D(h.quantity) * px)),
            }
        )
    return {"holdings": rows}


def add_capital(amount: Decimal, note: str = "Capital addition") -> dict:
    state = store.load_book()
    cfg = store.get_risk_config()
    state.total_capital = money(state.total_capital + D(amount))
    swing_add = money(D(amount) * cfg.swing_capital_pct)
    pos_add = money(D(amount) * cfg.positional_capital_pct)
    res_add = money(D(amount) * cfg.cash_reserve_pct)
    state.ledger_seq += 1
    apply_ledger_delta(state.balances, "swing", swing_add, LedgerReason.CAPITAL_ADDITION, note, state.ledger, state.ledger_seq)
    state.ledger_seq += 1
    apply_ledger_delta(state.balances, "positional", pos_add, LedgerReason.CAPITAL_ADDITION, note, state.ledger, state.ledger_seq)
    state.ledger_seq += 1
    apply_ledger_delta(state.balances, "reserve", res_add, LedgerReason.CAPITAL_ADDITION, note, state.ledger, state.ledger_seq)
    store.save_book(state)
    return summary().model_dump(mode="json")