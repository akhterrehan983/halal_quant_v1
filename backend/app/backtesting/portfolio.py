from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from app.portfolio.money import D, money


@dataclass
class SimPosition:
    symbol: str
    quantity: int
    entry_price: Decimal
    entry_date: date
    stop: Decimal
    strategy: str
    sell_authorized_date: date | None = None


@dataclass
class SimBook:
    cash: Decimal
    positions: dict[str, SimPosition] = field(default_factory=dict)
    realized_pnl: Decimal = field(default_factory=lambda: D(0))
    costs_paid: Decimal = field(default_factory=lambda: D(0))

    def equity(self, marks: dict[str, Decimal]) -> Decimal:
        mv = sum(D(p.quantity) * marks.get(p.symbol, p.entry_price) for p in self.positions.values())
        return money(self.cash + mv)

    def open_count(self) -> int:
        return len(self.positions)