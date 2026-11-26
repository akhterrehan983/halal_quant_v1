"""M14 Phase 1 regression tests.

Written BEFORE the Phase 1 implementation (see docs/m14_backtesting_audit.md).

Expectation on the PRE-Phase-1 code:
  * every test below FAILS, except those named ``test_guard_*`` which must PASS before and after
    (they protect Shariah / ownership / M12 isolation behaviour that Phase 1 must not change);
  * after Phase 1, all tests pass.

Design: the unified signal generator is replaced by a stub (always BUY, per-symbol score) so the
tests exercise the *simulator* (data loading, fills, sizing, exits, marks, coverage, provenance)
deterministically and quickly. Prices are fixed-date synthetic bars; nothing here is performance evidence.

Finding map: B-01 as-of data, B-02 stop/target, B-03 sizing/fill validation, B-08 stale marks,
B-09/B-12/B-14 universe scan + excluded symbols, B-28 provenance, B-30 coverage.
"""

from __future__ import annotations

from datetime import date, timedelta
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from app.backtesting.schemas import BacktestConfig, CostScenario, ShariahBacktestMode
from app.backtesting.simulator import run_backtest
from app.data import sample_data
from app.signals.schemas import SignalCategory

BASE_DATE = "2023-01-02"
N = 120  # default bar count for short scenarios


# --------------------------------------------------------------------------- helpers


def bar_date(i: int, n: int, start: str = BASE_DATE) -> date:
    return pd.bdate_range(start=start, periods=n)[i].date()


def make_bars(n: int, *, price: float = 100.0, overrides: dict | None = None, skip=()) -> pd.DataFrame:
    dates = pd.bdate_range(start=BASE_DATE, periods=n)
    df = pd.DataFrame(
        {
            "date": dates,
            "open": price,
            "high": price + 1.0,
            "low": price - 1.0,
            "close": price,
            "volume": 1_000_000.0,
        }
    )
    for i, cols in (overrides or {}).items():
        for col, val in cols.items():
            df.loc[i, col] = val
    if len(list(skip)):
        df = df.drop(index=list(skip)).reset_index(drop=True)
    return df


def make_ramp(n: int) -> pd.DataFrame:
    """Rising series so an entry price identifies the exact bar that was used."""
    df = make_bars(n)
    px = 100.0 + 0.1 * np.arange(n)
    df["open"] = px
    df["close"] = px
    df["high"] = px + 0.5
    df["low"] = px - 0.5
    return df


@pytest.fixture
def install_market(monkeypatch):
    def _install(frames: dict[str, pd.DataFrame]) -> None:
        monkeypatch.setattr(sample_data, "HISTORIES", {k: v.copy() for k, v in frames.items()})
        monkeypatch.setattr(sample_data, "SYMBOLS", list(frames))

    return _install


def stub_signals(monkeypatch, *, scores=None, stop=95.0, target=120.0, seen=None) -> None:
    scores = scores or {}

    def fake(symbol, df, horizon="swing", *, as_of_index=-1):
        if seen is not None:
            seen.setdefault(symbol, []).append(pd.Timestamp(df["date"].iloc[-1]).date())
        return SimpleNamespace(
            symbol=symbol,
            category=SignalCategory.BUY,
            overall_score=scores.get(symbol, 80),
            stop_reference=stop,
            target_reference=target,
        )

    monkeypatch.setattr("app.backtesting.simulator.generate_unified_signal", fake)


def make_cfg(start: date, end: date, **kw) -> BacktestConfig:
    base = dict(
        name="m14_p1",
        start_date=start,
        end_date=end,
        shariah_mode=ShariahBacktestMode.RESEARCH_ONLY,
        cost_scenario=CostScenario.ZERO,
        slippage_bps=0,
        max_positions=1,
        hold_days=400,  # effectively "no time exit" inside these short windows
    )
    base.update(kw)
    return BacktestConfig(**base)


def run_single(install_market, monkeypatch, overrides, *, stop=95.0, target=120.0, **cfg_kw):
    """One symbol, signal at bar 62 -> fill bar 63 open -> ownership authorised from bar 66."""
    install_market({"AAA": make_bars(N, overrides=overrides)})
    stub_signals(monkeypatch, stop=stop, target=target)
    return run_backtest(make_cfg(bar_date(62, N), bar_date(N - 1, N), **cfg_kw))


def first_trade(run):
    assert run.trades, "expected a closed trade but the position was never closed"
    return run.trades[0]


# --------------------------------------------------------------------------- B-01 as-of data


