from datetime import date

import pandas as pd
from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.exceptions import HalalQuantError
from app.market_data.adjustments import fetch_corporate_actions, load_candles_with_adjusted
from app.market_data.ingestion import ingest_csv_bytes
from app.market_data.quality import quality_report_for_symbol, quality_report_universe
from app.market_data.repository import SymbolNotFoundError, get_history_dataframe, symbol_metadata
from app.models import MarketDataImport

router = APIRouter(tags=["market-data"])


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    return date.fromisoformat(value)


@router.post("/market-data/import/csv")
async def import_csv(
    file: UploadFile = File(...),
    conflict_policy: str | None = Query(default=None),
):
    content = await file.read()
    session = None
    try:
        if settings.database_enabled:
            if SessionLocal is None:
                raise HTTPException(503, "Database unavailable")
            session = SessionLocal()
        summary = ingest_csv_bytes(
            content,
            filename=file.filename,
            conflict_policy=conflict_policy,
            session=session,
        )
        return summary.model_dump()
    except HalalQuantError as e:
        raise HTTPException(e.status_code, detail={"message": e.message, "code": e.code}) from e
    finally:
        if session is not None:
            session.close()


def _require_db_session():
    if not settings.database_enabled or SessionLocal is None:
        raise HTTPException(503, "DATABASE_URL is required for this endpoint")
    return SessionLocal()


@router.get("/market-data/imports")
def list_imports(limit: int = 20):
    factory = _require_db_session()
    with factory() as db:
        rows = db.execute(select(MarketDataImport).order_by(MarketDataImport.id.desc()).limit(limit)).scalars()
        items = [
            {
                "id": r.id,
                "filename": r.filename,
                "status": r.status,
                "inserted_rows": r.inserted_rows,
                "updated_rows": r.updated_rows,
                "skipped_rows": r.skipped_rows,
                "symbols": r.symbols,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ]
    return {"items": items, "total": len(items)}


@router.get("/market-data/imports/{import_id}")
def get_import(import_id: int):
    factory = _require_db_session()
    with factory() as db:
        rec = db.get(MarketDataImport, import_id)
        if not rec:
            raise HTTPException(404, "Import not found")
        return {
            "id": rec.id,
            "filename": rec.filename,
            "status": rec.status,
            "conflict_policy": rec.conflict_policy,
            "total_rows_received": rec.total_rows_received,
            "valid_rows": rec.valid_rows,
            "rejected_rows": rec.rejected_rows,
            "inserted_rows": rec.inserted_rows,
            "updated_rows": rec.updated_rows,
            "skipped_rows": rec.skipped_rows,
            "duplicate_rows": rec.duplicate_rows,
            "symbols": rec.symbols,
            "date_range": {
                "start": rec.date_range_start.isoformat() if rec.date_range_start else None,
                "end": rec.date_range_end.isoformat() if rec.date_range_end else None,
            },
            "validation_summary": rec.validation_summary,
            "error_message": rec.error_message,
            "created_at": rec.created_at.isoformat() if rec.created_at else None,
            "completed_at": rec.completed_at.isoformat() if rec.completed_at else None,
        }


@router.get("/market-data/{symbol}/candles")
def candles(
    symbol: str,
    start: str | None = None,
    end: str | None = None,
    limit: int = 260,
    adjusted: bool = False,
):
    symbol = symbol.upper()
    start_d, end_d = _parse_date(start), _parse_date(end)
    try:
        if adjusted and settings.database_enabled and SessionLocal is not None:
            with SessionLocal() as session:
                df = load_candles_with_adjusted(session, symbol, use_adjusted=True)
        else:
            df = get_history_dataframe(symbol, limit=limit, start=start_d, end=end_d)
    except SymbolNotFoundError:
        raise HTTPException(404, "Unknown symbol") from None
    except HalalQuantError as e:
        raise HTTPException(e.status_code, e.message) from e

    if start_d:
        df = df[df["date"] >= pd.Timestamp(start_d)]
    if end_d:
        df = df[df["date"] <= pd.Timestamp(end_d)]
    df = df.tail(limit)

    out = []
    for row in df.itertuples():
        adj = getattr(row, "adjusted_close", None)
        out.append(
            {
                "trading_date": row.date.strftime("%Y-%m-%d"),
                "open": round(float(row.open), 4),
                "high": round(float(row.high), 4),
                "low": round(float(row.low), 4),
                "close": round(float(row.close), 4),
                "volume": int(row.volume),
                "adjusted_close": round(float(adj), 4) if adj is not None and pd.notna(adj) else None,
            }
        )
    return {"symbol": symbol, "adjusted": adjusted, "candles": out}


@router.get("/market-data/{symbol}/latest")
def latest_candle(symbol: str):
    try:
        meta = symbol_metadata(symbol)
        df = get_history_dataframe(symbol, limit=2)
    except SymbolNotFoundError:
        raise HTTPException(404, "Unknown symbol") from None
    row = df.iloc[-1]
    return {
        "symbol": symbol.upper(),
        "metadata": meta,
        "candle": {
            "trading_date": row["date"].strftime("%Y-%m-%d"),
            "close": round(float(row["close"]), 4),
            "volume": int(row["volume"]),
        },
    }


@router.post("/market-data/validate")
async def validate_csv(file: UploadFile = File(...)):
    content = await file.read()
    from app.market_data.normalization import read_csv_normalized
    from app.market_data.validation import validate_dataframe

    try:
        default_sym = file.filename.rsplit(".", 1)[0] if file.filename and "." in file.filename else None
        df = read_csv_normalized(content, default_symbol=default_sym)
        _, report = validate_dataframe(df)
        return {
            "filename": file.filename,
            "total_rows": len(df),
            "validation": report.to_summary_dict(),
            "issues": [i.model_dump(mode="json") for i in report.issues[:100]],
            "warnings": [w.model_dump(mode="json") for w in report.warnings[:100]],
            "missing_sessions": report.missing_sessions,
            "missing_sessions_approximate": report.missing_sessions_approximate,
        }
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.get("/market-data/quality/{symbol}")
def quality_symbol(symbol: str):
    rep = quality_report_for_symbol(symbol)
    if rep.get("status") == "not_found":
        raise HTTPException(404, "Unknown symbol")
    return rep


@router.get("/market-data/quality")
def quality_all():
    return quality_report_universe()


@router.get("/market-data/{symbol}/corporate-actions")
def corporate_actions(symbol: str):
    if not settings.database_enabled or SessionLocal is None:
        return {
            "symbol": symbol.upper(),
            "items": [],
            "notice": "No corporate actions loaded. Import verified records before using adjustments.",
        }
    with SessionLocal() as db:
        actions = fetch_corporate_actions(db, symbol)
    return {
        "symbol": symbol.upper(),
        "items": [
            {
                "action_type": a.action_type,
                "effective_date": a.effective_date.isoformat(),
                "ratio": float(a.ratio) if a.ratio is not None else None,
                "factor": float(a.factor) if a.factor is not None else None,
                "source": a.source,
                "notes": a.notes,
            }
            for a in actions
        ],
    }