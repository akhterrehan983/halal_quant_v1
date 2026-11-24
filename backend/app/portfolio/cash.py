from __future__ import annotations

from decimal import Decimal

from app.portfolio.money import D, money
from app.portfolio.schemas import CashLedgerEntry, LedgerReason, SleeveName


def apply_ledger_delta(
    balances: dict[str, Decimal],
    sleeve: str,
    amount: Decimal,
    reason: LedgerReason,
    note: str,
    ledger: list[CashLedgerEntry],
    entry_id: int,
) -> CashLedgerEntry:
    if sleeve not in balances:
        raise ValueError(f"Unknown sleeve {sleeve}")
    balances[sleeve] = money(balances[sleeve] + D(amount))
    if balances[sleeve] < D(0):
        raise ValueError("Cash balance cannot go negative")
    entry = CashLedgerEntry(
        id=entry_id,
        sleeve=sleeve,
        reason=reason,
        amount=money(amount),
        balance_after=balances[sleeve],
        note=note,
    )
    ledger.append(entry)
    return entry


def init_sleeve_balances(total: Decimal, swing_pct: Decimal, pos_pct: Decimal, reserve_pct: Decimal) -> dict[str, Decimal]:
    return {
        SleeveName.SWING.value: money(total * swing_pct),
        SleeveName.POSITIONAL.value: money(total * pos_pct),
        SleeveName.RESERVE.value: money(total * reserve_pct),
    }