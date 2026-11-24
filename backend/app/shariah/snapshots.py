from __future__ import annotations

from datetime import date, datetime

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.shariah_execution import ShariahSnapshotRow
from app.shariah.schemas import EligibilityRecord, ScreeningSnapshot
from app.shariah import store as sh_store


def append_snapshot(rec: EligibilityRecord) -> ScreeningSnapshot:
    snap = ScreeningSnapshot(
        snapshot_id=sh_store.next_snap_id(),
        symbol=rec.symbol,
        standard_id=rec.standard_id,
        standard_version=rec.standard_version,
        screening_date=rec.verified_at or date.today(),
        reporting_period=rec.ratios[0].reporting_period if rec.ratios else None,
        status=rec.status,
        payload=rec.model_dump(mode="json"),
        created_at=datetime.utcnow(),
    )
    sh_store.append_snapshot_memory(snap)
    if settings.database_enabled and SessionLocal:
        with SessionLocal() as session:
            session.add(
                ShariahSnapshotRow(
                    symbol=rec.symbol,
                    standard_id=rec.standard_id,
                    payload=snap.model_dump(mode="json"),
                )
            )
            session.commit()
    return snap