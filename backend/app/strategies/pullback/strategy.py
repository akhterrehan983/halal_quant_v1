from __future__ import annotations

from app.strategies.base import BaseStrategy
from app.strategies.schemas import StrategyResultModel
from app.strategies.context import StrategyContext
from app.strategies.schemas import SignalDirection
from app.strategies.utils import make_result


class PullbackStrategy(BaseStrategy):
    strategy_id = "pullback"
    legacy_name = "Pullback"
    description = "Pullback to EMA20 within an established uptrend."

    @property
    def name(self) -> str:
        return self.legacy_name

    def evaluate(self, context: StrategyContext) -> StrategyResultModel:
        cfg = context.config
        price = context.price
        ema20 = float(context.feature("ema20", price))
        ema50 = float(context.feature("ema50", price))
        sma200 = float(context.feature("sma200", ema50))
        rsi = float(context.feature("rsi14", 50))
        low = float(context.row.low)
        uptrend = price > sma200 and ema50 > sma200
        touched = low <= ema20 * cfg.pullback_ema_tolerance and price >= ema20
        rsi_ok = cfg.pullback_rsi_min <= rsi <= cfg.pullback_rsi_max
        triggered = uptrend and touched and rsi_ok
        score = (
            40
            + (20 if uptrend else 0)
            + (20 if touched else 0)
            + (15 if rsi_ok else 0)
        )
        met, rej = [], []
        if uptrend:
            met.append("Uptrend confirmed")
        else:
            rej.append("Uptrend not confirmed")
        if touched:
            met.append("Pullback toward EMA20")
        if rsi_ok:
            met.append("RSI in recovery band")
        direction = SignalDirection.BUY if triggered and score >= cfg.buy_score_threshold else (
            SignalDirection.HOLD if score >= cfg.watchlist_score_threshold else SignalDirection.NO_SIGNAL
        )
        rationale = (
            f"Uptrend {'confirmed' if uptrend else 'not confirmed'}; RSI {rsi:.1f}; EMA20 {ema20:.2f}."
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
            features_used={"rsi14": rsi, "ema20": ema20, "low": low, "close": price},
        )


strategy = PullbackStrategy()