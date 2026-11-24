from dataclasses import dataclass


@dataclass(frozen=True)
class RegimeConfig:
    benchmark_symbol: str = "NIFTY500_PROXY"
    min_bars: int = 120
    sma_fast: int = 50
    sma_slow: int = 200
    adx_trend_threshold: float = 20.0
    high_vol_percentile: float = 0.80
    breadth_bull_threshold: float = 0.55
    breadth_bear_threshold: float = 0.45


DEFAULT_REGIME_CONFIG = RegimeConfig()