"""PostgreSQL persistence for OHLCV candles and import metadata."""

from __future__ import annotations

import logging
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

import pandas as pd
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import HalalQuantError
from app.market_data.schemas import CandleRow, ConflictPolicy
from app.models import MarketDataImport, OHLCVCandle, Stock

logger = logging.getLogger(__name__)

ConflictMode = Literal["reject", "skip", "update"]


def require_database() -> None:
    if not settings.database_enabled:
        raise HalalQuantError(
            "DATABASE_URL is not configured; persistence requires PostgreSQL",
            status_code=503,
            code="database_disabled",
        )


def ensure_stock(session: Session, symbol: str, *, is_synthetic: bool, data_source: str) -> Stock:
    stock = session.execute(select(Stock).where(Stock.symbol == symbol)).scalar_one_or_none()
    if stock:
        return stock
    stock = Stock(
        symbol=symbol,
        exchange="NSE",
        data_source=data_source,
        is_synthetic=is_synthetic,
        is_active=True,
    )
    session.add(stock)
    session.flush()
    return stock


def existing_dates(session: Session, symbol: str, dates: list[date]) -> set[date]:
    if not dates:
        return set()
    rows = session.execute(
        select(OHLCVCandle.trading_date).where(
            OHLCVCandle.symbol == symbol,
            OHLCVCandle.trading_date.in_(dates),
        )
    ).scalars()
    return set(rows)


def persist_candles(
    session: Session,
    candles: list[CandleRow],
    *,
    data_source: str,
    is_synthetic: bool,
    conflict_policy: ConflictMode,
) -> tuple[int, int, int, int]:
    """Bulk insert with conflict handling. Returns inserted, updated, skipped, duplicate conflicts."""
    inserted = updated = skipped = conflicts = 0
    if not candles:
        return inserted, updated, skipped, conflicts

    by_symbol: dict[str, list[CandleRow]] = {}
    for c in candles:
        by_symbol.setdefault(c.symbol, []).append(c)

    for symbol, rows in by_symbol.items():
        stock = ensure_stock(session, symbol, is_synthetic=is_synthetic, data_source=data_source)
        dates = [r.trading_date for r in rows]
        existing = existing_dates(session, symbol, dates)

        for row in rows:
            if row.trading_date in existing:
                if conflict_policy == "skip":
                    skipped += 1
                    continue
                if conflict_policy == "reject":
                    conflicts += 1
                    raise HalalQuantError(
                        f"Conflict for {symbol} on {row.trading_date}",
                        status_code=409,
                        code="candle_conflict",
                    )
                # update
                candle = session.execute(
                    select(OHLCVCandle).where(
                        OHLCVCandle.symbol == symbol,
                        OHLCVCandle.trading_date == row.trading_date,
                    )
                ).scalar_one()
                candle.open = Decimal(str(row.open))
                candle.high = Decimal(str(row.high))
                candle.low = Decimal(str(row.low))
                candle.close = Decimal(str(row.close))
                candle.volume = row.volume
                candle.data_source = data_source
                candle.is_synthetic = is_synthetic
                candle.updated_at = datetime.utcnow()
                updated += 1
                continue

            session.add(
                OHLCVCandle(
                    stock_id=stock.id,
                    symbol=symbol,
                    exchange=row.exchange,
                    trading_date=row.trading_date,
                    open=Decimal(str(row.open)),
                    high=Decimal(str(row.high)),
                    low=Decimal(str(row.low)),
                    close=Decimal(str(row.close)),
                    volume=row.volume,
                    adjusted_close=Decimal(str(row.adjusted_close))
                    if row.adjusted_close is not None
                    else None,
                    data_source=data_source,
                    is_synthetic=is_synthetic,
                )
            )
            inserted += 1
            existing.add(row.trading_date)

    return inserted, updated, skipped, conflicts


def candles_to_dataframe(candles: list[OHLCVCandle]) -> pd.DataFrame:
    rows = []
    for c in candles:
        rows.append(
            {
                "date": pd.Timestamp(c.trading_date),
                "open": float(c.open),
                "high": float(c.high),
                "low": float(c.low),
                "close": float(c.close),
                "volume": int(c.volume),
                "symbol": c.symbol,
            }
        )
    if not rows:
        return pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume", "symbol"])
    return pd.DataFrame(rows).sort_values("date").reset_index(drop=True)


def fetch_candles(
    session: Session,
    symbol: str,
    *,
    start: date | None = None,
    end: date | None = None,
    limit: int | None = None,
) -> list[OHLCVCandle]:
    stmt = select(OHLCVCandle).where(OHLCVCandle.symbol == symbol.upper()).order_by(OHLCVCandle.trading_date)
    if start:
        stmt = stmt.where(OHLCVCandle.trading_date >= start)
    if end:
        stmt = stmt.where(OHLCVCandle.trading_date <= end)
    if limit:
        stmt = stmt.limit(limit)
    return list(session.execute(stmt).scalars().all())


def symbol_date_range(session: Session, symbol: str) -> tuple[date | None, date | None]:
    row = session.execute(
        select(func.min(OHLCVCandle.trading_date), func.max(OHLCVCandle.trading_date)).where(
            OHLCVCandle.symbol == symbol.upper()
        )
    ).one()
    return row[0], row[1]


def list_db_symbols(session: Session) -> list[str]:
    return list(session.execute(select(Stock.symbol).where(Stock.is_active.is_(True))).scalars().all())


def create_import_record(
    session: Session,
    *,
    filename: str | None,
    conflict_policy: str,
) -> MarketDataImport:
    rec = MarketDataImport(filename=filename, conflict_policy=conflict_policy, status="running")
    session.add(rec)
    session.flush()
    return rec


def finalize_import(
    session: Session,
    rec: MarketDataImport,
    *,
    status: str,
    summary: dict,
    error: str | None = None,
) -> None:
    rec.status = status
    rec.total_rows_received = summary.get("total_rows_received", 0)
    rec.valid_rows = summary.get("valid_rows", 0)
    rec.rejected_rows = summary.get("rejected_rows", 0)
    rec.inserted_rows = summary.get("inserted_rows", 0)
    rec.updated_rows = summary.get("updated_rows", 0)
    rec.skipped_rows = summary.get("skipped_rows", 0)
    rec.duplicate_rows = summary.get("duplicate_rows", 0)
    rec.symbols = summary.get("symbols", [])
    dr = summary.get("date_range", {})
    if dr.get("start"):
        rec.date_range_start = date.fromisoformat(dr["start"])
    if dr.get("end"):
        rec.date_range_end = date.fromisoformat(dr["end"])
    rec.validation_summary = summary.get("validation", {})
    rec.error_message = error
    rec.completed_at = datetime.utcnow()