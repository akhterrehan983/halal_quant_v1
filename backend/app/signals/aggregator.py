from __future__ import annotations

from app.signals.config import CORRELATED_STRATEGY_GROUPS
from app.signals.schemas import StrategyContribution
from app.strategies.schemas import SignalDirection, StrategyResultModel


def effective_consensus_weight(strategy_id: str, seen_groups: set[int]) -> float:
    for i, group in enumerate(CORRELATED_STRATEGY_GROUPS):
        if strategy_id in group:
            if i in seen_groups:
                return 0.35
            seen_groups.add(i)
            return 1.0
    return 1.0


def build_contributions(results: list[StrategyResultModel]) -> tuple[list[StrategyContribution], float, list[str], str]:
    contributions: list[StrategyContribution] = []
    seen: set[int] = set()
    effective_buys = 0.0
    buy_ids: list[str] = []
    sell_like: list[str] = []

    for r in results:
        legacy = r.to_legacy_dict()
        weight = effective_consensus_weight(r.strategy_id, seen)
        is_buy = r.direction == SignalDirection.BUY or legacy["signal"] == "BUY"
        if is_buy:
            effective_buys += weight
            buy_ids.append(r.strategy_id)
        if legacy["signal"] == "NO ACTION" and r.score >= 40:
            sell_like.append(r.strategy_id)
        contributions.append(
            StrategyContribution(
                strategy_id=r.strategy_id,
                strategy_name=r.strategy_name,
                direction=r.direction.value,
                score=r.score,
                legacy_signal=legacy["signal"],
                rationale=r.rationale,
                weight_in_consensus=weight if is_buy else 0.0,
            )
        )

    conflicting = [s for s in sell_like if s not in buy_ids]
    if effective_buys >= 2.5:
        level = "high"
    elif effective_buys >= 1.5:
        level = "moderate"
    elif effective_buys >= 0.9:
        level = "low"
    else:
        level = "none"
    return contributions, effective_buys, conflicting, level