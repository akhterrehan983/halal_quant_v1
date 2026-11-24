from __future__ import annotations

from app.strategies.base import BaseStrategy
from app.strategies.schemas import StrategyResultModel
from app.strategies.context import StrategyContext
from app.strategies.schemas import SignalDirection
from app.strategies.utils import make_result


class TrendFollowingStrategy(BaseStrategy):
    strategy_id = "trend_following"
    legacy_name = "Trend Following"
    description = "Directional trend participation using EMA stack and ADX."

    @property
    def name(self) -> str:
        return self.legacy_name

    def evaluate(self, context: StrategyContext) -> StrategyResultModel:
        cfg = context.config
        price = context.price
        ema20 = float(context.feature("ema20", price))
        ema50 = float(context.feature("ema50", price))
        sma200 = float(context.feature("sma200", ema50))
        adx = float(context.feature("adx14", 0))
        ema_aligned = ema20 > ema50
        above200 = price > sma200
        triggered = above200 and ema_aligned and adx >= cfg.trend_min_adx
        score = (
            35
            + (20 if above200 else 0)
            + (20 if ema_aligned else 0)
            + min(20, max(0, adx - 15))
        )
        met, rej = [], []
        if above200:
            met.append("Price above SMA200")
        if ema_aligned:
            met.append("EMA20 above EMA50")
        if adx >= cfg.trend_min_adx:
            met.append("ADX confirms trend")
        else:
            rej.append("ADX below minimum")
        direction = SignalDirection.BUY if triggered and score >= cfg.buy_score_threshold else (
            SignalDirection.HOLD if score >= cfg.watchlist_score_threshold else SignalDirection.NO_SIGNAL
        )
        rationale = f"Price vs SMA200; EMA20/EMA50 alignment; ADX {adx:.1f}."
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
            features_used={"adx14": adx, "ema20": ema20, "ema50": ema50, "sma200": sma200},
        )


strategy = TrendFollowingStrategy()