"""CSV ingestion orchestration."""

from __future__ import annotations

import logging
from datetime import date

import pandas as pd
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.exceptions import HalalQuantError
from app.data import sample_data
from app.market_data.normalization import read_csv_normalized
from app.market_data.persistence import (
    create_import_record,
    finalize_import,
    persist_candles,
    require_database,
)
from app.market_data.schemas import ConflictPolicy, ImportSummary
from app.market_data.validation import rows_to_candles, validate_dataframe

logger = logging.getLogger(__name__)


def _date_range(df: pd.DataFrame) -> dict[str, str | None]:
    if df.empty:
        return {"start": None, "end": None}
    start = df["date"].min()
    end = df["date"].max()
    return {
        "start": start.date().isoformat() if hasattr(start, "date") else str(start)[:10],
        "end": end.date().isoformat() if hasattr(end, "date") else str(end)[:10],
    }


def _sync_demo_memory(df: pd.DataFrame) -> list[str]:
    """Demo mode: update in-memory HISTORIES used by legacy API."""
    updated: list[str] = []
    for symbol, grp in df.groupby("symbol"):
        sym = str(symbol).upper()
        out = grp.sort_values("date")[["date", "open", "high", "low", "close", "volume"]].reset_index(drop=True)
        if sym in sample_data.HISTORIES:
            existing = sample_data.HISTORIES[sym]
            merged = (
                pd.concat([existing, out])
                .drop_duplicates(subset=["date"], keep="last")
                .sort_values("date")
                .tail(3000)
                .reset_index(drop=True)
            )
            sample_data.HISTORIES[sym] = merged
        else:
            sample_data.HISTORIES[sym] = out.tail(3000)
            if sym not in sample_data.SYMBOLS:
                sample_data.SYMBOLS.append(sym)
        updated.append(sym)
    return updated


def ingest_csv_bytes(
    content: bytes,
    *,
    filename: str | None = None,
    default_symbol: str | None = None,
    conflict_policy: str | None = None,
    session: Session | None = None,
) -> ImportSummary:
    max_bytes = settings.csv_max_upload_mb * 1024 * 1024
    if len(content) > max_bytes:
        raise HalalQuantError(
            f"CSV exceeds limit of {settings.csv_max_upload_mb} MB",
            status_code=413,
            code="file_too_large",
        )

    policy = (conflict_policy or settings.import_conflict_policy).lower()
    if policy not in {p.value for p in ConflictPolicy}:
        raise HalalQuantError("Invalid conflict_policy", status_code=400, code="invalid_policy")

    default_sym = default_symbol
    if filename and "." in filename and not default_sym:
        default_sym = filename.rsplit(".", 1)[0]

    raw_df = read_csv_normalized(content, default_symbol=default_sym)
    total_rows = len(raw_df)
    valid_df, report = validate_dataframe(raw_df)
    candles = rows_to_candles(valid_df)
    symbols = sorted({c.symbol for c in candles})
    summary = ImportSummary(
        status="completed",
        filename=filename,
        total_rows_received=total_rows,
        valid_rows=report.valid_rows,
        rejected_rows=report.rejected_rows,
        duplicate_rows=report.duplicate_rows_in_file,
        symbols=symbols,
        date_range=_date_range(valid_df),
        conflict_policy=policy,
        validation=report.to_summary_dict(),
    )

    logger.info("import_started filename=%s rows=%s policy=%s", filename, total_rows, policy)

    if settings.database_enabled:
        own_session = session is None
        db = session or SessionLocal()
        if db is None:
            raise HalalQuantError("Database session unavailable", status_code=503, code="database_error")
        rec = create_import_record(db, filename=filename, conflict_policy=policy)
        try:
            inserted, updated, skipped, _ = persist_candles(
                db,
                candles,
                data_source="csv_upload",
                is_synthetic=False,
                conflict_policy=policy,  # type: ignore[arg-type]
            )
            summary.inserted_rows = inserted
            summary.updated_rows = updated
            summary.skipped_rows = skipped
            summary.import_id = rec.id
            finalize_import(db, rec, status="completed", summary=summary.model_dump())
            db.commit()
            logger.info(
                "import_completed id=%s inserted=%s updated=%s skipped=%s",
                rec.id,
                inserted,
                updated,
                skipped,
            )
        except Exception as exc:
            db.rollback()
            finalize_import(db, rec, status="failed", summary=summary.model_dump(), error=str(exc))
            db.commit()
            logger.exception("import_failed id=%s", rec.id)
            raise HalalQuantError(str(exc), status_code=500, code="import_failed") from exc
        finally:
            if own_session:
                db.close()
    else:
        if len(valid_df) < 60 and symbols and len(valid_df) == len(candles):
            # Per-symbol check
            for sym, grp in valid_df.groupby("symbol"):
                if len(grp) < 60:
                    raise HalalQuantError(
                        f"{sym}: at least 60 daily rows required",
                        status_code=400,
                        code="insufficient_history",
                    )
        _sync_demo_memory(valid_df)
        summary.inserted_rows = len(candles)
        summary.message = "Stored in demo in-memory universe (DATABASE_URL not set)"
        logger.info("import_completed_demo rows=%s symbols=%s", len(candles), symbols)

    return summary


def ingest_csv_bytes_db_required(content: bytes, **kwargs) -> ImportSummary:
    require_database()
    return ingest_csv_bytes(content, **kwargs)