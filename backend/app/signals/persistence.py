"""Signal persistence — PostgreSQL or in-memory demo store."""

from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.exceptions import HalalQuantError
from app.models.signals import ResearchSignal, SignalLifecycleEvent
from app.signals.lifecycle import activate_new_signal, should_supersede, transition
from app.signals.schemas import LifecycleState, UnifiedSignal

logger = logging.getLogger(__name__)

_MEM_SIGNALS: dict[int, UnifiedSignal] = {}
_MEM_EVENTS: list[dict] = []
_MEM_SEQ = 0


def _next_id() -> int:
    global _MEM_SEQ
    _MEM_SEQ += 1
    return _MEM_SEQ


def _active_memory(symbol: str, horizon: str) -> UnifiedSignal | None:
    for sig in _MEM_SIGNALS.values():
        if (
            sig.symbol == symbol.upper()
            and sig.horizon == horizon
            and sig.lifecycle_state == LifecycleState.ACTIVE
        ):
            return sig
    return None


def _active_db(session: Session, symbol: str, horizon: str) -> ResearchSignal | None:
    return session.execute(
        select(ResearchSignal)
        .where(
            ResearchSignal.symbol == symbol.upper(),
            ResearchSignal.horizon == horizon,
            ResearchSignal.lifecycle_state == LifecycleState.ACTIVE.value,
        )
        .order_by(ResearchSignal.id.desc())
    ).scalar_one_or_none()


def persist_signal(signal: UnifiedSignal) -> UnifiedSignal:
    signal = activate_new_signal(signal)
    existing = None
    if settings.database_enabled and SessionLocal:
        with SessionLocal() as session:
            existing_rec = _active_db(session, signal.symbol, signal.horizon)
            if existing_rec:
                existing = UnifiedSignal.model_validate(existing_rec.payload)
                existing.signal_id = existing_rec.id
            if existing and should_supersede(existing, signal):
                transition(existing, LifecycleState.SUPERSEDED, "Superseded by newer evaluation")
                rec = session.get(ResearchSignal, existing.signal_id)
                if rec:
                    rec.lifecycle_state = LifecycleState.SUPERSEDED.value
                    rec.payload = existing.model_dump(mode="json")
                    rec.updated_at = datetime.utcnow()
                    session.add(
                        SignalLifecycleEvent(
                            signal_id=existing.signal_id,
                            from_state=LifecycleState.ACTIVE.value,
                            to_state=LifecycleState.SUPERSEDED.value,
                            reason="superseded",
                        )
                    )
            elif existing and not should_supersede(existing, signal):
                signal.signal_id = existing.signal_id
                signal.lifecycle_state = LifecycleState.ACTIVE
                return signal
            signal = _save_db(session, signal, event_reason="created")
            session.commit()
            logger.info("signal_persisted id=%s symbol=%s", signal.signal_id, signal.symbol)
            return signal

    existing = _active_memory(signal.symbol, signal.horizon)
    if existing and should_supersede(existing, signal):
        transition(existing, LifecycleState.SUPERSEDED, "Superseded by newer evaluation")
        _MEM_SIGNALS[existing.signal_id] = existing
        _MEM_EVENTS.append(
            {
                "signal_id": existing.signal_id,
                "from_state": LifecycleState.ACTIVE.value,
                "to_state": LifecycleState.SUPERSEDED.value,
                "reason": "superseded",
            }
        )
    elif existing and not should_supersede(existing, signal):
        signal.signal_id = existing.signal_id
        signal.lifecycle_state = LifecycleState.ACTIVE
        return signal

    sid = _next_id()
    signal.signal_id = sid
    signal.created_at = datetime.utcnow()
    _MEM_SIGNALS[sid] = signal
    _MEM_EVENTS.append(
        {
            "signal_id": sid,
            "from_state": LifecycleState.CREATED.value,
            "to_state": signal.lifecycle_state.value,
            "reason": "demo_store",
        }
    )
    return signal


def _save_db(session: Session, signal: UnifiedSignal, *, event_reason: str) -> UnifiedSignal:
    payload = signal.model_dump(mode="json")
    if signal.signal_id:
        rec = session.get(ResearchSignal, signal.signal_id)
        if rec:
            rec.category = signal.category.value
            rec.overall_score = signal.overall_score
            rec.lifecycle_state = signal.lifecycle_state.value
            rec.payload = payload
            rec.updated_at = datetime.utcnow()
    else:
        rec = ResearchSignal(
            symbol=signal.symbol,
            horizon=signal.horizon,
            evaluation_date=signal.evaluation_date,
            category=signal.category.value,
            overall_score=signal.overall_score,
            lifecycle_state=signal.lifecycle_state.value,
            market_regime=str(signal.market_regime),
            entry_reference=signal.entry_reference,
            stop_reference=signal.stop_reference,
            target_reference=signal.target_reference,
            payload=payload,
            expires_after_sessions=signal.expires_after_sessions,
        )
        session.add(rec)
        session.flush()
        signal.signal_id = rec.id
    session.add(
        SignalLifecycleEvent(
            signal_id=signal.signal_id,
            from_state=LifecycleState.CREATED.value,
            to_state=signal.lifecycle_state.value,
            reason=event_reason,
        )
    )
    return signal


def list_persisted_signals(
    *,
    symbol: str | None = None,
    horizon: str | None = None,
    lifecycle: str | None = None,
    category: str | None = None,
) -> list[UnifiedSignal]:
    if settings.database_enabled and SessionLocal:
        with SessionLocal() as session:
            stmt = select(ResearchSignal).order_by(ResearchSignal.id.desc())
            if symbol:
                stmt = stmt.where(ResearchSignal.symbol == symbol.upper())
            if horizon:
                stmt = stmt.where(ResearchSignal.horizon == horizon)
            if lifecycle:
                stmt = stmt.where(ResearchSignal.lifecycle_state == lifecycle)
            if category:
                stmt = stmt.where(ResearchSignal.category == category)
            rows = session.execute(stmt.limit(200)).scalars().all()
            return [UnifiedSignal.model_validate(r.payload) for r in rows]

    out = []
    for sig in _MEM_SIGNALS.values():
        if symbol and sig.symbol != symbol.upper():
            continue
        if horizon and sig.horizon != horizon:
            continue
        if lifecycle and sig.lifecycle_state.value != lifecycle:
            continue
        if category and sig.category.value != category:
            continue
        out.append(sig)
    return sorted(out, key=lambda s: s.signal_id or 0, reverse=True)


def get_signal_by_id(signal_id: int) -> UnifiedSignal:
    if settings.database_enabled and SessionLocal:
        with SessionLocal() as session:
            rec = session.get(ResearchSignal, signal_id)
            if not rec:
                raise HalalQuantError("Signal not found", status_code=404, code="not_found")
            return UnifiedSignal.model_validate(rec.payload)
    if signal_id not in _MEM_SIGNALS:
        raise HalalQuantError("Signal not found", status_code=404, code="not_found")
    return _MEM_SIGNALS[signal_id]


def signal_history(signal_id: int) -> list[dict]:
    if settings.database_enabled and SessionLocal:
        with SessionLocal() as session:
            events = session.execute(
                select(SignalLifecycleEvent)
                .where(SignalLifecycleEvent.signal_id == signal_id)
                .order_by(SignalLifecycleEvent.id)
            ).scalars()
            return [
                {
                    "from_state": e.from_state,
                    "to_state": e.to_state,
                    "reason": e.reason,
                    "created_at": e.created_at.isoformat() if e.created_at else None,
                }
                for e in events
            ]
    return [e for e in _MEM_EVENTS if e["signal_id"] == signal_id]