def test_history_window_helpers(install_market):
    """New as-of loaders exist and honour the end bound (B-01)."""
    from app.market_data.repository import get_history_window, get_next_bar

    n = 300
    install_market({"AAA": make_bars(n)})
    end = bar_date(150, n)
    window = get_history_window("AAA", end=end, lookback_bars=100)
    assert len(window) == 100
    assert pd.Timestamp(window["date"].iloc[-1]).date() == end
    nxt = get_next_bar("AAA", end)
    assert pd.Timestamp(nxt["date"]).date() == bar_date(151, n)
    assert get_next_bar("AAA", bar_date(n - 1, n)) is None


def test_breadth_as_of_uses_history_before_the_520_bar_window(install_market):
    """Breadth for an old session must not be empty just because it predates the latest 520 bars (B-01)."""
    from app.regime.market_breadth import compute_universe_breadth

    n = 800
    install_market({"AAA": make_ramp(n)})
    out = compute_universe_breadth(as_of_date=bar_date(150, n))
    assert out["symbols_sampled"] == 1


def test_early_sessions_trade_when_history_exceeds_520_bars(install_market, monkeypatch):
    """Sessions older than the latest-520-bar window must still be simulated (B-01)."""
    n = 800
    frame = make_ramp(n)
    install_market({"AAA": frame})
    seen: dict[str, list[date]] = {}
    stub_signals(monkeypatch, stop=50.0, target=10_000.0, seen=seen)
    start, end = bar_date(100, n), bar_date(160, n)
    run = run_backtest(make_cfg(start, end, hold_days=5))

    assert run.status.value == "COMPLETED"
    assert run.trades, "no trades: sessions before the latest-520-bar window were silently skipped"
    assert seen.get("AAA"), "signal generator never saw an as-of slice"
    assert all(start <= d <= end for d in seen["AAA"]), "signal saw bars outside the requested range"
    t = run.trades[0]
    assert start < t.entry_date <= end
    row = frame[pd.to_datetime(frame["date"]).dt.date == t.entry_date].iloc[0]
    assert round(float(t.entry_price), 2) == round(float(row["open"]), 2)  # next-session open, correct bar


# --------------------------------------------------------------------------- B-02 stop / target


def test_stop_exit_at_stop_level(install_market, monkeypatch):
    run = run_single(install_market, monkeypatch, {68: {"low": 90.0}})
    t = first_trade(run)
    assert t.exit_reason == "stop"
    assert t.exit_date == bar_date(68, N)
    assert float(t.exit_price) == pytest.approx(95.0)
    point = next(p for p in run.equity_curve if p.date == bar_date(68, N))
    assert point.invested == 0  # stop exit is reflected in that day's equity point


def test_gap_down_through_stop_exits_at_open(install_market, monkeypatch):
    gap = {"open": 90.0, "high": 91.0, "low": 88.0, "close": 90.0}
    run = run_single(install_market, monkeypatch, {68: gap})
    t = first_trade(run)
    assert t.exit_reason == "stop"
    assert float(t.exit_price) == pytest.approx(90.0)  # worse than the stop level; no fantasy fill at 95


def test_target_exit_at_target_level(install_market, monkeypatch):
    run = run_single(install_market, monkeypatch, {68: {"high": 125.0}})
    t = first_trade(run)
    assert t.exit_reason == "target"
    assert t.exit_date == bar_date(68, N)
    assert float(t.exit_price) == pytest.approx(120.0)


def test_gap_up_through_target_exits_at_open(install_market, monkeypatch):
    gap = {"open": 125.0, "high": 126.0, "low": 124.0, "close": 125.0}
    run = run_single(install_market, monkeypatch, {68: gap})
    t = first_trade(run)
    assert t.exit_reason == "target"
    assert float(t.exit_price) == pytest.approx(125.0)


def test_stop_first_when_stop_and_target_both_hit_on_one_bar(install_market, monkeypatch):
    run = run_single(install_market, monkeypatch, {68: {"low": 90.0, "high": 125.0}})
    t = first_trade(run)
    assert t.exit_reason == "stop"
    assert float(t.exit_price) == pytest.approx(95.0)


def test_stop_breach_before_sell_authorisation_is_delayed_not_ignored(install_market, monkeypatch):
    """Ownership safeguard: no sale before authorisation; the breach executes on the first allowed session."""
    run = run_single(install_market, monkeypatch, {64: {"low": 90.0}})  # authorised from bar 66
    t = first_trade(run)
    assert t.exit_reason == "stop_ownership_delayed"
    assert t.ownership_delayed_exit is True
    assert t.exit_date == bar_date(66, N)
    assert float(t.exit_price) == pytest.approx(100.0)  # first authorised session's open
    assert run.metrics.ownership_blocked_exits >= 1


