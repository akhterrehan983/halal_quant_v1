from __future__ import annotations

from datetime import date

import pandas as pd

from app.regime.benchmark import benchmark_slice
from app.regime.config import DEFAULT_REGIME_CONFIG, RegimeConfig
from app.regime.indicators import benchmark_features
from app.regime.market_breadth import compute_universe_breadth
from app.regime.schemas import MarketRegimeLabel, RegimeClassification


def classify_market(
    *,
    as_of_index: int = -1,
    as_of_date: date | None = None,
    config: RegimeConfig = DEFAULT_REGIME_CONFIG,
) -> RegimeClassification:
    df, idx = benchmark_slice(as_of_index, as_of_date=as_of_date)
    if len(df) < config.min_bars or idx < 0:
        fallback_as_of = as_of_date or date.today()
        return RegimeClassification(
            regime=MarketRegimeLabel.MIXED,
            confidence=0.0,
            as_of_date=fallback_as_of,
            benchmark_symbol=config.benchmark_symbol,
            factors={"bars": len(df)},
            observations=["Insufficient benchmark history"],
            data_quality="insufficient_history",
            disclaimer="Need more benchmark bars for stable regime classification.",
        )

    x = benchmark_features(df)
    row = x.iloc[idx]
    ts = row.date
    as_of = ts.date() if hasattr(ts, "date") else ts
    price = float(row.close)
    sma50 = float(row.sma50) if pd.notna(row.get("sma50")) else float(row.ema50)
    sma200 = float(row.sma200) if pd.notna(row.sma200) else sma50
    adx = float(row.adx14) if pd.notna(row.adx14) else 15.0
    hist_vol = float(row.hist_vol_20) if pd.notna(row.get("hist_vol_20")) else None
    vol_series = x["hist_vol_20"].dropna()
    high_vol = False
    if hist_vol is not None and len(vol_series) >= 30:
        threshold = float(vol_series.quantile(config.high_vol_percentile))
        high_vol = bool(hist_vol >= threshold)

    slope50 = float(row.ema50_slope) if pd.notna(row.get("ema50_slope")) else 0.0
    breadth = compute_universe_breadth(as_of_date=as_of)
    breadth_pct = breadth.get("pct_above_sma50")

    observations: list[str] = []
    score_bull = score_bear = score_side = 0

    if price > sma50:
        score_bull += 1
        observations.append("Benchmark above SMA50")
    elif price < sma50:
        score_bear += 1
    else:
        score_side += 1

    if price > sma200:
        score_bull += 1
        observations.append("Benchmark above SMA200")
    elif price < sma200:
        score_bear += 1

    if slope50 > 0:
        score_bull += 1
    elif slope50 < 0:
        score_bear += 1

    if adx >= config.adx_trend_threshold:
        observations.append(f"ADX {adx:.1f} indicates trending conditions")
        if price > sma50:
            score_bull += 1
        elif price < sma50:
            score_bear += 1
    else:
        score_side += 1
        observations.append(f"ADX {adx:.1f} below trend threshold — range conditions")

    if high_vol:
        regime = MarketRegimeLabel.HIGH_VOLATILITY
        confidence = 0.7
    elif score_bull >= score_bear + 2:
        regime = MarketRegimeLabel.BULLISH
        confidence = min(0.95, 0.5 + score_bull * 0.1)
    elif score_bear >= score_bull + 2:
        regime = MarketRegimeLabel.BEARISH
        confidence = min(0.95, 0.5 + score_bear * 0.1)
    elif score_side >= score_bull and score_side >= score_bear:
        regime = MarketRegimeLabel.SIDEWAYS
        confidence = 0.55
    else:
        regime = MarketRegimeLabel.MIXED
        confidence = 0.5

    if breadth_pct is not None:
        if breadth_pct >= config.breadth_bull_threshold:
            observations.append(f"Breadth {breadth_pct:.0%} above SMA50 (universe proxy)")
        elif breadth_pct <= config.breadth_bear_threshold:
            observations.append(f"Breadth {breadth_pct:.0%} below SMA50 (universe proxy)")

    factors = {
        "close": round(price, 2),
        "sma50": round(sma50, 2),
        "sma200": round(sma200, 2),
        "adx14": round(adx, 1),
        "sma50_slope": round(slope50, 4),
        "hist_vol_20": round(hist_vol, 4) if hist_vol is not None else None,
        "high_volatility_flag": high_vol,
        "breadth": breadth,
        "india_vix": None,
    }

    return RegimeClassification(
        regime=regime,
        confidence=round(confidence, 2),
        as_of_date=as_of,
        benchmark_symbol=config.benchmark_symbol,
        factors=factors,
        observations=observations,
        disclaimer="Proxy benchmark and approximate breadth; not licensed NSE index data.",
    )