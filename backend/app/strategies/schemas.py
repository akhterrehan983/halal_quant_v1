from datetime import date
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class SignalDirection(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"
    NO_SIGNAL = "NO_SIGNAL"


class StrategyResultModel(BaseModel):
    strategy_id: str
    strategy_name: str
    symbol: str
    evaluation_date: date
    horizon: str
    direction: SignalDirection
    score: int = Field(ge=0, le=100)
    strength: str = "moderate"
    entry_price: float
    stop_loss: float
    target: float
    risk_reward: float
    rationale: str
    rejection_reasons: list[str] = Field(default_factory=list)
    conditions_met: list[str] = Field(default_factory=list)
    features_used: dict[str, Any] = Field(default_factory=dict)
    parameters_version: str = "0.3.0"
    triggered: bool = False

    def to_legacy_dict(self) -> dict[str, Any]:
        """Backward-compatible payload for legacy `/api/signals` responses."""
        if self.direction == SignalDirection.BUY and self.triggered and self.score >= 70:
            signal = "BUY"
        elif self.score >= 50:
            signal = "WATCHLIST"
        else:
            signal = "NO ACTION"
        return {
            "strategy": self.strategy_name,
            "signal": signal,
            "score": self.score,
            "rationale": self.rationale,
            "entry_price": self.entry_price,
            "stop_loss": self.stop_loss,
            "target": self.target,
            "risk_reward": self.risk_reward,
        }

    def to_api_dict(self) -> dict[str, Any]:
        d = self.model_dump(mode="json")
        d["direction"] = self.direction.value
        d["legacy_signal"] = self.to_legacy_dict()["signal"]
        return d