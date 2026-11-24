"""Horizon-aware strategy parameters (defaults — not optimized)."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class HorizonConfig:
    horizon: str
    min_history_bars: int = 60
    momentum_min_ret_3m: float = 0.0
    momentum_min_ret_6m: float = 0.0
    breakout_lookback: int = 20
    breakout_min_rel_volume: float = 1.2
    breakout_atr_buffer: float = 0.0
    pullback_rsi_min: float = 40.0
    pullback_rsi_max: float = 68.0
    pullback_ema_tolerance: float = 1.015
    mean_reversion_rsi_max: float = 35.0
    mean_reversion_allow_non_uptrend_swing: bool = True
    trend_min_adx: float = 18.0
    high_momentum_52w_proximity: float = 0.85
    buy_score_threshold: int = 70
    watchlist_score_threshold: int = 50
    atr_stop_mult: float = 2.0
    atr_target_mult: float = 3.0


def get_horizon_config(horizon: str) -> HorizonConfig:
    if horizon == "positional":
        return HorizonConfig(
            horizon="positional",
            breakout_lookback=55,
            high_momentum_52w_proximity=0.90,
            mean_reversion_allow_non_uptrend_swing=False,
        )
    return HorizonConfig(horizon="swing", breakout_lookback=20, high_momentum_52w_proximity=0.85)


STRATEGY_DESCRIPTIONS: dict[str, str] = {
    "momentum": "Cross-sectional and time-series momentum with trend confirmation.",
    "breakout": "Close above prior rolling high with volume confirmation (excludes current bar from resistance).",
    "pullback": "Uptrend pullback toward EMA20 with RSI recovery band.",
    "mean_reversion": "Oversold stretch below lower Bollinger with trend context filters.",
    "trend_following": "EMA alignment, price above SMA200, and ADX trend strength.",
    "high_momentum": "52-week high proximity with positive medium-term returns.",
}