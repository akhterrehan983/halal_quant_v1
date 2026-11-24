from datetime import date, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from app.regime.schemas import MarketRegimeLabel


class SignalCategory(str, Enum):
    STRONG_BUY = "STRONG_BUY"
    BUY = "BUY"
    WATCHLIST = "WATCHLIST"
    NO_ACTION = "NO_ACTION"


class LifecycleState(str, Enum):
    CREATED = "CREATED"
    ACTIVE = "ACTIVE"
    EXPIRED = "EXPIRED"
    SUPERSEDED = "SUPERSEDED"
    ENTERED = "ENTERED"
    HOLDING = "HOLDING"
    EXIT_TRIGGERED = "EXIT_TRIGGERED"
    CLOSED = "CLOSED"
    REJECTED = "REJECTED"


ALLOWED_TRANSITIONS: dict[LifecycleState, set[LifecycleState]] = {
    LifecycleState.CREATED: {LifecycleState.ACTIVE, LifecycleState.REJECTED},
    LifecycleState.ACTIVE: {
        LifecycleState.EXPIRED,
        LifecycleState.SUPERSEDED,
        LifecycleState.ENTERED,
        LifecycleState.REJECTED,
    },
    LifecycleState.ENTERED: {LifecycleState.HOLDING, LifecycleState.CLOSED},
    LifecycleState.HOLDING: {LifecycleState.EXIT_TRIGGERED, LifecycleState.CLOSED},
    LifecycleState.EXIT_TRIGGERED: {LifecycleState.CLOSED},
}


class StrategyContribution(BaseModel):
    strategy_id: str
    strategy_name: str
    direction: str
    score: int
    legacy_signal: str
    rationale: str
    weight_in_consensus: float = 1.0


class ScoreBreakdown(BaseModel):
    momentum_quality: float = 0
    trend_quality: float = 0
    setup_quality: float = 0
    relative_strength: float = 0
    volume_confirmation: float = 0
    regime_alignment: float = 0
    total: int = 0
    explanations: list[str] = Field(default_factory=list)


class UnifiedSignal(BaseModel):
    symbol: str
    horizon: str
    evaluation_date: date
    category: SignalCategory
    overall_score: int
    lifecycle_state: LifecycleState = LifecycleState.CREATED
    market_regime: MarketRegimeLabel | str
    regime_confidence: float = 0.0
    entry_reference: float
    stop_reference: float
    target_reference: float
    relative_strength: dict[str, float | None] = Field(default_factory=dict)
    contributions: list[StrategyContribution] = Field(default_factory=list)
    conflicting_strategies: list[str] = Field(default_factory=list)
    consensus_effective_buys: float = 0.0
    agreement_level: str = "low"
    score_breakdown: ScoreBreakdown
    rejection_reasons: list[str] = Field(default_factory=list)
    strategy_results: list[dict[str, Any]] = Field(default_factory=list)
    signal_id: int | None = None
    created_at: datetime | None = None
    expires_after_sessions: int = 15