def test_ownership_delayed_stop_reports_breach_stop_fill_and_loss_beyond_stop(install_market, monkeypatch):
    """Stop breached on bar 64 (sale unauthorised until bar 66); bar 66 opens below the stop."""
    open_below = {"open": 92.0, "high": 93.0, "low": 91.0, "close": 92.0}
    run = run_single(install_market, monkeypatch, {64: {"low": 90.0}, 66: open_below})
    t = first_trade(run)

    assert t.exit_reason == "stop_ownership_delayed"
    assert t.stop_breach_date == bar_date(64, N)
    assert float(t.stop_price) == pytest.approx(95.0)
    assert t.delayed_exit_date == bar_date(66, N) == t.exit_date
    assert float(t.exit_price) == pytest.approx(92.0)  # actual fill at the first authorised open
    assert float(t.loss_beyond_stop) == pytest.approx((95.0 - 92.0) * t.quantity)

    rep = run.validation["ownership_delayed_stops"]
    assert rep["count"] == 1
    ev = rep["events"][0]
    assert ev["symbol"] == "AAA"
    assert ev["stop_breach_date"] == bar_date(64, N).isoformat()
    assert float(ev["stop_price"]) == pytest.approx(95.0)
    assert ev["delayed_exit_date"] == bar_date(66, N).isoformat()
    assert float(ev["actual_fill"]) == pytest.approx(92.0)
    assert float(ev["loss_beyond_stop"]) == pytest.approx(float(t.loss_beyond_stop))
    assert float(rep["total_loss_beyond_stop"]) == pytest.approx(float(t.loss_beyond_stop))
    assert any("Ownership-delayed stop exits" in w for w in run.warnings)


def test_ownership_delayed_stop_loss_beyond_stop_is_zero_when_price_recovers(install_market, monkeypatch):
    run = run_single(install_market, monkeypatch, {64: {"low": 90.0}})  # bar 66 opens at 100, above the stop
    t = first_trade(run)
    assert t.exit_reason == "stop_ownership_delayed"
    assert t.stop_breach_date == bar_date(64, N)
    assert float(t.exit_price) == pytest.approx(100.0)
    assert float(t.loss_beyond_stop) == 0.0  # never negative: a recovery is not reported as a gain
    assert run.validation["ownership_delayed_stops"]["count"] == 1


def test_ordinary_stop_exit_reports_stop_fields_but_is_not_flagged_as_delayed(install_market, monkeypatch):
    gap = {"open": 90.0, "high": 91.0, "low": 88.0, "close": 90.0}
    run = run_single(install_market, monkeypatch, {68: gap})
    t = first_trade(run)
    assert t.exit_reason == "stop"
    assert t.stop_breach_date == t.exit_date == bar_date(68, N)
    assert t.delayed_exit_date is None and t.ownership_delayed_exit is False
    assert float(t.loss_beyond_stop) == pytest.approx((95.0 - 90.0) * t.quantity)  # gap slippage past the stop
    assert run.validation["ownership_delayed_stops"] == {
        "count": 0,
        "total_loss_beyond_stop": "0.0000",
        "events": [],
    }

    run = run_single(install_market, monkeypatch, {68: {"low": 90.0}})  # fills at the stop level itself
    t = first_trade(run)
    assert float(t.exit_price) == pytest.approx(95.0)
    assert float(t.loss_beyond_stop) == 0.0


def test_non_stop_exits_carry_the_stop_level_but_no_breach_fields(install_market, monkeypatch):
    run = run_single(install_market, monkeypatch, {68: {"high": 125.0}})  # target exit
    t = first_trade(run)
    assert t.exit_reason == "target"
    assert float(t.stop_price) == pytest.approx(95.0)
    assert t.stop_breach_date is None
    assert t.delayed_exit_date is None
    assert t.loss_beyond_stop is None


# --------------------------------------------------------------------------- B-03 sizing / fill validation


def test_signal_time_quantity_does_not_depend_on_next_session_open(install_market, monkeypatch):
    signal_qty, final_qty = {}, {}
    for label in ("base", "gap_up"):
        ov = {} if label == "base" else {63: {"open": 110.0, "high": 111.0, "low": 109.0, "close": 110.0}}
        install_market({"AAA": make_bars(N, overrides=ov)})
        stub_signals(monkeypatch, stop=70.0, target=10_000.0)
        run = run_backtest(make_cfg(bar_date(62, N), bar_date(N - 1, N), hold_days=5))
        t = first_trade(run)
        signal_qty[label], final_qty[label] = t.signal_quantity, t.quantity
    # Signal-time size must not depend on the next session's open:
    # risk budget 0.75% of 100k = 750; assumed entry 100, stop 70 -> 750 / 30 = 25 shares.
    assert signal_qty["base"] == signal_qty["gap_up"] == 25
    # Fill-time validation may only reduce quantity (gap-up fill at 110 -> risk 750 / 40 -> 18 shares).
    assert final_qty["gap_up"] <= signal_qty["gap_up"]


