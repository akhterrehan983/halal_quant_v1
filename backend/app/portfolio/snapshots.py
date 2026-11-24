"""Immutable valuation snapshot persistence (PostgreSQL or in-memory)."""

from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.portfolio_risk import PortfolioBook
from app.models.portfolio_valuation import PortfolioValuationSnapshot
from app.portfolio import store
from app.portfolio.money import money
from app.portfolio.valuation import compute_portfolio_valuation, resolve_holdings_prices
from app.portfolio.valuation_schemas import SnapshotTrigger, ValuationSnapshotRecord

_MEM: list[ValuationSnapshotRecord] = []
_MEM_SEQ = 0


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _book_row_id(book_name: str) -> int | None:
    if not settings.database_enabled or not SessionLocal:
        return None
    with SessionLocal() as session:
        row = session.execute(select(PortfolioBook).where(PortfolioBook.name == book_name)).scalar_one_or_none()
        return row.id if row else None


def _get_daily(book_name: str, valuation_date: date, trigger: SnapshotTrigger) -> ValuationSnapshotRecord | None:
    if settings.database_enabled and SessionLocal:
        with SessionLocal() as session:
            row = session.execute(
                select(PortfolioValuationSnapshot).where(
                    PortfolioValuationSnapshot.book_name == book_name,
                    PortfolioValuationSnapshot.valuation_date == valuation_date,
                    PortfolioValuationSnapshot.trigger == trigger.value,
                )
            ).scalar_one_or_none()
            if row:
                return ValuationSnapshotRecord.from_row(row)
    for s in _MEM:
        if s.book_name == book_name and s.valuation_date == valuation_date and s.trigger == trigger:
            return s
    return None


def _insert_record(rec: ValuationSnapshotRecord) -> ValuationSnapshotRecord:
    global _MEM_SEQ
    if settings.database_enabled and SessionLocal:
        row = PortfolioValuationSnapshot(
            book_name=rec.book_name,
            portfolio_book_id=rec.portfolio_book_id,
            valued_at=rec.valued_at,
            valuation_date=rec.valuation_date,
            trigger=rec.trigger.value,
            portfolio_equity=rec.portfolio_equity,
            available_cash=rec.available_cash,
            reserved_cash=rec.reserved_cash,
            invested_market_value=rec.invested_market_value,
            realized_pnl=rec.realized_pnl,
            unrealized_pnl=rec.unrealized_pnl,
            total_pnl=rec.total_pnl,
            swing_equity=rec.swing_equity,
            positional_equity=rec.positional_equity,
            cash_reserve=rec.cash_reserve,
            equity_peak_prior=rec.equity_peak_prior,
            equity_peak_at_snapshot=rec.equity_peak_at_snapshot,
            drawdown_amount=rec.drawdown_amount,
            drawdown_pct=rec.drawdown_pct,
            price_quality_json=rec.price_quality,
            valuation_complete=rec.valuation_complete,
        )
        try:
            with SessionLocal() as session:
                session.add(row)
                session.commit()
                session.refresh(row)
                return ValuationSnapshotRecord.from_row(row)
        except IntegrityError:
            existing = _get_daily(rec.book_name, rec.valuation_date, rec.trigger)
            if existing:
                return existing
            raise
    _MEM_SEQ += 1
    stored = rec.model_copy(update={"snapshot_id": _MEM_SEQ})
    _MEM.append(stored)
    return stored


def generate_snapshot(
    *,
    book_name: str = "default",
    valuation_date: date | None = None,
    trigger: SnapshotTrigger = SnapshotTrigger.ON_DEMAND,
    update_book_peak: bool = True,
) -> ValuationSnapshotRecord:
    """Create one immutable snapshot; daily trigger is idempotent per valuation_date."""
    vdate = valuation_date or _utc_now().date()
    if trigger == SnapshotTrigger.DAILY:
        existing = _get_daily(book_name, vdate, trigger)
        if existing:
            return existing

    state = store.load_book()
    if book_name != "default" and settings.database_enabled:
        pass  # single default book in M12
    resolution = resolve_holdings_prices(state.all_holdings(), strict=True)
    metrics = compute_portfolio_valuation(state, resolution)

    if update_book_peak:
        state.peak_value = metrics["equity_peak_at_snapshot"]
        state.last_valuation_date = vdate
        store.save_book(state)

    rec = ValuationSnapshotRecord(
        snapshot_id=0,
        book_name=book_name,
        portfolio_book_id=_book_row_id(book_name),
        valued_at=_utc_now(),
        valuation_date=vdate,
        trigger=trigger,
        portfolio_equity=metrics["portfolio_equity"],
        available_cash=metrics["available_cash"],
        reserved_cash=metrics["reserved_cash"],
        invested_market_value=metrics["invested_market_value"],
        realized_pnl=metrics["realized_pnl"],
        unrealized_pnl=metrics["unrealized_pnl"],
        total_pnl=metrics["total_pnl"],
        swing_equity=metrics["swing_equity"],
        positional_equity=metrics["positional_equity"],
        cash_reserve=metrics["cash_reserve"],
        equity_peak_prior=metrics["equity_peak_prior"],
        equity_peak_at_snapshot=metrics["equity_peak_at_snapshot"],
        drawdown_amount=metrics["drawdown_amount"],
        drawdown_pct=metrics["drawdown_pct"],
        price_quality=metrics["price_quality"],
        valuation_complete=metrics["valuation_complete"],
    )
    return _insert_record(rec)


def list_snapshots(
    *,
    book_name: str = "default",
    start: date | None = None,
    end: date | None = None,
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[ValuationSnapshotRecord], int]:
    limit = min(max(limit, 1), 500)
    offset = max(offset, 0)
    if settings.database_enabled and SessionLocal:
        with SessionLocal() as session:
            q = select(PortfolioValuationSnapshot).where(PortfolioValuationSnapshot.book_name == book_name)
            if start:
                q = q.where(PortfolioValuationSnapshot.valuation_date >= start)
            if end:
                q = q.where(PortfolioValuationSnapshot.valuation_date <= end)
            rows = (
                session.execute(q.order_by(PortfolioValuationSnapshot.valuation_date.desc(), PortfolioValuationSnapshot.id.desc()))
                .scalars()
                .all()
            )
            total = len(rows)
            page = rows[offset : offset + limit]
            return [ValuationSnapshotRecord.from_row(r) for r in page], total
    filtered = [s for s in _MEM if s.book_name == book_name]
    if start:
        filtered = [s for s in filtered if s.valuation_date >= start]
    if end:
        filtered = [s for s in filtered if s.valuation_date <= end]
    filtered.sort(key=lambda s: (s.valuation_date, s.valued_at), reverse=True)
    total = len(filtered)
    return filtered[offset : offset + limit], total


def latest_snapshot(book_name: str = "default") -> ValuationSnapshotRecord | None:
    items, _ = list_snapshots(book_name=book_name, limit=1)
    return items[0] if items else None


def clear_mem_snapshots_for_tests() -> None:
    global _MEM, _MEM_SEQ
    _MEM = []
    _MEM_SEQ = 0