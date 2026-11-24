from __future__ import annotations

from datetime import datetime

from sqlalchemy import select

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.shariah_execution import ShariahEligibilityStore, ShariahSnapshotRow
from app.shariah.schemas import EligibilityRecord, ScreeningSnapshot

_ELIGIBILITY: dict[str, EligibilityRecord] = {}
_FINANCIALS: dict[str, dict] = {}
_SNAPSHOTS: list[ScreeningSnapshot] = []
_SNAP_SEQ = 0


def save_financials(symbol: str, data: dict) -> None:
    _FINANCIALS[symbol.upper()] = data
    if settings.database_enabled and SessionLocal:
        with SessionLocal() as session:
            row = session.execute(
                select(ShariahEligibilityStore).where(ShariahEligibilityStore.symbol == symbol.upper())
            ).scalar_one_or_none()
            payload = {"financials": data}
            if row:
                row.payload = {**(row.payload or {}), **payload}
            else:
                session.add(ShariahEligibilityStore(symbol=symbol.upper(), payload=payload))
            session.commit()


def get_financials(symbol: str) -> dict | None:
    if symbol.upper() in _FINANCIALS:
        return _FINANCIALS[symbol.upper()]
    if settings.database_enabled and SessionLocal:
        with SessionLocal() as session:
            row = session.execute(
                select(ShariahEligibilityStore).where(ShariahEligibilityStore.symbol == symbol.upper())
            ).scalar_one_or_none()
            if row and row.payload:
                return row.payload.get("financials")
    return None


def save_eligibility(rec: EligibilityRecord) -> None:
    _ELIGIBILITY[rec.symbol.upper()] = rec
    if settings.database_enabled and SessionLocal:
        with SessionLocal() as session:
            row = session.execute(
                select(ShariahEligibilityStore).where(ShariahEligibilityStore.symbol == rec.symbol.upper())
            ).scalar_one_or_none()
            payload = rec.model_dump(mode="json")
            if row:
                row.payload = {**(row.payload or {}), "latest": payload}
            else:
                session.add(ShariahEligibilityStore(symbol=rec.symbol.upper(), payload={"latest": payload}))
            session.commit()


def get_latest_eligibility(symbol: str) -> EligibilityRecord | None:
    if symbol.upper() in _ELIGIBILITY:
        return _ELIGIBILITY[symbol.upper()]
    if settings.database_enabled and SessionLocal:
        with SessionLocal() as session:
            row = session.execute(
                select(ShariahEligibilityStore).where(ShariahEligibilityStore.symbol == symbol.upper())
            ).scalar_one_or_none()
            if row and row.payload and row.payload.get("latest"):
                return EligibilityRecord.model_validate(row.payload["latest"])
    return None


def list_snapshots(symbol: str) -> list[ScreeningSnapshot]:
    sym = symbol.upper()
    items = [s for s in _SNAPSHOTS if s.symbol == sym]
    if settings.database_enabled and SessionLocal:
        with SessionLocal() as session:
            rows = session.execute(
                select(ShariahSnapshotRow).where(ShariahSnapshotRow.symbol == sym).order_by(ShariahSnapshotRow.id.desc())
            ).scalars()
            for r in rows:
                items.append(ScreeningSnapshot.model_validate(r.payload))
    return sorted(items, key=lambda x: x.snapshot_id or 0, reverse=True)


def next_snap_id() -> int:
    global _SNAP_SEQ
    _SNAP_SEQ += 1
    return _SNAP_SEQ


def append_snapshot_memory(snap: ScreeningSnapshot) -> None:
    _SNAPSHOTS.append(snap)