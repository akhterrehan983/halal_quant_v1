from dataclasses import dataclass, field


@dataclass(frozen=True)
class ScoringWeights:
    momentum_quality: int = 25
    trend_quality: int = 20
    setup_quality: int = 20
    relative_strength: int = 15
    volume_confirmation: int = 10
    regime_alignment: int = 10

    def validate(self) -> None:
        total = (
            self.momentum_quality
            + self.trend_quality
            + self.setup_quality
            + self.relative_strength
            + self.volume_confirmation
            + self.regime_alignment
        )
        if total != 100:
            raise ValueError(f"Scoring weights must sum to 100, got {total}")


DEFAULT_WEIGHTS = ScoringWeights()
DEFAULT_WEIGHTS.validate()

CORRELATED_STRATEGY_GROUPS = (
    {"momentum", "high_momentum"},
    {"breakout", "trend_following"},
)


@dataclass(frozen=True)
class CategoryThresholds:
    strong_buy: int = 85
    buy: int = 75
    watchlist: int = 60


@dataclass(frozen=True)
class LifecycleConfig:
    swing_max_sessions: int = 15
    positional_max_sessions: int = 120
    score_change_supersede: int = 8
    entry_change_pct_supersede: float = 0.02


DEFAULT_CATEGORIES = CategoryThresholds()
DEFAULT_LIFECYCLE = LifecycleConfig()