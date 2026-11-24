from __future__ import annotations

import random
from decimal import Decimal

from app.backtesting.schemas import CompletedTrade
from app.portfolio.money import D


def monte_carlo_trade_returns(trades: list[CompletedTrade], *, simulations: int = 500, seed: int = 42) -> dict:
    if not trades:
        return {"simulations": 0, "notice": "No trades to resample"}
    rng = random.Random(seed)
    returns = [float(t.net_pnl) for t in trades]
    finals = []
    for _ in range(simulations):
        seq = returns.copy()
        rng.shuffle(seq)
        finals.append(sum(seq))
    finals.sort()
    p5 = finals[int(0.05 * len(finals))]
    p50 = finals[len(finals) // 2]
    p95 = finals[int(0.95 * len(finals)) - 1]
    return {
        "simulations": simulations,
        "seed": seed,
        "final_pnl_p5": p5,
        "final_pnl_p50": p50,
        "final_pnl_p95": p95,
        "notice": "Trade-sequence resampling — not a forecast",
    }