"""Ownership / possession policy — conservative delivery default."""

from __future__ import annotations

from datetime import datetime

from app.shariah.schemas import OwnershipEvent, OwnershipPossessionState

OWNERSHIP_TRANSITIONS: dict[OwnershipPossessionState, set[OwnershipPossessionState]] = {
    OwnershipPossessionState.NOT_OWNED: {OwnershipPossessionState.ORDER_PENDING, OwnershipPossessionState.EXECUTED_UNSETTLED},
    OwnershipPossessionState.ORDER_PENDING: {
        OwnershipPossessionState.EXECUTED_UNSETTLED,
        OwnershipPossessionState.NOT_OWNED,
    },
    OwnershipPossessionState.EXECUTED_UNSETTLED: {
        OwnershipPossessionState.SETTLED_PENDING_VERIFICATION,
    },
    OwnershipPossessionState.SETTLED_PENDING_VERIFICATION: {
        OwnershipPossessionState.OWNERSHIP_VERIFIED,
        OwnershipPossessionState.REVIEW_REQUIRED,
    },
    OwnershipPossessionState.OWNERSHIP_VERIFIED: {
        OwnershipPossessionState.POSSESSION_VERIFIED,
        OwnershipPossessionState.REVIEW_REQUIRED,
    },
    OwnershipPossessionState.POSSESSION_VERIFIED: {
        OwnershipPossessionState.SELL_AUTHORIZED,
        OwnershipPossessionState.REVIEW_REQUIRED,
    },
    OwnershipPossessionState.SELL_AUTHORIZED: {OwnershipPossessionState.OWNERSHIP_REVERSED},
    OwnershipPossessionState.REVIEW_REQUIRED: {
        OwnershipPossessionState.OWNERSHIP_VERIFIED,
        OwnershipPossessionState.POSSESSION_VERIFIED,
        OwnershipPossessionState.SELL_AUTHORIZED,
    },
}


def can_transition(current: OwnershipPossessionState, new: OwnershipPossessionState) -> bool:
    return new in OWNERSHIP_TRANSITIONS.get(current, set())


def transition(
    symbol: str,
    current: OwnershipPossessionState,
    new: OwnershipPossessionState,
    *,
    evidence: str,
    verifier: str | None = None,
    reason: str = "",
) -> OwnershipEvent:
    if not can_transition(current, new):
        raise ValueError(f"Invalid ownership transition {current} -> {new}")
    return OwnershipEvent(
        symbol=symbol.upper(),
        state=new,
        timestamp=datetime.utcnow(),
        evidence=evidence,
        verifier=verifier,
        reason=reason,
    )


CONSERVATIVE_POLICY_ID = "conservative_delivery"