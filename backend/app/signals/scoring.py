from __future__ import annotations

from app.regime.schemas import MarketRegimeLabel
from app.signals.config import DEFAULT_WEIGHTS, ScoringWeights
from app.signals.schemas import ScoreBreakdown, SignalCategory
from app.strategies.schemas import SignalDirection, StrategyResultModel


def category_from_score(score: int, *, hard_reject: bool) -> SignalCategory:
    if hard_reject:
        return SignalCategory.NO_ACTION
    if score >= 85:
        return SignalCategory.STRONG_BUY
    if score >= 75:
        return SignalCategory.BUY
    if score >= 60:
        return SignalCategory.WATCHLIST
    return SignalCategory.NO_ACTION


def _clamp(v: float, lo=0.0, hi=1.0) -> float:
    return max(lo, min(hi, v))


def score_signal(
    results: list[StrategyResultModel],
    *,
    rel_strength: dict[str, float | None],
    regime: MarketRegimeLabel,
    rel_volume: float | None,
    weights: ScoringWeights = DEFAULT_WEIGHTS,
) -> ScoreBreakdown:
    weights.validate()
    buy_like = [r for r in results if r.direction == SignalDirection.BUY or r.to_legacy_dict().get("signal") == "BUY"]
    explanations: list[str] = []

    mom_scores = [r.score for r in results if r.strategy_id in ("momentum", "high_momentum")]
    momentum_quality = _clamp((max(mom_scores) if mom_scores else 0) / 100)

    trend_scores = [r.score for r in results if r.strategy_id in ("trend_following", "pullback")]
    trend_quality = _clamp((max(trend_scores) if trend_scores else 0) / 100)

    setup_scores = [r.score for r in results if r.strategy_id in ("breakout", "mean_reversion", "pullback")]
    setup_quality = _clamp((max(setup_scores) if setup_scores else 0) / 100)

    rel3 = rel_strength.get("rel_63d")
    if rel3 is None:
        rel3 = rel_strength.get("rel_21d")
    relative_strength = _clamp(((rel3 or 0) + 0.15) / 0.35) if rel3 is not None else 0.0
    if rel3 is None:
        explanations.append("Relative strength unavailable — zero weight applied")

    volume_confirmation = _clamp(((rel_volume or 1.0) - 0.8) / 1.2)

    regime_alignment = 0.5
    if regime in (MarketRegimeLabel.BULLISH, MarketRegimeLabel.SIDEWAYS):
        regime_alignment = 0.75 if regime == MarketRegimeLabel.BULLISH else 0.55
    elif regime in (MarketRegimeLabel.BEARISH, MarketRegimeLabel.HIGH_VOLATILITY):
        regime_alignment = 0.25
    elif regime == MarketRegimeLabel.MIXED:
        regime_alignment = 0.5

    contrib = ScoreBreakdown(
        momentum_quality=round(momentum_quality * weights.momentum_quality, 2),
        trend_quality=round(trend_quality * weights.trend_quality, 2),
        setup_quality=round(setup_quality * weights.setup_quality, 2),
        relative_strength=round(relative_strength * weights.relative_strength, 2),
        volume_confirmation=round(volume_confirmation * weights.volume_confirmation, 2),
        regime_alignment=round(regime_alignment * weights.regime_alignment, 2),
        explanations=explanations,
    )
    total = int(
        round(
            contrib.momentum_quality
            + contrib.trend_quality
            + contrib.setup_quality
            + contrib.relative_strength
            + contrib.volume_confirmation
            + contrib.regime_alignment
        )
    )
    contrib.total = max(0, min(100, total))
    if not buy_like:
        contrib.explanations.append("No BUY-classified strategy outputs — capped below watchlist")
        contrib.total = min(contrib.total, 59)
    return contrib