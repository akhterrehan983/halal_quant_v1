from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, Field

from app.portfolio.money import D


class SleeveName(str, Enum):
    SWING = "swing"
    POSITIONAL = "positional"
    RESERVE = "reserve"


class LedgerReason(str, Enum):
    INITIAL_FUNDING = "INITIAL_FUNDING"
    CAPITAL_ADDITION = "CAPITAL_ADDITION"
    WITHDRAWAL = "WITHDRAWAL"
    ALLOCATION_RESERVE = "ALLOCATION_RESERVE"
    RESERVE_RELEASE = "RESERVE_RELEASE"
    REALIZED_PNL = "REALIZED_PNL"
    ADJUSTMENT = "ADJUSTMENT"


class ProposalStatus(str, Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    SUPERSEDED = "SUPERSEDED"


class CashLedgerEntry(BaseModel):
    id: int | None = None
    sleeve: str
    reason: LedgerReason
    amount: Decimal
    balance_after: Decimal
    note: str = ""
    created_at: datetime | None = None


class SleeveHolding(BaseModel):
    symbol: str
    sleeve: str
    quantity: int
    average_entry: Decimal
    stop_reference: Decimal | None = None
    risk_per_share: Decimal | None = None
    signal_id: int | None = None
    opened_at: date | None = None


class SleeveSnapshot(BaseModel):
    name: str
    allocated_capital: Decimal
    available_cash: Decimal
    reserved_cash: Decimal
    invested_value: Decimal
    market_value: Decimal
    unrealized_pnl: Decimal
    position_count: int
    open_risk: Decimal


class PortfolioSummary(BaseModel):
    total_capital: Decimal
    cash_reserve: Decimal
    available_cash: Decimal
    invested_capital: Decimal
    market_value: Decimal
    portfolio_value: Decimal
    realized_pnl: Decimal
    unrealized_pnl: Decimal
    open_risk: Decimal
    current_drawdown_pct: Decimal
    peak_value: Decimal
    drawdown_locked: bool
    swing: SleeveSnapshot
    positional: SleeveSnapshot
    sleeves_valid: bool
    notice: str = "Research allocation book — proposals are not executed orders."


class AllocationProposal(BaseModel):
    proposal_id: int | None = None
    signal_id: int | None = None
    symbol: str
    sleeve: str
    status: ProposalStatus = ProposalStatus.PENDING
    quantity: int = 0
    entry_reference: Decimal
    stop_reference: Decimal
    target_reference: Decimal | None = None
    notional: Decimal = Field(default_factory=lambda: D(0))
    risk_amount: Decimal = Field(default_factory=lambda: D(0))
    risk_per_trade_pct: Decimal = Field(default_factory=lambda: D(0))
    validations: list[str] = Field(default_factory=list)
    rejections: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    exposure_checks: dict = Field(default_factory=dict)
    created_at: datetime | None = None


class RebalanceProposal(BaseModel):
    proposal_id: int | None = None
    status: ProposalStatus = ProposalStatus.PENDING
    actions: list[dict] = Field(default_factory=list)
    reason: str = ""
    created_at: datetime | None = None