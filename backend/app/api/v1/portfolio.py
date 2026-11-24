from datetime import date

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.core.config import settings
from app.execution.reconcile import reconcile_all, reconcile_report
from app.portfolio import allocator, manager, rebalancing
from app.portfolio import store
from app.portfolio.compat import legacy_portfolio_snapshot
from app.portfolio.enriched import enriched_holdings
from app.portfolio.money import D
from app.portfolio import snapshots as valuation_snapshots
from app.portfolio.drawdown_audit import (
    current_drawdown_from_latest,
    episodes_from_snapshots,
    max_drawdown_over_period,
)
from app.portfolio.schemas import AllocationProposal
from app.portfolio.valuation_schemas import PerformanceHistoryPoint, SnapshotRequest, SnapshotTrigger

LEGACY_TRADE_BLOCKED = (
    "Direct trades/buy-sell endpoints are disabled. Use POST /api/v1/execution/orders."
)

router = APIRouter(tags=["portfolio"])


class TradeRequest(BaseModel):
    symbol: str
    quantity: int = Field(gt=0)
    price: float = Field(gt=0)


class AllocateRequest(BaseModel):
    horizon: str | None = None
    limit: int = 20


class CapitalRequest(BaseModel):
    amount: float = Field(gt=0)
    note: str = ""


@router.get("/portfolio")
def portfolio_root():
    snap = manager.summary()
    return {**snap.model_dump(mode="json"), "mode": "research_book", "persisted": settings.database_enabled}


@router.get("/portfolio/summary")
def portfolio_summary():
    return portfolio_root()


@router.get("/portfolio/sleeves")
def portfolio_sleeves():
    s = manager.summary()
    return {"swing": s.swing.model_dump(mode="json"), "positional": s.positional.model_dump(mode="json")}


@router.get("/portfolio/holdings")
def portfolio_holdings_v1(enriched: bool = True):
    if enriched:
        return {"holdings": enriched_holdings(sync=True), "source": "research_book"}
    return manager.holdings()


@router.get("/portfolio/holdings/enriched")
def portfolio_holdings_enriched():
    return {"holdings": enriched_holdings(sync=True), "source": "research_book"}


@router.get("/portfolio/reconciliation")
def portfolio_reconciliation(repair: bool = False):
    if repair:
        return reconcile_all()
    return reconcile_report()


