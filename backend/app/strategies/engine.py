"""Backward-compatible evaluation facade over modular strategies."""

import pandas as pd

from app.strategies.evaluator import build_context, evaluate_all_strategies, feature_snapshot
from app.strategies.registry import list_strategies

# Legacy list used by tests and API metadata
STRATEGIES = [s.legacy_name for s in list_strategies()]


def evaluate_all(df: pd.DataFrame, horizon: str = "swing") -> tuple[list[dict], dict]:
    symbol = "UNKNOWN"
    if "symbol" in df.columns and len(df):
        symbol = str(df["symbol"].iloc[-1])
    results = evaluate_all_strategies(symbol, df, horizon)
    ctx = build_context(symbol, df, horizon)
    legacy = [r.to_legacy_dict() for r in results]
    return legacy, feature_snapshot(ctx)