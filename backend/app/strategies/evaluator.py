"""Build context and run registered strategies."""

from __future__ import annotations

from datetime import date

import pandas as pd

from app.features.relative_strength import aligned_relative_returns
from app.strategies.config import get_horizon_config
from app.strategies.context import StrategyContext
from app.strategies.indicators import add_indicators
from app.strategies.registry import enabled_strategies, get_strategy
from app.strategies.schemas import StrategyResultModel


def build_context(
    symbol: str,
    df: pd.DataFrame,
    horizon: str = "swing",
    *,
    eval_index: int = -1,
    regime: str | None = None,
) -> StrategyContext:
    cfg = get_horizon_config(horizon)
    x = add_indicators(df)
    if len(x) < cfg.min_history_bars:
        raise ValueError("At least 60 daily candles are required")
    idx = len(x) + eval_index if eval_index < 0 else eval_index
    row = x.iloc[idx]
    prev = x.iloc[idx - 1] if idx > 0 else None
    ts = row.date
    eval_date = ts.date() if hasattr(ts, "date") else ts
    bench_feats = aligned_relative_returns(df.iloc[: idx + 1], as_of_index=-1)
    return StrategyContext(
        symbol=symbol.upper(),
        ohlcv=df,
        features=x,
        row=row,
        prev_row=prev,
        evaluation_date=eval_date,
        horizon=horizon,
        regime=regime,
        benchmark_features=bench_feats,
        config=cfg,
    )


def evaluate_strategy(
    strategy_id: str,
    symbol: str,
    df: pd.DataFrame,
    horizon: str = "swing",
    *,
    eval_index: int = -1,
) -> StrategyResultModel:
    strategy = get_strategy(strategy_id)
    if not strategy:
        raise KeyError(f"Unknown strategy: {strategy_id}")
    ctx = build_context(symbol, df, horizon, eval_index=eval_index)
    return strategy.evaluate(ctx)


def evaluate_all_strategies(
    symbol: str,
    df: pd.DataFrame,
    horizon: str = "swing",
    *,
    eval_index: int = -1,
) -> list[StrategyResultModel]:
    ctx = build_context(symbol, df, horizon, eval_index=eval_index)
    results: list[StrategyResultModel] = []
    for strategy in enabled_strategies():
        results.append(strategy.evaluate(ctx))
    return results


def feature_snapshot(ctx: StrategyContext) -> dict:
    r = ctx.row
    price = float(r.close)
    ema50 = float(r.ema50)
    sma200 = float(r.sma200) if pd.notna(r.sma200) else ema50
    high52 = float(r.high_52w) if pd.notna(r.high_52w) else price
    proximity = price / high52 if high52 else 0
    ret1 = float(r.return_1m) if pd.notna(r.return_1m) else 0.0
    ret3 = float(r.return_3m) if pd.notna(r.return_3m) else 0.0
    ret6 = float(r.return_6m) if pd.notna(r.return_6m) else 0.0
    regime = ctx.regime or (
        "Bullish"
        if price > sma200 and ema50 > sma200
        else ("Bearish" if price < sma200 and ema50 < sma200 else "Mixed / Sideways")
    )
    return {
        "close": round(price, 2),
        "ema20": round(float(r.ema20), 2),
        "ema50": round(ema50, 2),
        "sma200": round(sma200, 2),
        "rsi14": round(float(r.rsi14), 1),
        "adx14": round(float(r.adx14), 1),
        "atr14": round(float(r.atr14), 2),
        "relative_volume": round(float(r.relative_volume), 2) if pd.notna(r.relative_volume) else 1.0,
        "return_1m": round(ret1 * 100, 2),
        "return_3m": round(ret3 * 100, 2),
        "return_6m": round(ret6 * 100, 2),
        "high_52w": round(high52, 2),
        "high_proximity": round(proximity * 100, 1),
        "regime": regime,
    }