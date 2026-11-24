"""Unified signal generation orchestration."""

from __future__ import annotations

from datetime import date

import pandas as pd

from app.features.relative_strength import aligned_relative_returns
from app.regime.classifier import classify_market
from app.signals.aggregator import build_contributions
from app.signals.config import DEFAULT_CATEGORIES, DEFAULT_LIFECYCLE
from app.signals.scoring import category_from_score, score_signal
from app.signals.schemas import LifecycleState, UnifiedSignal
from app.strategies.evaluator import build_context, evaluate_all_strategies, feature_snapshot
from app.strategies.schemas import StrategyResultModel


def _resolve_eval_index(df: pd.DataFrame, as_of_index: int) -> int:
    idx = len(df) + as_of_index if as_of_index < 0 else as_of_index
    return max(0, min(idx, len(df) - 1))


def evaluation_date(df: pd.DataFrame, as_of_index: int = -1) -> date:
    """Calendar date of the evaluation bar (point-in-time anchor for regime and breadth)."""
    if df.empty:
        return date.today()
    idx = _resolve_eval_index(df, as_of_index)
    ts = df.iloc[idx]["date"]
    return ts.date() if hasattr(ts, "date") else ts


def generate_unified_signal(
    symbol: str,
    df: pd.DataFrame,
    horizon: str = "swing",
    *,
    as_of_index: int = -1,
) -> UnifiedSignal:
    eval_date = evaluation_date(df, as_of_index)
    regime = classify_market(as_of_date=eval_date, as_of_index=as_of_index)
    rel = aligned_relative_returns(df, as_of_index=as_of_index, as_of_date=eval_date)
    results = evaluate_all_strategies(symbol, df, horizon, eval_index=as_of_index)
    ctx = build_context(symbol, df, horizon, eval_index=as_of_index, regime=regime.regime.value)
    features = feature_snapshot(ctx)

    contributions, eff_buys, conflicts, agreement = build_contributions(results)
    breakdown = score_signal(
        results,
        rel_strength=rel,
        regime=regime.regime,
        rel_volume=features.get("relative_volume"),
    )
    from app.regime.schemas import MarketRegimeLabel

    hard_reject = regime.regime in (MarketRegimeLabel.BEARISH, MarketRegimeLabel.HIGH_VOLATILITY) and breakdown.total >= 75
    category = category_from_score(breakdown.total, hard_reject=hard_reject)
    rejection = []
    if hard_reject:
        rejection.append("Hard context gate: bearish/high-vol regime caps actionable category")
    if eff_buys < 0.9:
        rejection.append("Insufficient de-duplicated strategy consensus")

    best = max(results, key=lambda r: r.score)
    entry = float(ctx.row.close)
    stop = best.stop_loss or entry * 0.95
    target = best.target or entry * 1.05
    buy_candidates = [r for r in results if r.to_legacy_dict()["signal"] == "BUY"]
    if buy_candidates:
        ref = max(buy_candidates, key=lambda r: r.score)
        entry = ref.entry_price
        stop = ref.stop_loss
        target = ref.target

    max_sessions = (
        DEFAULT_LIFECYCLE.swing_max_sessions
        if horizon == "swing"
        else DEFAULT_LIFECYCLE.positional_max_sessions
    )

    return UnifiedSignal(
        symbol=symbol.upper(),
        horizon=horizon,
        evaluation_date=ctx.evaluation_date,
        category=category,
        overall_score=breakdown.total,
        lifecycle_state=LifecycleState.CREATED,
        market_regime=regime.regime,
        regime_confidence=regime.confidence,
        entry_reference=entry,
        stop_reference=stop,
        target_reference=target,
        relative_strength=rel,
        contributions=contributions,
        conflicting_strategies=conflicts,
        consensus_effective_buys=round(eff_buys, 2),
        agreement_level=agreement,
        score_breakdown=breakdown,
        rejection_reasons=rejection,
        strategy_results=[r.to_api_dict() for r in results],
        expires_after_sessions=max_sessions,
    )


def generate_batch(
    symbol_df_pairs: list[tuple[str, pd.DataFrame]],
    horizon: str,
    *,
    as_of_index: int = -1,
) -> list[UnifiedSignal]:
    out: list[UnifiedSignal] = []
    for symbol, df in symbol_df_pairs:
        try:
            out.append(generate_unified_signal(symbol, df, horizon, as_of_index=as_of_index))
        except ValueError:
            continue
    return out