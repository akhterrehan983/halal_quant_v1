from __future__ import annotations

import logging
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import select

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.shariah_execution import ExecutionStateRow
from app.execution.schemas import (
    ExecutionHolding,
    FillRecord,
    OrderState,
    PaperOrder,
    SettlementRecord,
)
from app.portfolio import store as portfolio_store
from app.portfolio.cash import apply_ledger_delta
from app.portfolio.money import D, money
from app.portfolio.schemas import LedgerReason, SleeveHolding

logger = logging.getLogger(__name__)

_STATE: dict | None = None
_ORDER_SEQ = 0
_FILL_SEQ = 0
_SETT_SEQ = 0
_OWN_SEQ = 0


def _empty() -> dict:
    return {
        "orders": [],
        "fills": [],
        "settlements": [],
        "holdings": [],
        "ownership_events": [],
        "processed_settlements": [],
    }


def _normalize_state(st: dict) -> dict:
    """Ensure all expected keys exist (legacy or partial JSON payloads)."""
    base = _empty()
    out = {**base, **st}
    proc = out.get("processed_settlements", [])
    if isinstance(proc, list):
        out["processed_settlements"] = set(proc)
    elif not isinstance(proc, set):
        out["processed_settlements"] = set()
    return out


def _load() -> dict:
    global _STATE
    if settings.database_enabled and SessionLocal:
        with SessionLocal() as session:
            row = session.execute(select(ExecutionStateRow).where(ExecutionStateRow.name == "default")).scalar_one_or_none()
            if not row:
                st = _empty()
                session.add(ExecutionStateRow(name="default", state_json=st))
                session.commit()
                return st
            return _normalize_state(dict(row.state_json))
    if _STATE is None:
        _STATE = _empty()
    return _normalize_state(_STATE)


def _save(state: dict) -> None:
    global _STATE
    payload = {**state, "processed_settlements": list(state.get("processed_settlements", []))}
    if settings.database_enabled and SessionLocal:
        with SessionLocal() as session:
            row = session.execute(select(ExecutionStateRow).where(ExecutionStateRow.name == "default")).scalar_one_or_none()
            if not row:
                row = ExecutionStateRow(name="default", state_json=payload)
                session.add(row)
            else:
                row.state_json = payload
                row.updated_at = datetime.utcnow()
            session.commit()
            return
    _STATE = state


def next_order_id() -> int:
    global _ORDER_SEQ
    _ORDER_SEQ += 1
    return _ORDER_SEQ


def list_orders() -> list[PaperOrder]:
    return [PaperOrder.model_validate(o) for o in _load()["orders"]]


def get_order(order_id: int) -> PaperOrder | None:
    for o in _load()["orders"]:
        if o.get("order_id") == order_id:
            return PaperOrder.model_validate(o)
    return None


def save_order(order: PaperOrder) -> PaperOrder:
    st = _load()
    replaced = False
    for i, o in enumerate(st["orders"]):
        if o.get("order_id") == order.order_id:
            st["orders"][i] = order.model_dump(mode="json")
            replaced = True
            break
    if not replaced:
        st["orders"].insert(0, order.model_dump(mode="json"))
    _save(st)
    return order


def order_sleeve(order_id: int) -> str:
    o = get_order(order_id)
    return o.sleeve if o else "swing"


def reserve_cash(sleeve: str, amount: Decimal) -> None:
    from app.portfolio.schemas import CashLedgerEntry, LedgerReason

    amt = D(amount)

    def mutate(book):
        available = book.balances.get(sleeve, D(0)) - book.reserved.get(sleeve, D(0))
        if amt > available:
            raise ValueError("Insufficient available cash to reserve")
        book.reserved[sleeve] = money(book.reserved.get(sleeve, D(0)) + amt)
        book.ledger_seq += 1
        book.ledger.append(
            CashLedgerEntry(
                id=book.ledger_seq,
                sleeve=sleeve,
                reason=LedgerReason.ALLOCATION_RESERVE,
                amount=amt,
                balance_after=book.balances[sleeve],
                note=f"Reserved {amount} for order",
            )
        )

    portfolio_store.update_book(mutate)


def release_cash(sleeve: str, amount: Decimal) -> None:
    from app.portfolio.schemas import CashLedgerEntry, LedgerReason

    amt = D(amount)

    def mutate(book):
        book.reserved[sleeve] = money(max(D(0), book.reserved.get(sleeve, D(0)) - amt))
        book.ledger_seq += 1
        book.ledger.append(
            CashLedgerEntry(
                id=book.ledger_seq,
                sleeve=sleeve,
                reason=LedgerReason.RESERVE_RELEASE,
                amount=-amt,
                balance_after=book.balances[sleeve],
                note=f"Released {amount}",
            )
        )

    portfolio_store.update_book(mutate)


