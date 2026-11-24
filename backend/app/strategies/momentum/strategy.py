from __future__ import annotations

from app.strategies.base import BaseStrategy
from app.strategies.schemas import StrategyResultModel
from app.strategies.context import StrategyContext
from app.strategies.schemas import SignalDirection
from app.strategies.utils import make_result


class MomentumStrategy(BaseStrategy):
    strategy_id = "momentum"
    legacy_name = "Relative Momentum"
    description = "Positive medium-term returns with price above EMA50."

    @property
    def name(self) -> str:
        return self.legacy_name

    def evaluate(self, context: StrategyContext) -> StrategyResultModel:
        cfg = context.config
        price = context.price
        ret3 = float(context.feature("return_3m", 0) or 0)
        ret6 = float(context.feature("return_6m", 0) or 0)
        ema50 = float(context.feature("ema50", price))
        triggered = ret3 > cfg.momentum_min_ret_3m and ret6 > cfg.momentum_min_ret_6m and price > ema50
        score = 25 + max(-20, min(35, ret3 * 100)) + max(-10, min(20, ret6 * 50))
        met, rej = [], []
        if ret3 > cfg.momentum_min_ret_3m:
            met.append("3M return positive")
        else:
            rej.append("3M return not positive")
        if ret6 > cfg.momentum_min_ret_6m:
            met.append("6M return positive")
        else:
            rej.append("6M return not positive")
        if price > ema50:
            met.append("Price above EMA50")
        else:
            rej.append("Price below EMA50")
        direction = SignalDirection.BUY if triggered and score >= cfg.buy_score_threshold else (
            SignalDirection.HOLD if score >= cfg.watchlist_score_threshold else SignalDirection.NO_SIGNAL
        )
        rationale = (
            f"3M return {ret3:.1%}; 6M return {ret6:.1%}; price "
            f"{'above' if price > ema50 else 'below'} EMA50."
        )
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
            features_used={"return_3m": ret3, "return_6m": ret6, "ema50": ema50, "close": price},
        )


strategy = MomentumStrategy()