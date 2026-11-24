from __future__ import annotations

from app.strategies.base import BaseStrategy
from app.strategies.schemas import StrategyResultModel
from app.strategies.context import StrategyContext
from app.strategies.schemas import SignalDirection
from app.strategies.utils import make_result


class BreakoutStrategy(BaseStrategy):
    strategy_id = "breakout"
    legacy_name = "Breakout"
    description = "Close above prior rolling high (excluding current candle) with volume."

    @property
    def name(self) -> str:
        return self.legacy_name

    @property
    def required_features(self) -> set[str]:
        return super().required_features | {"high_20", "high_55"}

    def evaluate(self, context: StrategyContext) -> StrategyResultModel:
        cfg = context.config
        price = context.price
        ema50 = float(context.feature("ema50", price))
        sma200 = float(context.feature("sma200", ema50))
        relvol = float(context.feature("relative_volume", 1.0) or 1.0)
        high_key = "high_20" if cfg.breakout_lookback <= 25 else "high_55"
        breakout_level = float(context.feature(high_key, price * 1.02))
        buffer = cfg.breakout_atr_buffer * float(context.feature("atr14", price * 0.03) or price * 0.03)
        uptrend = price > sma200 and ema50 > sma200
        triggered = (
            price > breakout_level + buffer
            and relvol >= cfg.breakout_min_rel_volume
            and price > ema50
        )
        score = (
            45
            + (15 if price > breakout_level else 0)
            + min(25, max(0, (relvol - 1) * 20))
            + (15 if uptrend else 0)
        )
        met, rej = [], []
        if price > breakout_level:
            met.append(f"Close above prior {cfg.breakout_lookback}-day high")
        else:
            rej.append("No breakout above resistance")
        if relvol >= cfg.breakout_min_rel_volume:
            met.append("Relative volume sufficient")
        else:
            rej.append("Relative volume too low")
        direction = SignalDirection.BUY if triggered and score >= cfg.buy_score_threshold else (
            SignalDirection.HOLD if score >= cfg.watchlist_score_threshold else SignalDirection.NO_SIGNAL
        )
        rationale = (
            f"Close vs prior {cfg.breakout_lookback}-day high; relative volume {relvol:.2f}x."
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
            features_used={
                "breakout_level": breakout_level,
                "relative_volume": relvol,
                high_key: breakout_level,
                "close": price,
            },
        )


strategy = BreakoutStrategy()