def apply_buy_fill(order: PaperOrder, fill: FillRecord, fees: Decimal) -> None:
    sleeve = order.sleeve
    notional = money(D(fill.quantity) * D(fill.price) + D(fees))
    release_amt = min(D(order.reserved_cash), notional)

    def mutate(book):
        book.reserved[sleeve] = money(max(D(0), book.reserved.get(sleeve, D(0)) - release_amt))
        if notional > book.balances.get(sleeve, D(0)):
            raise ValueError("Insufficient sleeve cash for BUY fill")
        book.balances[sleeve] = money(book.balances[sleeve] - notional)
        book.ledger_seq += 1
        apply_ledger_delta(
            book.balances,
            sleeve,
            -notional,
            LedgerReason.ADJUSTMENT,
            "BUY fill",
            book.ledger,
            book.ledger_seq,
        )
        portfolio_store._merge_holding(book, sleeve, order.symbol, fill.quantity, fill.price)

    portfolio_store.update_book(mutate)


def apply_sell_fill(order: PaperOrder, fill: FillRecord, fees: Decimal) -> None:
    sleeve = order.sleeve
    sym = order.symbol.upper()
    proceeds = money(D(fill.quantity) * D(fill.price) - D(fees))

    def mutate(book):
        cost_basis = D(0)
        holdings = list(book.holdings_for(sleeve))
        for h in holdings:
            if h.symbol == sym:
                cost_basis = D(fill.quantity) * D(h.average_entry)
                h.quantity -= fill.quantity
                if h.quantity <= 0:
                    holdings = [x for x in holdings if x.symbol != sym]
                break
        if sleeve == "swing":
            book.holdings_swing = holdings
        else:
            book.holdings_positional = holdings
        book.balances[sleeve] = money(book.balances.get(sleeve, D(0)) + proceeds)
        book.realized_pnl = money(book.realized_pnl + proceeds - cost_basis)
        book.ledger_seq += 1
        apply_ledger_delta(
            book.balances,
            sleeve,
            proceeds,
            LedgerReason.ADJUSTMENT,
            "SELL fill",
            book.ledger,
            book.ledger_seq,
        )

    portfolio_store.update_book(mutate)


def get_holding(symbol: str, sleeve: str) -> ExecutionHolding | None:
    for h in _load()["holdings"]:
        if h["symbol"] == symbol.upper() and h["sleeve"] == sleeve:
            return ExecutionHolding.model_validate(h)
    return None


def upsert_holding(h: ExecutionHolding) -> None:
    st = _load()
    st["holdings"] = [x for x in st["holdings"] if not (x["symbol"] == h.symbol and x["sleeve"] == h.sleeve)]
    st["holdings"].append(h.model_dump(mode="json"))
    _save(st)


def remove_holding(symbol: str, sleeve: str) -> None:
    st = _load()
    sym = symbol.upper()
    st["holdings"] = [x for x in st["holdings"] if not (x["symbol"] == sym and x["sleeve"] == sleeve)]
    _save(st)


def append_ownership_event(ev) -> int:
    global _OWN_SEQ
    _OWN_SEQ += 1
    st = _load()
    payload = ev.model_dump(mode="json") if hasattr(ev, "model_dump") else ev
    payload["event_id"] = _OWN_SEQ
    st["ownership_events"].append(payload)
    _save(st)
    return _OWN_SEQ


def get_ownership_record(event_id: int) -> dict | None:
    for e in _load()["ownership_events"]:
        if e.get("event_id") == event_id:
            return e
    return None


def ownership_history(symbol: str) -> list[dict]:
    return [e for e in _load()["ownership_events"] if e.get("symbol") == symbol.upper()]


def add_fill(fill: FillRecord) -> FillRecord:
    global _FILL_SEQ
    _FILL_SEQ += 1
    fill.fill_id = _FILL_SEQ
    st = _load()
    st["fills"].insert(0, fill.model_dump(mode="json"))
    _save(st)
    return fill


def add_settlement(rec: SettlementRecord) -> SettlementRecord:
    global _SETT_SEQ
    _SETT_SEQ += 1
    rec.settlement_id = _SETT_SEQ
    st = _load()
    st["settlements"].append(rec.model_dump(mode="json"))
    _save(st)
    return rec


def list_pending_settlements() -> list[SettlementRecord]:
    return [SettlementRecord.model_validate(s) for s in _load()["settlements"] if s.get("status") == "PENDING"]


def update_settlement(rec: SettlementRecord) -> None:
    st = _load()
    for i, s in enumerate(st["settlements"]):
        if s.get("settlement_id") == rec.settlement_id:
            st["settlements"][i] = rec.model_dump(mode="json")
            break
    _save(st)


def idempotent_settlement(settlement_id: int) -> bool:
    st = _load()
    proc = st.setdefault("processed_settlements", set())
    if isinstance(proc, list):
        proc = set(proc)
        st["processed_settlements"] = proc
    if settlement_id in proc:
        return False
    proc.add(settlement_id)
    _save(st)
    return True


def list_holdings() -> list[ExecutionHolding]:
    return [ExecutionHolding.model_validate(h) for h in _load()["holdings"]]