@router.get("/portfolio/valuations")
def list_valuations(
    book_name: str = "default",
    start: date | None = None,
    end: date | None = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    items, total = valuation_snapshots.list_snapshots(
        book_name=book_name, start=start, end=end, limit=limit, offset=offset
    )
    return {
        "book_name": book_name,
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": [i.model_dump(mode="json") for i in items],
        "notice": "Historical valuations are immutable point-in-time records.",
    }


@router.get("/portfolio/valuations/latest")
def valuations_latest(book_name: str = "default"):
    snap = valuation_snapshots.latest_snapshot(book_name)
    if not snap:
        return {"book_name": book_name, "snapshot": None, "notice": "No valuation snapshots yet."}
    return {"book_name": book_name, "snapshot": snap.model_dump(mode="json")}


@router.post("/portfolio/valuations/snapshot")
def valuations_snapshot(body: SnapshotRequest):
    if body.valuation_date and body.valuation_date > date.today():
        raise HTTPException(400, "valuation_date cannot be in the future")
    snap = valuation_snapshots.generate_snapshot(
        book_name=body.book_name,
        valuation_date=body.valuation_date,
        trigger=body.trigger,
    )
    return {"snapshot": snap.model_dump(mode="json")}


@router.get("/portfolio/drawdown")
def portfolio_drawdown(
    book_name: str = "default",
    start: date | None = None,
    end: date | None = None,
):
    items, _ = valuation_snapshots.list_snapshots(book_name=book_name, start=start, end=end, limit=500, offset=0)
    if not items:
        return {
            "book_name": book_name,
            "current": current_drawdown_from_latest(None),
            "max_drawdown_pct": "0",
            "episodes": [],
            "notice": "No snapshots — record valuations to build drawdown history.",
        }
    chron = sorted(items, key=lambda x: x.valuation_date)
    latest = valuation_snapshots.latest_snapshot(book_name)
    return {
        "book_name": book_name,
        "current": current_drawdown_from_latest(latest),
        "max_drawdown_pct": str(max_drawdown_over_period(chron)),
        "episodes": [
            {
                "peak_date": e.peak_date.isoformat(),
                "trough_date": e.trough_date.isoformat(),
                "peak_equity": str(e.peak_equity),
                "trough_equity": str(e.trough_equity),
                "max_drawdown_pct": str(e.max_drawdown_pct),
                "recovered": e.recovered,
                "recovery_date": e.recovery_date.isoformat() if e.recovery_date else None,
                "drawdown_days": e.drawdown_days,
                "recovery_days": e.recovery_days,
            }
            for e in episodes_from_snapshots(chron)
        ],
    }


@router.get("/portfolio/performance-history")
def portfolio_performance_history(
    book_name: str = "default",
    start: date | None = None,
    end: date | None = None,
    limit: int = Query(260, ge=1, le=500),
):
    items, total = valuation_snapshots.list_snapshots(book_name=book_name, start=start, end=end, limit=limit, offset=0)
    chron = sorted(items, key=lambda x: x.valuation_date)
    points = [
        PerformanceHistoryPoint(
            date=s.valuation_date.isoformat(),
            equity=str(s.portfolio_equity),
            drawdown_pct=str(s.drawdown_pct),
            swing_equity=str(s.swing_equity),
            positional_equity=str(s.positional_equity),
        ).model_dump()
        for s in chron
    ]
    return {
        "book_name": book_name,
        "total": total,
        "points": points,
        "source": "portfolio_valuation_snapshots",
        "notice": "Research book valuations only — not backtest equity curves.",
    }


@router.get("/portfolio/performance")
def portfolio_performance():
    s = manager.summary()
    return {
        "portfolio_value": str(s.portfolio_value),
        "realized_pnl": str(s.realized_pnl),
        "unrealized_pnl": str(s.unrealized_pnl),
        "current_drawdown_pct": str(s.current_drawdown_pct),
        "peak_value": str(s.peak_value),
        "open_risk": str(s.open_risk),
    }


@router.get("/portfolio/cash-ledger")
def portfolio_cash_ledger():
    return manager.cash_ledger()


@router.post("/portfolio/allocate")
def portfolio_allocate(req: AllocateRequest):
    proposals = allocator.generate_allocation_proposals(horizon=req.horizon, limit=req.limit)
    return {
        "count": len(proposals),
        "proposals": [p.model_dump(mode="json") for p in proposals],
        "notice": "Allocation proposals only — not executed purchases.",
    }


@router.post("/portfolio/allocation-proposals")
def create_allocation_proposals(req: AllocateRequest):
    return portfolio_allocate(req)


@router.get("/portfolio/allocation-proposals")
def list_allocation_proposals(status: str | None = None):
    items = store.list_proposals(status=status)
    return {"items": [p.model_dump(mode="json") for p in items], "total": len(items)}


@router.get("/portfolio/allocation-proposals/{proposal_id}")
def get_allocation_proposal(proposal_id: int):
    prop = store.get_proposal(proposal_id)
    if not prop:
        raise HTTPException(404, "Proposal not found")
    return prop.model_dump(mode="json")


@router.post("/portfolio/rebalance/propose")
def rebalance_propose():
    prop = rebalancing.propose_rebalance()
    return prop.model_dump(mode="json")


@router.get("/portfolio/rebalance/proposals")
def list_rebalance_proposals():
    state = store.load_book()
    return {"items": [r.model_dump(mode="json") for r in state.rebalance[:20]]}


@router.post("/portfolio/capital/add")
def add_capital(req: CapitalRequest):
    return manager.add_capital(D(req.amount), req.note or "Capital addition")


@router.post("/trades/buy")
def trade_buy(req: TradeRequest):
    raise HTTPException(403, LEGACY_TRADE_BLOCKED)


@router.post("/trades/sell")
def trade_sell(req: TradeRequest):
    raise HTTPException(403, LEGACY_TRADE_BLOCKED)


@router.get("/portfolio/positions")
def portfolio_positions_legacy():
    snap = legacy_portfolio_snapshot()
    return {"positions": snap.get("positions", []), "scope": "research_book"}