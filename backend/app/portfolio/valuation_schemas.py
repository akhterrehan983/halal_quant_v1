"""Pydantic schemas for valuation snapshots (M13)."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, Field

from app.portfolio.money import D


class SnapshotTrigger(str, Enum):
    ON_DEMAND = "on_demand"
    DAILY = "daily"
    AFTER_PERSIST = "after_persist"


class ValuationSnapshotRecord(BaseModel):
    snapshot_id: int
    book_name: str
    portfolio_book_id: int | None = None
    valued_at: datetime
    valuation_date: date
    trigger: SnapshotTrigger
    portfolio_equity: Decimal
    available_cash: Decimal
    reserved_cash: Decimal
    invested_market_value: Decimal
    realized_pnl: Decimal
    unrealized_pnl: Decimal
    total_pnl: Decimal
    swing_equity: Decimal
    positional_equity: Decimal
    cash_reserve: Decimal
    equity_peak_prior: Decimal
    equity_peak_at_snapshot: Decimal
    drawdown_amount: Decimal
    drawdown_pct: Decimal
    price_quality: dict = Field(default_factory=dict)
    valuation_complete: bool = True

    @classmethod
    def from_row(cls, row) -> ValuationSnapshotRecord:
        return cls(
            snapshot_id=row.id,
            book_name=row.book_name,
            portfolio_book_id=row.portfolio_book_id,
            valued_at=row.valued_at,
            valuation_date=row.valuation_date,
            trigger=SnapshotTrigger(row.trigger),
            portfolio_equity=D(row.portfolio_equity),
            available_cash=D(row.available_cash),
            reserved_cash=D(row.reserved_cash),
            invested_market_value=D(row.invested_market_value),
            realized_pnl=D(row.realized_pnl),
            unrealized_pnl=D(row.unrealized_pnl),
            total_pnl=D(row.total_pnl),
            swing_equity=D(row.swing_equity),
            positional_equity=D(row.positional_equity),
            cash_reserve=D(row.cash_reserve),
            equity_peak_prior=D(row.equity_peak_prior),
            equity_peak_at_snapshot=D(row.equity_peak_at_snapshot),
            drawdown_amount=D(row.drawdown_amount),
            drawdown_pct=D(row.drawdown_pct),
            price_quality=row.price_quality_json or {},
            valuation_complete=bool(row.valuation_complete),
        )


class SnapshotRequest(BaseModel):
    book_name: str = "default"
    valuation_date: date | None = None
    trigger: SnapshotTrigger = SnapshotTrigger.ON_DEMAND


class PerformanceHistoryPoint(BaseModel):
    date: str
    equity: str
    drawdown_pct: str
    swing_equity: str
    positional_equity: str