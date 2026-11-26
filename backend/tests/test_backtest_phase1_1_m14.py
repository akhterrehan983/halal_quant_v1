"""M14 Phase 1.1 regression tests — deterministic universe and benchmark handling.

F-1  benchmark loading / tradable-symbol construction independent of scenario and run order
F-2  benchmark / index proxies excluded from breadth, which stays point-in-time and causal
F-3  explicit benchmark registry: registered benchmarks are never scanned, sampled, or traded

The signal generator is replaced by a stub that reads the same inputs the real one does (the benchmark
slice and as-of breadth) and bases its score on them. Any order dependence in either input therefore
changes scores, entries, exits, and metrics. Data are fixed seeded random walks, not performance evidence.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest
from sqlalchemy import create_engine, select, update
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.backtesting.schemas import BacktestConfig, CostScenario, ShariahBacktestMode
from app.backtesting.simulator import run_backtest
from app.core import config
from app.core.database import Base
from app.data import sample_data
from app.execution import store
from app.execution.order_manager import create_order
from app.execution.schemas import OrderSide, OrderState, OrderType
from app.market_data import benchmarks, repository
from app.market_data.persistence import candle_fingerprints
from app.market_data.repository import (
    bar_fingerprints,
    iter_symbol_histories,
    list_all_symbols,
    list_universe_symbols,
)
from app.models import OHLCVCandle, Stock
from app.regime import benchmark as benchmark_mod
from app.regime import market_breadth
from app.regime.market_breadth import compute_universe_breadth
from app.signals.schemas import SignalCategory

BASE_DATE = "2023-01-02"
N = 130
EQUITIES = {"AAA": 11, "BBB": 22, "CCC": 33}  # symbol -> seed
EQUITY_BONUS = {"AAA": 3, "BBB": 2, "CCC": 1}
SCENARIOS = {
    "A": dict(shariah_mode=ShariahBacktestMode.RESEARCH_ONLY, cost_scenario=CostScenario.ZERO),
    "B": dict(shariah_mode=ShariahBacktestMode.RESEARCH_ONLY, cost_scenario=CostScenario.REALISTIC),
    "C": dict(shariah_mode=ShariahBacktestMode.STRICT, cost_scenario=CostScenario.ZERO),
}


# --------------------------------------------------------------------------- helpers


def bar_date(i: int):
    return pd.bdate_range(start=BASE_DATE, periods=N)[i].date()


def walk(seed: int, n: int = N, start: float = 100.0, vol: float = 0.015) -> pd.DataFrame:
    rng = np.random.RandomState(seed)
    close = start * np.cumprod(1 + rng.normal(0.0004, vol, n))
    open_ = np.concatenate([[start], close[:-1]]) * (1 + rng.normal(0, 0.003, n))
    high = np.maximum(open_, close) * (1 + np.abs(rng.normal(0, 0.004, n)))
    low = np.minimum(open_, close) * (1 - np.abs(rng.normal(0, 0.004, n)))
    return pd.DataFrame(
        {
            "date": pd.bdate_range(start=BASE_DATE, periods=n),
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": 1_000_000.0,
        }
    )


def fresh_market(monkeypatch, extra: dict[str, pd.DataFrame] | None = None) -> None:
    """Install a clean market, as a freshly started process would see it."""
    frames = {sym: walk(seed) for sym, seed in EQUITIES.items()}
    frames.update(extra or {})
    monkeypatch.setattr(sample_data, "HISTORIES", {k: v.copy() for k, v in frames.items()})
    monkeypatch.setattr(sample_data, "SYMBOLS", list(frames))
    benchmark_mod.clear_benchmark_cache()


@pytest.fixture(autouse=True)
def _clean_benchmark_cache():
    benchmark_mod.clear_benchmark_cache()
    yield
    benchmark_mod.clear_benchmark_cache()


def install_regime_aware_stub(monkeypatch, holder: dict, *, unknown_bonus: int = 50) -> None:
    """Stub signal whose score depends on the benchmark slice and as-of breadth, and records both."""

    def fake(symbol, df, horizon="swing", *, as_of_index=-1):
        session = pd.Timestamp(df["date"].iloc[-1]).date()
        bench, _ = benchmark_mod.benchmark_slice(-1, as_of_date=session)
        breadth = compute_universe_breadth(as_of_date=session)
        pct = breadth["pct_above_sma50"] or 0.0
        bench_up = len(bench) > 5 and float(bench["close"].iloc[-1]) >= float(bench["close"].iloc[-6])
        holder["signals"].append(
            (
                symbol,
                session.isoformat(),
                len(bench),
                round(float(bench["close"].iloc[-1]), 8) if len(bench) else None,
                breadth["symbols_sampled"],
                pct,
            )
        )
        close = float(df["close"].iloc[-1])
        score = int(40 + 20 * pct + (10 if bench_up else 0) + EQUITY_BONUS.get(symbol, unknown_bonus))
        return SimpleNamespace(
            symbol=symbol,
            category=SignalCategory.BUY,
            overall_score=score,
            stop_reference=close * 0.96,
            target_reference=close * 1.06,
        )

    monkeypatch.setattr("app.backtesting.simulator.generate_unified_signal", fake)


def spy_breadth_inputs(monkeypatch, sink: list) -> None:
    real = market_breadth.get_history_window

    def spy(symbol, *, end, lookback_bars=520):
        sink.append((symbol, end.isoformat()))
        return real(symbol, end=end, lookback_bars=lookback_bars)

    monkeypatch.setattr(market_breadth, "get_history_window", spy)


def make_cfg(**kw) -> BacktestConfig:
    base = dict(
        name="m14_p11",
        start_date=bar_date(70),
        end_date=bar_date(100),
        slippage_bps=10,
        max_positions=2,
        hold_days=8,
    )
    base.update(kw)
    return BacktestConfig(**base)


def run_scenarios(monkeypatch, order: list[str]) -> tuple[dict, list[str]]:
    """Run the named scenarios in ``order`` on a fresh market; return per-scenario evidence."""
    fresh_market(monkeypatch)
    holder: dict = {"signals": []}
    breadth_inputs: list = []
    install_regime_aware_stub(monkeypatch, holder)
    spy_breadth_inputs(monkeypatch, breadth_inputs)
    out: dict = {}
    for name in order:
        holder["signals"] = []
        breadth_inputs.clear()
        run = run_backtest(make_cfg(**SCENARIOS[name]))
        assert run.status.value == "COMPLETED"
        out[name] = {
            "coverage": run.validation["coverage"],
            "breadth_inputs": list(breadth_inputs),
            "signal_inputs": list(holder["signals"]),
            "trades": [t.model_dump(mode="json") for t in run.trades],
            "metrics": run.metrics.model_dump(mode="json"),
            "equity": [p.model_dump(mode="json") for p in run.equity_curve],
        }
    return out, list(sample_data.SYMBOLS)


# --------------------------------------------------------------------------- F-1 determinism


def test_scenario_order_does_not_change_symbols_breadth_trades_or_metrics(monkeypatch):
    first, symbols_after_first = run_scenarios(monkeypatch, ["A", "B", "C"])
    second, symbols_after_second = run_scenarios(monkeypatch, ["C", "B", "A"])

    for name in SCENARIOS:
        a, b = first[name], second[name]
        assert a["coverage"] == b["coverage"], f"{name}: symbols/coverage depend on run order"
        assert a["breadth_inputs"] == b["breadth_inputs"], f"{name}: breadth inputs depend on run order"
        assert a["signal_inputs"] == b["signal_inputs"], f"{name}: benchmark/breadth seen by signals differ"
        assert a["trades"] == b["trades"], f"{name}: trades depend on run order"
        assert a["metrics"] == b["metrics"], f"{name}: metrics depend on run order"
        assert a["equity"] == b["equity"], f"{name}: equity curve depends on run order"

    # The comparison is only meaningful if the runs actually did something.
    assert first["A"]["trades"], "scenario A produced no trades"
    assert first["B"]["trades"], "scenario B produced no trades"
    assert first["A"]["signal_inputs"] and first["A"]["breadth_inputs"]

    # The stored universe is never changed by running (the old lazy proxy build appended to it).
    assert symbols_after_first == symbols_after_second == list(EQUITIES)

    # Breadth sampled only equities; the tradable set is the same equities in every scenario and order.
    for name in SCENARIOS:
        assert {s for s, _ in first[name]["breadth_inputs"]} == set(EQUITIES)
        assert first[name]["coverage"]["scanned_symbols"] == list(EQUITIES)
        assert first[name]["coverage"]["benchmark_excluded"] == []  # no registered benchmark was stored


def test_building_the_benchmark_proxy_has_no_side_effects(monkeypatch):
    fresh_market(monkeypatch)
    symbols_before = list(sample_data.SYMBOLS)
    histories_before = set(sample_data.HISTORIES)
    universe_before = list_universe_symbols()

    first = benchmark_mod.ensure_benchmark_history()

    assert list(sample_data.SYMBOLS) == symbols_before
    assert set(sample_data.HISTORIES) == histories_before
    assert list_universe_symbols() == universe_before == list(EQUITIES)
    assert list_all_symbols() == symbols_before

    second = benchmark_mod.ensure_benchmark_history()
    pd.testing.assert_frame_equal(first, second, check_exact=True)

    first.loc[0, "close"] = -1.0  # a caller mutating its copy must not poison the cache
    pd.testing.assert_frame_equal(benchmark_mod.ensure_benchmark_history(), second, check_exact=True)


def count_proxy_builds(monkeypatch) -> list:
    """Wrap the proxy builder so tests can tell a cache hit from a rebuild."""
    builds: list = []
    real = benchmark_mod._build_equal_weight_proxy  # noqa: SLF001

    def counting(symbols):
        builds.append(tuple(symbols))
        return real(symbols)

    monkeypatch.setattr(benchmark_mod, "_build_equal_weight_proxy", counting)
    return builds


def test_proxy_is_independent_of_symbol_order(monkeypatch):
    fresh_market(monkeypatch)
    builds = count_proxy_builds(monkeypatch)
    reference = benchmark_mod.ensure_benchmark_history()
    assert len(builds) == 1

    # Same data, reversed list order, warm cache -> identical, and a cache hit (the key is order free).
    monkeypatch.setattr(sample_data, "SYMBOLS", list(reversed(sample_data.SYMBOLS)))
    assert list_universe_symbols() == list(reversed(list(EQUITIES)))  # the order really did change
    pd.testing.assert_frame_equal(benchmark_mod.ensure_benchmark_history(), reference, check_exact=True)
    assert len(builds) == 1

    # Same data, reversed list order, cold cache -> a real rebuild is also identical (build sorts symbols).
    benchmark_mod.clear_benchmark_cache()
    pd.testing.assert_frame_equal(benchmark_mod.ensure_benchmark_history(), reference, check_exact=True)
    assert len(builds) == 2
    assert list(builds[1]) == list(reversed(list(EQUITIES)))  # the builder really was handed reversed order

    # The fingerprint itself ignores list order and symbol case.
    assert bar_fingerprints(["CCC", "AAA", "BBB"]) == bar_fingerprints(["bbb", "AAA", "ccc"])


def test_proxy_rebuilds_when_bars_change_but_the_symbol_set_is_identical(monkeypatch):
    """Regression: the old key was (symbol, bar count, last date) in memory mode and the symbol set only in
    database mode, so a corrected or restated bar with an unchanged symbol list served a stale proxy."""
    fresh_market(monkeypatch)
    builds = count_proxy_builds(monkeypatch)

    reference = benchmark_mod.ensure_benchmark_history()
    benchmark_mod.ensure_benchmark_history()
    assert len(builds) == 1  # unchanged data -> cache hit

    original = sample_data.HISTORIES["AAA"]
    middle = len(original) // 2
    edited = original.copy()
    edited.loc[middle, "close"] = float(original.loc[middle, "close"]) * 1.25

    # Preconditions: everything the old key looked at is identical, only one middle close differs.
    symbols_before = list(sample_data.SYMBOLS)
    sample_data.HISTORIES["AAA"] = edited
    assert list(sample_data.SYMBOLS) == symbols_before
    assert len(edited) == len(original)
    assert edited["date"].iloc[-1] == original["date"].iloc[-1]
    assert edited["close"].iloc[-1] == original["close"].iloc[-1]

    changed = benchmark_mod.ensure_benchmark_history()
    assert len(builds) == 2, "a changed bar must force a rebuild"
    assert not changed["close"].equals(reference["close"]), "the proxy must reflect the changed bar"

    # Restoring the original bar restores the original proxy exactly (rebuilt, not a stale hit).
    sample_data.HISTORIES["AAA"] = original
    restored = benchmark_mod.ensure_benchmark_history()
    assert len(builds) == 3
    pd.testing.assert_frame_equal(restored, reference, check_exact=True)


def test_proxy_rebuilds_when_a_symbol_is_added(monkeypatch):
    fresh_market(monkeypatch)
    reference = benchmark_mod.ensure_benchmark_history()
    sample_data.HISTORIES["DDD"] = walk(44)
    sample_data.SYMBOLS.append("DDD")
    assert not benchmark_mod.ensure_benchmark_history()["close"].equals(reference["close"])


# --------------------------------------------------------------------------- database-mode fingerprint


def bars_to_candles(symbol: str, frame: pd.DataFrame) -> list[OHLCVCandle]:
    def money(x) -> Decimal:
        return Decimal(str(round(float(x), 4)))

    return [
        OHLCVCandle(
            symbol=symbol,
            exchange="NSE",
            trading_date=pd.Timestamp(row.date).date(),
            open=money(row.open),
            high=money(row.high),
            low=money(row.low),
            close=money(row.close),
            volume=int(row.volume),
        )
        for row in frame.itertuples()
    ]


def seed_database(session, symbols: dict[str, int]) -> None:
    for sym, seed in symbols.items():
        session.add(Stock(symbol=sym, exchange="NSE", company_name=sym, is_active=True))
        session.add_all(bars_to_candles(sym, walk(seed)))
    session.commit()


def edit_candle(session, symbol: str, index: int, **changes) -> None:
    """Edit one stored bar while holding ``updated_at`` fixed, so only the OHLCV content signals the change."""
    row = session.execute(
        select(OHLCVCandle).where(OHLCVCandle.symbol == symbol, OHLCVCandle.trading_date == bar_date(index))
    ).scalar_one()
    session.execute(
        update(OHLCVCandle).where(OHLCVCandle.id == row.id).values(updated_at=row.updated_at, **changes)
    )
    session.commit()
    session.expire_all()


def test_candle_fingerprints_detect_any_changed_bar_when_symbols_and_dates_are_identical(sqlite_session):
    seed_database(sqlite_session, {"AAA": 11, "BBB": 22})
    base = candle_fingerprints(sqlite_session, ["AAA", "BBB"])
    assert set(base) == {"AAA", "BBB"}
    assert candle_fingerprints(sqlite_session, ["bbb", "AAA"]) == base  # stable, order and case free
    assert candle_fingerprints(sqlite_session, ["AAA", "NOPE"]).keys() == {"AAA"}  # unknown symbols omitted
    assert candle_fingerprints(sqlite_session, []) == {}

    def close_of(sym, i):
        return sqlite_session.execute(
            select(OHLCVCandle.close).where(OHLCVCandle.symbol == sym, OHLCVCandle.trading_date == bar_date(i))
        ).scalar_one()

    # 1. One middle close edited: count, first and last dates all unchanged.
    edit_candle(sqlite_session, "AAA", 60, close=close_of("AAA", 60) + Decimal("1.0000"))
    after_close = candle_fingerprints(sqlite_session, ["AAA", "BBB"])
    assert after_close["AAA"] != base["AAA"]
    assert after_close["BBB"] == base["BBB"]  # other symbols are unaffected
    assert after_close["AAA"][:3] == base["AAA"][:3]  # (count, first date, last date) really did not move

    # 2. Volume-only edit.
    edit_candle(sqlite_session, "BBB", 50, volume=123_456)
    after_volume = candle_fingerprints(sqlite_session, ["AAA", "BBB"])
    assert after_volume["BBB"] != base["BBB"]

    # 3. Two closes swapped between dates: every plain sum is unchanged, the id-weighted sum is not.
    first, second = close_of("AAA", 20), close_of("AAA", 21)
    assert first != second
    before_swap = candle_fingerprints(sqlite_session, ["AAA"])["AAA"]
    edit_candle(sqlite_session, "AAA", 20, close=second)
    edit_candle(sqlite_session, "AAA", 21, close=first)
    assert candle_fingerprints(sqlite_session, ["AAA"])["AAA"] != before_swap


def test_database_mode_proxy_rebuilds_when_bars_change_but_the_symbol_set_is_identical(monkeypatch):
    """The exact defect branch: database mode, identical symbols, one edited bar."""
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with factory() as seeding:
        seed_database(seeding, EQUITIES)

    # Force database mode in the repository, the module that owns the storage-mode decision.
    monkeypatch.setattr(repository, "settings", SimpleNamespace(database_enabled=True))
    monkeypatch.setattr(repository, "SessionLocal", factory)
    benchmark_mod.clear_benchmark_cache()
    builds = count_proxy_builds(monkeypatch)

    assert list_universe_symbols() == sorted(EQUITIES)
    assert set(bar_fingerprints(list(EQUITIES))) == set(EQUITIES)  # served by the database, not memory

    reference = benchmark_mod.ensure_benchmark_history()
    assert len(reference) > 100
    benchmark_mod.ensure_benchmark_history()
    assert len(builds) == 1  # unchanged data -> cache hit

    with factory() as session:
        edit_candle(session, "AAA", 60, close=Decimal("250.0000"))
    assert list_universe_symbols() == sorted(EQUITIES)  # same symbols

    changed = benchmark_mod.ensure_benchmark_history()
    assert len(builds) == 2, "a changed stored bar must force a rebuild in database mode"
    assert not changed["close"].equals(reference["close"])


def test_settings_are_not_bound_at_import_time(monkeypatch):
    # The registry reads the active settings object at call time, so swapping it takes effect.
    monkeypatch.setattr(config, "settings", SimpleNamespace(benchmark_symbols="SWAPPED"))
    assert "SWAPPED" in benchmarks.benchmark_symbols()
    assert benchmarks.is_benchmark("swapped")

    # The proxy module owns no settings binding at all; the storage mode is decided in the repository.
    assert not hasattr(benchmark_mod, "settings")


# --------------------------------------------------------------------------- F-2 breadth


def test_breadth_excludes_benchmark_proxy_and_stays_point_in_time(monkeypatch):
    fresh_market(monkeypatch, {"NIFTY500_PROXY": walk(99)})  # a stored benchmark series is present
    session = bar_date(100)

    assert "NIFTY500_PROXY" in list_all_symbols()
    assert "NIFTY500_PROXY" not in list_universe_symbols()
    assert "NIFTY500_PROXY" not in {s for s, _ in iter_symbol_histories()}

    sink: list = []
    spy_breadth_inputs(monkeypatch, sink)
    as_of = compute_universe_breadth(as_of_date=session)
    assert {s for s, _ in sink} == set(EQUITIES)
    assert as_of["symbols_sampled"] == len(EQUITIES)
    assert compute_universe_breadth()["symbols_sampled"] == len(EQUITIES)  # latest-bar path too

    # Causality: appending much higher future bars to every symbol must not change an as-of breadth.
    for sym in EQUITIES:
        hist = sample_data.HISTORIES[sym]
        future = walk(7, n=40)
        future[["open", "high", "low", "close"]] = future[["open", "high", "low", "close"]] * 10
        future["date"] = pd.bdate_range(start=pd.Timestamp(hist["date"].iloc[-1]) + timedelta(days=1), periods=40)
        sample_data.HISTORIES[sym] = pd.concat([hist, future], ignore_index=True)
    assert compute_universe_breadth(as_of_date=session) == as_of


# --------------------------------------------------------------------------- F-3 registry


def test_registry_defaults_and_configuration(monkeypatch):
    monkeypatch.setattr(config.settings, "benchmark_symbols", "")
    assert benchmarks.benchmark_symbols() == frozenset({"NIFTY500_PROXY"})
    assert benchmarks.registered_benchmarks()["NIFTY500_PROXY"].kind == "equal_weight_proxy"
    assert benchmarks.is_benchmark(" nifty500_proxy ")
    assert not benchmarks.is_benchmark("TCS")

    monkeypatch.setattr(config.settings, "benchmark_symbols", " nifty50 , NIFTYBANK ,,")
    assert benchmarks.benchmark_symbols() == frozenset({"NIFTY500_PROXY", "NIFTY50", "NIFTYBANK"})
    assert benchmarks.registered_benchmarks()["NIFTY50"].kind == "configured"
    assert benchmarks.is_benchmark("niftybank")
    assert benchmarks.registered_benchmarks() == benchmarks.registered_benchmarks()  # no hidden state


def test_configured_benchmark_is_never_scanned_sampled_or_traded(monkeypatch):
    monkeypatch.setattr(config.settings, "benchmark_symbols", "NIFTYTEST")
    fresh_market(monkeypatch, {"NIFTYTEST": walk(55)})
    holder: dict = {"signals": []}
    install_regime_aware_stub(monkeypatch, holder, unknown_bonus=50)  # would win any scan if it were scanned
    sink: list = []
    spy_breadth_inputs(monkeypatch, sink)

    assert "NIFTYTEST" in list_all_symbols()
    assert "NIFTYTEST" not in list_universe_symbols()

    run = run_backtest(make_cfg(**SCENARIOS["A"]))
    cov = run.validation["coverage"]
    assert cov["scanned_symbols"] == list(EQUITIES)
    assert cov["benchmark_excluded"] == ["NIFTYTEST"]
    assert cov["benchmarks_registered"] == ["NIFTY500_PROXY", "NIFTYTEST"]
    assert "NIFTYTEST" not in cov["symbols"]
    assert "NIFTYTEST" not in {row[0] for row in holder["signals"]}  # never offered to the signal generator
    assert "NIFTYTEST" not in {s for s, _ in sink}  # never a breadth constituent
    assert run.trades and "NIFTYTEST" not in {t.symbol for t in run.trades}

    # An explicit request naming benchmarks (any case, duplicates) is filtered the same way.
    run = run_backtest(make_cfg(symbols=["AAA", "niftytest", "NIFTY500_PROXY", "AAA"], **SCENARIOS["A"]))
    cov = run.validation["coverage"]
    assert cov["scanned_symbols"] == ["AAA"]
    assert cov["benchmark_excluded"] == ["NIFTY500_PROXY", "NIFTYTEST"]


def test_registered_benchmark_cannot_be_bought_as_an_equity():
    store._STATE = store._empty()  # noqa: SLF001
    order = create_order(
        symbol="NIFTY500_PROXY",
        sleeve="swing",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=1,
        proposal_id=None,
    )
    assert order.state == OrderState.REJECTED
    assert any("not a tradable equity" in reason for reason in order.rejections)
