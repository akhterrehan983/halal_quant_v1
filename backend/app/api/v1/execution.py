from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.execution import store
from app.execution.order_manager import approve_order, cancel_order, create_order
from app.execution.paper_broker import simulate_order
from app.execution.schemas import OrderSide, OrderType
from app.execution.sell_authorization import evaluate_sell
from app.execution.settlement import process_settlements
from app.shariah.schemas import OwnershipPossessionState
from app.execution import ownership as own

router = APIRouter(tags=["execution"])


class CreateOrderBody(BaseModel):
    symbol: str
    sleeve: str = "swing"
    side: OrderSide
    order_type: OrderType = OrderType.MARKET
    quantity: int = Field(gt=0)
    limit_price: float | None = None
    proposal_id: int | None = None


class VerifyBody(BaseModel):
    to_state: OwnershipPossessionState
    evidence: str


@router.post("/execution/orders")
def post_order(body: CreateOrderBody):
    try:
        from app.portfolio.money import D

        order = create_order(
            symbol=body.symbol,
            sleeve=body.sleeve,
            side=body.side,
            order_type=body.order_type,
            quantity=body.quantity,
            limit_price=D(body.limit_price) if body.limit_price else None,
            proposal_id=body.proposal_id,
        )
        return order.model_dump(mode="json")
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.get("/execution/orders")
def list_orders_api():
    return {"items": [o.model_dump(mode="json") for o in store.list_orders()]}


@router.get("/execution/orders/{order_id}")
def get_order_api(order_id: int):
    o = store.get_order(order_id)
    if not o:
        raise HTTPException(404, "Not found")
    return o.model_dump(mode="json")


@router.post("/execution/orders/{order_id}/approve")
def approve(order_id: int):
    try:
        return approve_order(order_id).model_dump(mode="json")
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.post("/execution/orders/{order_id}/cancel")
def cancel(order_id: int):
    try:
        return cancel_order(order_id).model_dump(mode="json")
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.post("/execution/orders/{order_id}/simulate")
def simulate(order_id: int):
    try:
        return simulate_order(order_id).model_dump(mode="json")
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.get("/execution/holdings")
def holdings():
    from app.portfolio.enriched import enriched_holdings

    return {"holdings": enriched_holdings(sync=True), "source": "research_book", "notice": "Quantities from research book; overlay fields for ownership."}


@router.get("/execution/holdings/{symbol}")
def holding_symbol(symbol: str, sleeve: str = "swing"):
    h = store.get_holding(symbol.upper(), sleeve)
    if not h:
        raise HTTPException(404, "No holding")
    return h.model_dump(mode="json")


@router.get("/execution/ownership/{symbol}")
def ownership_symbol(symbol: str):
    return {"symbol": symbol.upper(), "history": store.ownership_history(symbol.upper())}


@router.post("/execution/ownership/{record_id}/verify")
def verify_ownership(record_id: int, body: VerifyBody):
    try:
        return own.verify_ownership(record_id, to_state=body.to_state, evidence=body.evidence)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.get("/execution/ownership/{record_id}/history")
def ownership_record_history(record_id: int):
    rec = store.get_ownership_record(record_id)
    if not rec:
        raise HTTPException(404, "Not found")
    return {"record": rec, "symbol_history": store.ownership_history(rec["symbol"])}


@router.get("/execution/settlements")
def settlements():
    return {
        "pending": [s.model_dump(mode="json") for s in store.list_pending_settlements()],
    }


@router.post("/execution/settlements/process")
def settlements_process():
    done = process_settlements()
    return {"processed": [s.model_dump(mode="json") for s in done]}


@router.get("/execution/sell-authorizations")
def sell_auths(symbol: str, quantity: int, sleeve: str = "swing"):
    return evaluate_sell(symbol, quantity, sleeve).model_dump(mode="json")


@router.post("/execution/sell-authorizations/evaluate")
def sell_auth_eval(body: CreateOrderBody):
    if body.side != OrderSide.SELL:
        raise HTTPException(400, "Use SELL side")
    return evaluate_sell(body.symbol, body.quantity, body.sleeve).model_dump(mode="json")