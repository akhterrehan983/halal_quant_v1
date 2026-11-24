from __future__ import annotations

from datetime import datetime

from app.signals.config import DEFAULT_LIFECYCLE
from app.signals.schemas import ALLOWED_TRANSITIONS, LifecycleState, UnifiedSignal


class LifecycleError(ValueError):
    pass


def can_transition(current: LifecycleState, new: LifecycleState) -> bool:
    return new in ALLOWED_TRANSITIONS.get(current, set())


def transition(signal: UnifiedSignal, new_state: LifecycleState, reason: str) -> UnifiedSignal:
    if not can_transition(signal.lifecycle_state, new_state):
        raise LifecycleError(f"Invalid transition {signal.lifecycle_state} -> {new_state}")
    signal.lifecycle_state = new_state
    if new_state == LifecycleState.ACTIVE:
        signal.created_at = signal.created_at or datetime.utcnow()
    signal.rejection_reasons = list(signal.rejection_reasons) + [f"{new_state.value}: {reason}"]
    return signal


def activate_new_signal(signal: UnifiedSignal) -> UnifiedSignal:
    if signal.category.value == "NO_ACTION":
        return transition(signal, LifecycleState.REJECTED, "Category NO_ACTION")
    return transition(signal, LifecycleState.ACTIVE, "Initial activation")


def should_supersede(existing: UnifiedSignal, new: UnifiedSignal) -> bool:
    cfg = DEFAULT_LIFECYCLE
    if existing.horizon != new.horizon or existing.symbol != new.symbol:
        return False
    if abs(new.overall_score - existing.overall_score) >= cfg.score_change_supersede:
        return True
    if existing.entry_reference > 0:
        chg = abs(new.entry_reference - existing.entry_reference) / existing.entry_reference
        if chg >= cfg.entry_change_pct_supersede:
            return True
    return False


def is_expired(signal: UnifiedSignal, sessions_elapsed: int) -> bool:
    return sessions_elapsed >= signal.expires_after_sessions