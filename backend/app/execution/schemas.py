from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, Field

from app.shariah.schemas import OwnershipPossessionState


class OrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(str, Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"


class OrderState(str, Enum):
    DRAFT = "DRAFT"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    APPROVED = "APPROVED"
    SUBMITTED = "SUBMITTED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"


ALLOWED_ORDER_TRANSITIONS: dict[OrderState, set[OrderState]] = {
    OrderState.DRAFT: {OrderState.PENDING_APPROVAL, OrderState.REJECTED, OrderState.CANCELLED},
    OrderState.PENDING_APPROVAL: {OrderState.APPROVED, OrderState.REJECTED, OrderState.CANCELLED},
    OrderState.APPROVED: {OrderState.SUBMITTED, OrderState.CANCELLED},
    OrderState.SUBMITTED: {OrderState.PARTIALLY_FILLED, OrderState.FILLED, OrderState.REJECTED, OrderState.CANCELLED, OrderState.EXPIRED},
    OrderState.PARTIALLY_FILLED: {OrderState.FILLED, OrderState.CANCELLED},
}


class PaperOrder(BaseModel):
    order_id: int | None = None
    symbol: str
    sleeve: str = "swing"
    side: OrderSide
    order_type: OrderType
    quantity: int
    limit_price: Decimal | None = None
    state: OrderState = OrderState.DRAFT
    proposal_id: int | None = None
    signal_date: date | None = None
    reserved_cash: Decimal = Field(default_factory=lambda: Decimal("0"))
    reserved_quantity: int = 0
    filled_quantity: int = 0
    avg_fill_price: Decimal | None = None
    rejections: list[str] = Field(default_factory=list)
    events: list[dict] = Field(default_factory=list)
    created_at: datetime | None = None


class FillRecord(BaseModel):
    fill_id: int | None = None
    order_id: int
    quantity: int
    price: Decimal
    slippage: Decimal
    fees: Decimal
    trade_date: date
    created_at: datetime | None = None


class SettlementRecord(BaseModel):
    settlement_id: int | None = None
    fill_id: int
    order_id: int
    symbol: str
    trade_date: date
    settlement_date: date
    status: str = "PENDING"
    cash_settled: bool = False
    securities_settled: bool = False


class ExecutionHolding(BaseModel):
    symbol: str
    sleeve: str
    quantity: int
    sellable_quantity: int
    avg_price: Decimal
    ownership_state: OwnershipPossessionState = OwnershipPossessionState.NOT_OWNED
    reserved_for_sell: int = 0
    authorized_sell_qty: int = 0


class SellAuthorization(BaseModel):
    auth_id: int | None = None
    symbol: str
    quantity: int
    granted: bool
    reasons: list[str] = Field(default_factory=list)
    ownership_state: OwnershipPossessionState | None = None