def test_fill_gapping_through_stop_is_rejected_at_fill(install_market, monkeypatch):
    gap = {"open": 90.0, "high": 91.0, "low": 89.0, "close": 90.0}
    run = run_single(install_market, monkeypatch, {63: gap})
    assert run.metrics.fill_rejections >= 1


def test_guard_fill_time_caps_quantity_at_fill_price(install_market, monkeypatch):
    """GUARD (passes before and after Phase 1).

    Signal-time size is 100 shares (cash/cap at assumed entry 100, risk 750/5 = 150).
    Fill opens at 102, so at fill: position cap 10% of 100,000 / 102 = 98 shares, and risk 750 / 7 = 107.
    Only the cap binds, so the fill-time quantity must be 98: cut, never raised.
    """
    gap_up = {"open": 102.0, "high": 103.0, "low": 101.0, "close": 102.0}
    install_market({"AAA": make_bars(N, overrides={63: gap_up})})
    stub_signals(monkeypatch, stop=95.0, target=150.0)
    run = run_backtest(make_cfg(bar_date(62, N), bar_date(N - 1, N), hold_days=5))
    assert first_trade(run).quantity == 98


# --------------------------------------------------------------------------- B-08 stale marks


def _stale_run(install_market, monkeypatch, *, skip):
    install_market({"HELD": make_bars(N, skip=skip), "OTHER": make_bars(N)})
    stub_signals(monkeypatch, scores={"HELD": 90, "OTHER": 50})
    return run_backtest(make_cfg(bar_date(62, N), bar_date(N - 1, N)))


def test_stale_marks_are_counted_and_warned(install_market, monkeypatch):
    run = _stale_run(install_market, monkeypatch, skip=range(70, 85))
    assert run.metrics.stale_marks >= 15
    assert run.metrics.max_stale_days >= 15
    assert any("stale" in w.lower() for w in run.validation["warnings"])


def test_no_stale_marks_without_gaps(install_market, monkeypatch):
    run = _stale_run(install_market, monkeypatch, skip=())
    assert run.metrics.stale_marks == 0


# --------------------------------------------------------------------------- B-09 / B-12 / B-14 universe


def test_full_universe_is_scanned_and_benchmark_is_never_traded(install_market, monkeypatch):
    frames = {f"S{i}": make_bars(N) for i in range(1, 7)}
    frames["NIFTY500_PROXY"] = make_bars(N)
    install_market(frames)
    stub_signals(monkeypatch, scores={"S6": 95, "NIFTY500_PROXY": 99})
    run = run_backtest(make_cfg(bar_date(62, N), bar_date(N - 1, N), hold_days=5))
    traded = {t.symbol for t in run.trades}
    assert "S6" in traded, "sixth symbol never scanned (scan cap still in place)"
    assert "NIFTY500_PROXY" not in traded
    cov = run.validation["coverage"]
    assert cov["benchmark_excluded"] == ["NIFTY500_PROXY"]
    assert len(cov["scanned_symbols"]) == 6


def test_partial_and_excluded_symbols_are_reported_not_silently_dropped(install_market, monkeypatch):
    n = 200
    frames = {
        "AAA": make_bars(n),
        "BBB": make_bars(n, skip=range(0, 100)),  # data starts at bar 100 (late listing / late data start)
        "CCC": make_bars(60),  # data ends before the requested range
    }
    install_market(frames)
    stub_signals(monkeypatch, scores={"AAA": 70, "BBB": 90, "CCC": 85})
    run = run_backtest(make_cfg(bar_date(70, n), bar_date(n - 1, n), hold_days=5))

    cov = run.validation["coverage"]
    assert cov["symbols"]["AAA"]["status"] == "full"
    assert cov["symbols"]["BBB"]["status"] == "partial"
    assert "CCC" in cov["excluded"]
    warnings = run.validation["warnings"]
    assert any("BBB" in w for w in warnings)
    assert any("CCC" in w for w in warnings)
    assert any("survivorship" in w.lower() for w in warnings), "survivorship must stay disclosed"

    traded = {t.symbol for t in run.trades}
    assert "AAA" in traded
    assert "CCC" not in traded
    bbb = [t for t in run.trades if t.symbol == "BBB"]
    assert bbb, "late-starting symbol was dropped for the whole run (selection on future data)"
    # point-in-time: BBB has its 60th own bar at index 159; the signal at 159 fills on 160 (the earliest legal entry)
    assert all(t.entry_date >= bar_date(160, n) for t in bbb)


