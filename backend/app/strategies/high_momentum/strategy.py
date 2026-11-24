from __future__ import annotations

from app.strategies.base import BaseStrategy
from app.strategies.schemas import StrategyResultModel
from app.strategies.context import StrategyContext
from app.strategies.schemas import SignalDirection
from app.strategies.utils import make_result


class HighMomentumStrategy(BaseStrategy):
    strategy_id = "high_momentum"
    legacy_name = "52-Week High Momentum"
    description = "Leaders near 52-week highs with positive 3M returns."

    @property
    def name(self) -> str:
        return self.legacy_name

    def evaluate(self, context: StrategyContext) -> StrategyResultModel:
        cfg = context.config
        price = context.price
        ema50 = float(context.feature("ema50", price))
        ret3 = float(context.feature("return_3m", 0) or 0)
        high52 = float(context.feature("high_52w", price))
        proximity = price / high52 if high52 else 0
        triggered = proximity >= cfg.high_momentum_52w_proximity and ret3 > 0 and price > ema50
        score = 35 + min(30, proximity * 30) + (20 if ret3 > 0 else 0) + (15 if price > ema50 else 0)
        met, rej = [], []
        if proximity >= cfg.high_momentum_52w_proximity:
            met.append("Near 52-week high")
        else:
            rej.append("52-week proximity below threshold")
        direction = SignalDirection.BUY if triggered and score >= cfg.buy_score_threshold else (
            SignalDirection.HOLD if score >= cfg.watchlist_score_threshold else SignalDirection.NO_SIGNAL
        )
        rationale = f"Price is {proximity:.1%} of 52-week high; 3M return {ret3:.1%}."
        return make_result(
            self.strategy_id,
            self.legacy_name,
            context,
            direction=direction,
            score=score,
            triggered=triggered,
            rationale=rationale,
            conditions_met=met,
            rejection_reasons=rej,
            features_used={"high_52w": high52, "proximity": proximity, "return_3m": ret3},
        )


strategy = HighMomentumStrategy()