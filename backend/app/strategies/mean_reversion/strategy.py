from __future__ import annotations

from app.strategies.base import BaseStrategy
from app.strategies.schemas import StrategyResultModel
from app.strategies.context import StrategyContext
from app.strategies.schemas import SignalDirection
from app.strategies.utils import make_result


class MeanReversionStrategy(BaseStrategy):
    strategy_id = "mean_reversion"
    legacy_name = "Mean Reversion"
    description = "Oversold deviation below lower Bollinger with confirmation context."

    @property
    def name(self) -> str:
        return self.legacy_name

    def evaluate(self, context: StrategyContext) -> StrategyResultModel:
        cfg = context.config
        price = context.price
        ema50 = float(context.feature("ema50", price))
        sma200 = float(context.feature("sma200", ema50))
        rsi = float(context.feature("rsi14", 50))
        bb_lower = float(context.feature("bb_lower", price * 0.95))
        uptrend = price > sma200 and ema50 > sma200
        stretched = price < bb_lower and rsi < cfg.mean_reversion_rsi_max
        context_ok = uptrend or (context.horizon == "swing")
        triggered = stretched and context_ok
        score = (
            35
            + (25 if price < bb_lower else 0)
            + (20 if rsi < 30 else 10 if rsi < cfg.mean_reversion_rsi_max else 0)
            + (15 if uptrend else 0)
        )
        met, rej = [], []
        if stretched:
            met.append("Price below lower Bollinger / RSI oversold")
        else:
            rej.append("No meaningful oversold stretch")
        if not context_ok:
            rej.append("Trend context not acceptable for horizon")
        direction = SignalDirection.BUY if triggered and score >= cfg.buy_score_threshold else (
            SignalDirection.HOLD if score >= cfg.watchlist_score_threshold else SignalDirection.NO_SIGNAL
        )
        rationale = (
            f"RSI {rsi:.1f}; lower Bollinger band {bb_lower:.2f}; "
            f"long-term trend {'positive' if uptrend else 'not positive'}."
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
            features_used={"rsi14": rsi, "bb_lower": bb_lower, "close": price},
        )


strategy = MeanReversionStrategy()