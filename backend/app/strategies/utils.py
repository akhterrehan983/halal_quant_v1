"""Shared helpers for modular strategies."""

import pandas as pd

from app.strategies.context import StrategyContext
from app.strategies.schemas import SignalDirection, StrategyResultModel


def levels_from_row(row: pd.Series, cfg) -> tuple[float, float, float, float]:
    price = float(row.close)
    atr = float(row.atr14) if pd.notna(row.atr14) else price * 0.03
    stop = price - cfg.atr_stop_mult * atr
    target = price + cfg.atr_target_mult * atr
    rr = (target - price) / max(price - stop, 0.0001)
    return price, stop, target, rr


def make_result(
    strategy_id: str,
    legacy_name: str,
    context: StrategyContext,
    *,
    direction: SignalDirection,
    score: int,
    triggered: bool,
    rationale: str,
    conditions_met: list[str],
    rejection_reasons: list[str],
    features_used: dict,
) -> StrategyResultModel:
    price, stop, target, rr = levels_from_row(context.row, context.config)
    return StrategyResultModel(
        strategy_id=strategy_id,
        strategy_name=legacy_name,
        symbol=context.symbol,
        evaluation_date=context.evaluation_date,
        horizon=context.horizon,
        direction=direction,
        score=int(max(0, min(100, score))),
        strength="strong" if score >= 75 else "moderate" if score >= 50 else "weak",
        entry_price=round(price, 2),
        stop_loss=round(stop, 2),
        target=round(target, 2),
        risk_reward=round(rr, 2),
        rationale=rationale,
        rejection_reasons=rejection_reasons,
        conditions_met=conditions_met,
        features_used=features_used,
        triggered=triggered,
    )