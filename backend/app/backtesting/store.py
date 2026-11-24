from __future__ import annotations

from datetime import datetime

from sqlalchemy import select

from app.core.config import settings
from app.core.database import SessionLocal
from app.backtesting.schemas import BacktestRun, BacktestStatus
from app.models.backtesting import BacktestRunRow

_MEM: dict[int, BacktestRun] = {}
_SEQ = 0


def next_id() -> int:
    global _SEQ
    _SEQ += 1
    return _SEQ


def save_run(run: BacktestRun) -> BacktestRun:
    if run.backtest_id is None:
        run.backtest_id = next_id()
    run.created_at = run.created_at or datetime.utcnow()
    if run.status == BacktestStatus.COMPLETED:
        run.completed_at = datetime.utcnow()
    payload = run.model_dump(mode="json")
    if settings.database_enabled and SessionLocal:
        with SessionLocal() as session:
            row = session.get(BacktestRunRow, run.backtest_id)
            if not row:
                row = BacktestRunRow(id=run.backtest_id, name=run.config.name, status=run.status.value, payload=payload)
                session.add(row)
            else:
                row.status = run.status.value
                row.payload = payload
                row.updated_at = datetime.utcnow()
            session.commit()
    else:
        _MEM[run.backtest_id] = run
    return run


def get_run(backtest_id: int) -> BacktestRun | None:
    if settings.database_enabled and SessionLocal:
        with SessionLocal() as session:
            row = session.get(BacktestRunRow, backtest_id)
            if row:
                return BacktestRun.model_validate(row.payload)
    return _MEM.get(backtest_id)


def list_runs() -> list[BacktestRun]:
    if settings.database_enabled and SessionLocal:
        with SessionLocal() as session:
            rows = session.execute(select(BacktestRunRow).order_by(BacktestRunRow.id.desc()).limit(50)).scalars()
            return [BacktestRun.model_validate(r.payload) for r in rows]
    return list(_MEM.values())