"""M11 — point-in-time regime, benchmark, breadth, and signal context."""

from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import patch

import pandas as pd

from app.data import sample_data
from app.data.sample_data import make_history
from app.regime.benchmark import benchmark_slice, ensure_benchmark_history
from app.regime.classifier import classify_market
from app.regime.market_breadth import compute_universe_breadth
from app.signals.generator import evaluation_date, generate_unified_signal


def _bench_series(periods: int = 260, *, end_offset_days: int = 0) -> pd.DataFrame:
    df = make_history("NIFTY500_PROXY", periods=periods)
    if end_offset_days:
        shift = pd.Timedelta(days=end_offset_days)
        df["date"] = pd.to_datetime(df["date"]) - shift
    return df


def test_benchmark_slice_respects_as_of_date():
    base = _bench_series(120)
    cut = pd.to_datetime(base["date"].iloc[80]).date()
    sliced, idx = benchmark_slice(-1, as_of_date=cut)
    assert not sliced.empty
    assert pd.to_datetime(sliced["date"]).dt.date.max() <= cut
    assert idx == len(sliced) - 1


def test_benchmark_empty_before_first_bar():
    base = _bench_series(80)
    first = pd.to_datetime(base["date"].iloc[0]).date()
    before = first - timedelta(days=30)
    with patch("app.regime.benchmark.ensure_benchmark_history", return_value=base.copy()):
        sliced, idx = benchmark_slice(-1, as_of_date=before)
    assert sliced.empty
    assert idx == -1


def test_regime_unchanged_when_future_benchmark_appended():
    base = _bench_series(200)
    eval_d = pd.to_datetime(base["date"].iloc[150]).date()
    extended = base.copy()
    tail = make_history("EXT", periods=40)
    tail["close"] = tail["close"] * 5.0
    tail["open"] = tail["high"] = tail["low"] = tail["close"]
    tail["date"] = pd.bdate_range(
        start=pd.to_datetime(base["date"].iloc[-1]) + pd.Timedelta(days=1),
        periods=40,
    )
    extended = pd.concat([base, tail], ignore_index=True)

    with patch("app.regime.benchmark.ensure_benchmark_history", return_value=base.copy()):
        before = classify_market(as_of_date=eval_d, as_of_index=-1)
    with patch("app.regime.benchmark.ensure_benchmark_history", return_value=extended):
        after = classify_market(as_of_date=eval_d, as_of_index=-1)

    assert before.data_quality == "ok"
    assert before.regime == after.regime
    assert before.factors["close"] == after.factors["close"]
    assert before.as_of_date == after.as_of_date


def test_breadth_unchanged_when_future_prices_appended():
    symbol = "PITTEST"
    hist = make_history(symbol, periods=120)
    eval_d = pd.to_datetime(hist["date"].iloc[90]).date()
    sample_data.HISTORIES[symbol] = hist.copy()
    try:
        b1 = compute_universe_breadth(as_of_date=eval_d)
        inflated = hist.copy()
        future = make_history(symbol + "F", periods=30)
        future["close"] *= 10
        future["date"] = pd.bdate_range(
            start=pd.to_datetime(hist["date"].iloc[-1]) + pd.Timedelta(days=1),
            periods=30,
        )
        sample_data.HISTORIES[symbol] = pd.concat([hist, future], ignore_index=True)
        b2 = compute_universe_breadth(as_of_date=eval_d)
        assert b1["pct_above_sma50"] == b2["pct_above_sma50"]
        assert b1["symbols_sampled"] == b2["symbols_sampled"]
    finally:
        sample_data.HISTORIES.pop(symbol, None)


def test_unified_signal_stable_when_future_benchmark_appended():
    stock = make_history("TCS", periods=150)
    sub = stock.iloc[:100].copy()
    eval_d = evaluation_date(sub, -1)

    base_bench = _bench_series(200)
    with patch("app.regime.benchmark.ensure_benchmark_history", return_value=base_bench.copy()):
        sig1 = generate_unified_signal("TCS", sub, "swing", as_of_index=-1)

    extended = base_bench.copy()
    extra = make_history("XB", periods=50)
    extra["close"] *= 3
    extra["date"] = pd.bdate_range(
        start=pd.to_datetime(base_bench["date"].iloc[-1]) + pd.Timedelta(days=1),
        periods=50,
    )
    extended = pd.concat([base_bench, extra], ignore_index=True)
    with patch("app.regime.benchmark.ensure_benchmark_history", return_value=extended):
        sig2 = generate_unified_signal("TCS", sub, "swing", as_of_index=-1)

    assert sig1.evaluation_date == eval_d
    assert sig1.market_regime == sig2.market_regime
    assert sig1.overall_score == sig2.overall_score
    assert sig1.regime_confidence == sig2.regime_confidence


def test_regime_history_breadth_not_using_latest():
    base = _bench_series(260)
    with patch("app.regime.benchmark.ensure_benchmark_history", return_value=base):
        older = classify_market(as_of_index=-30)
        latest = classify_market(as_of_index=-1)
    assert older.as_of_date < latest.as_of_date
    old_b = older.factors.get("breadth", {}).get("as_of_date")
    new_b = latest.factors.get("breadth", {}).get("as_of_date")
    assert old_b is not None and new_b is not None


def test_classify_insufficient_when_as_of_before_history():
    base = _bench_series(80)
    first = pd.to_datetime(base["date"].iloc[0]).date()
    with patch("app.regime.benchmark.ensure_benchmark_history", return_value=base):
        c = classify_market(as_of_date=first - timedelta(days=365))
    assert c.data_quality == "insufficient_history"


def test_live_classify_market_defaults_unchanged():
    """Latest bar path still works without explicit as_of_date."""
    c = classify_market()
    assert c.data_quality in ("ok", "insufficient_history")
    bench = ensure_benchmark_history()
    last = pd.to_datetime(bench.sort_values("date")["date"].iloc[-1]).date()
    if c.data_quality == "ok":
        assert c.as_of_date <= last


def test_backtest_signal_regime_on_or_before_session():
    from app.backtesting.data import index_as_of
    from app.market_data.repository import get_history_dataframe

    df = get_history_dataframe("TCS", limit=120)
    session = pd.to_datetime(df.iloc[70]["date"]).date()
    idx = index_as_of(df, session)
    sub = df.iloc[: idx + 1]
    sig = generate_unified_signal("TCS", sub, "swing", as_of_index=-1)
    regime = classify_market(as_of_date=evaluation_date(sub, -1), as_of_index=-1)
    assert sig.evaluation_date <= session
    assert regime.as_of_date <= session