# --------------------------------------------------------------------------- B-30 coverage


def test_end_gap_is_reported(install_market, monkeypatch):
    install_market({"AAA": make_bars(N)})
    stub_signals(monkeypatch)
    last = bar_date(N - 1, N)
    run = run_backtest(make_cfg(bar_date(62, N), last + timedelta(days=30)))
    cov = run.validation["coverage"]
    assert cov["end_gap_days"] >= 28
    assert any("coverage" in w.lower() for w in run.validation["warnings"])


def test_run_fails_loudly_when_no_sessions_in_range(install_market, monkeypatch):
    install_market({"AAA": make_bars(N)})
    stub_signals(monkeypatch)
    start = bar_date(N - 1, N) + timedelta(days=10)
    run = run_backtest(make_cfg(start, start + timedelta(days=40)))
    assert run.status.value == "FAILED"
    assert any("session" in w.lower() for w in run.warnings)


# --------------------------------------------------------------------------- B-28 provenance


def test_synthetic_runs_are_labelled_demo(install_market, monkeypatch):
    install_market({"AAA": make_bars(N)})
    stub_signals(monkeypatch)
    run = run_backtest(make_cfg(bar_date(62, N), bar_date(N - 1, N)))
    assert run.evidence_grade.value == "demo"
    assert run.data_provenance.kind == "synthetic"
    assert run.data_provenance.symbols["AAA"]
    dumped = run.model_dump(mode="json")
    assert dumped["evidence_grade"] == "demo"
    assert dumped["data_provenance"]["kind"] == "synthetic"


def test_provenance_is_persisted_and_served_by_api(install_market, monkeypatch):
    from fastapi.testclient import TestClient

    from app.main import app

    install_market({"AAA": make_bars(N)})
    stub_signals(monkeypatch)
    client = TestClient(app)
    res = client.post(
        "/api/v1/backtests?run_now=true",
        json={
            "name": "m14_p1_api",
            "start_date": bar_date(62, N).isoformat(),
            "end_date": bar_date(N - 1, N).isoformat(),
            "shariah_mode": "RESEARCH_ONLY",
            "cost_scenario": "ZERO",
            "slippage_bps": 0,
            "max_positions": 1,
            "hold_days": 400,
        },
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["evidence_grade"] == "demo"
    assert body["data_provenance"]["kind"] == "synthetic"

    got = client.get(f"/api/v1/backtests/{body['backtest_id']}").json()
    assert got["evidence_grade"] == "demo"
    listed = client.get("/api/v1/backtests").json()["items"]
    assert any(i["backtest_id"] == body["backtest_id"] and i["evidence_grade"] == "demo" for i in listed)


# --------------------------------------------------------------------------- GUARDS (pass before and after)


def test_guard_strict_mode_still_rejects_without_point_in_time_snapshot(install_market, monkeypatch):
    install_market({"AAA": make_bars(N)})
    stub_signals(monkeypatch)
    cfg = make_cfg(bar_date(62, N), bar_date(N - 1, N), shariah_mode=ShariahBacktestMode.STRICT)
    run = run_backtest(cfg)
    assert run.trades == []
    assert run.metrics.shariah_rejections > 0


def test_guard_time_exit_still_waits_for_sell_authorisation(install_market, monkeypatch):
    install_market({"AAA": make_bars(N)})
    stub_signals(monkeypatch, stop=1.0, target=10_000.0)
    run = run_backtest(make_cfg(bar_date(62, N), bar_date(N - 1, N), hold_days=1))
    assert run.trades
    for t in run.trades:
        authorised = (pd.Timestamp(t.entry_date) + pd.offsets.BDay(3)).date()
        assert t.exit_date >= authorised


def test_guard_backtest_does_not_touch_the_live_portfolio_book(install_market, monkeypatch):
    from app.portfolio import store as portfolio_store

    install_market({"AAA": make_bars(N)})
    stub_signals(monkeypatch)
    run_backtest(make_cfg(bar_date(62, N), bar_date(N - 1, N), hold_days=5))
    assert portfolio_store._BOOK_MEM is None  # noqa: SLF001 - M12 isolation: sim never loads/writes the book
