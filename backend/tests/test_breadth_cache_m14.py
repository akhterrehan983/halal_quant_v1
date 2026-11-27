"""M14 F-4 — run-scoped as-of breadth cache.

Cached breadth must equal uncached breadth exactly. A change to the as-of session, the equity universe,
the benchmark registry, or any stored equity bar must recompute. Benchmarks are never constituents, and
nothing is cached outside a backtest run, so no run can see another run's memo.
Data are fixed seeded random walks, not performance evidence.
"""

from __future__ import annotations

import contextlib
from decimal import Decimal
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest
from sqlalchemy import create_engine, select, update
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.backtesting import simulator
from app.backtesting.schemas import BacktestConfig, CostScenario, ShariahBacktestMode
from app.backtesting.simulator import run_backtest
from app.core import config
from app.core.database import Base
from app.data import sample_data
from app.market_data import repository
from app.models import OHLCVCandle, Stock
from app.regime import benchmark as benchmark_mod
from app.regime import market_breadth
from app.regime.market_breadth import breadth_cache_scope, compute_universe_breadth
from app.signals.schemas import SignalCategory

BASE_DATE = "2023-01-02"
N = 130
EQUITIES = {"AAA": 11, "BBB": 22, "CCC": 33}  # symbol -> seed
EQUITY_BONUS = {"AAA": 3, "BBB": 2, "CCC": 1}

uncached = market_breadth._compute_universe_breadth  # noqa: SLF001  (the real formula, never memoised)


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


@pytest.fixture(autouse=True)
def market(monkeypatch):
    frames = {sym: walk(seed) for sym, seed in EQUITIES.items()}
    monkeypatch.setattr(sample_data, "HISTORIES", frames)
    monkeypatch.setattr(sample_data, "SYMBOLS", list(frames))
    monkeypatch.setattr(config.settings, "benchmark_symbols", "")
    benchmark_mod.clear_benchmark_cache()
    yield
    benchmark_mod.clear_benchmark_cache()


def count_computations(monkeypatch) -> list:
    """Record every real (uncached) breadth computation, so a cache hit can be told from a recompute."""
    calls: list = []

    def counting(as_of_date):
        calls.append(as_of_date)
        return uncached(as_of_date)

    monkeypatch.setattr(market_breadth, "_compute_universe_breadth", counting)
    return calls


def set_close(symbol: str, index: int, factor: float) -> None:
    """Replace ``symbol``'s frame with a copy whose close at ``index`` is scaled (same dates, same length)."""
    edited = sample_data.HISTORIES[symbol].copy()
    edited.loc[index, "close"] = float(edited.loc[index, "close"]) * factor
    sample_data.HISTORIES[symbol] = edited


# --------------------------------------------------------------------------- identity


def test_cached_breadth_is_identical_to_uncached(monkeypatch):
    sessions = [bar_date(i) for i in (60, 75, 90, 105, N - 1)]
    reference = {d: uncached(d) for d in sessions}
    assert all(r["symbols_sampled"] == len(EQUITIES) for r in reference.values())
    assert any(r["pct_above_sma50"] not in (None, 0.0) for r in reference.values())

    calls = count_computations(monkeypatch)
    with breadth_cache_scope():
        first = {d: compute_universe_breadth(as_of_date=d) for d in sessions}
        again = {d: compute_universe_breadth(as_of_date=d) for d in reversed(sessions)}

    assert first == again == reference
    assert calls == sessions  # each session computed exactly once; the repeats were cache hits


def test_nothing_is_cached_outside_a_scope_or_for_latest_bar_breadth(monkeypatch):
    calls = count_computations(monkeypatch)
    d = bar_date(100)
    compute_universe_breadth(as_of_date=d)
    compute_universe_breadth(as_of_date=d)
    with breadth_cache_scope():
        compute_universe_breadth()
        compute_universe_breadth()
    assert calls == [d, d, None, None]


# --------------------------------------------------------------------------- invalidation


def test_a_different_as_of_session_is_never_served_from_another_session(monkeypatch):
    calls = count_computations(monkeypatch)
    early, late = bar_date(70), bar_date(71)
    with breadth_cache_scope():
        a = compute_universe_breadth(as_of_date=early)
        b = compute_universe_breadth(as_of_date=late)
    assert calls == [early, late]
    assert a == uncached(early) and a["as_of_date"] == early.isoformat()
    assert b == uncached(late) and b["as_of_date"] == late.isoformat()


def test_equity_universe_change_recomputes(monkeypatch):
    calls = count_computations(monkeypatch)
    d = bar_date(100)
    with breadth_cache_scope():
        before = compute_universe_breadth(as_of_date=d)

        sample_data.HISTORIES["DDD"] = walk(44)
        sample_data.SYMBOLS.append("DDD")
        added = compute_universe_breadth(as_of_date=d)
        assert added == uncached(d)
        assert added["symbols_sampled"] == before["symbols_sampled"] + 1

        sample_data.SYMBOLS.remove("DDD")
        removed = compute_universe_breadth(as_of_date=d)
    assert removed == before == uncached(d)
    assert calls == [d, d]  # removing DDD restores the original key exactly


def test_benchmark_registry_change_recomputes_and_excludes_the_benchmark(monkeypatch):
    calls = count_computations(monkeypatch)
    d = bar_date(100)
    with breadth_cache_scope():
        before = compute_universe_breadth(as_of_date=d)
        monkeypatch.setattr(config.settings, "benchmark_symbols", "BBB")  # BBB becomes a benchmark
        after = compute_universe_breadth(as_of_date=d)
        assert after == uncached(d)
    assert after["symbols_sampled"] == before["symbols_sampled"] - 1
    assert calls == [d, d]


def test_changed_equity_bar_recomputes_with_the_same_universe_and_dates(monkeypatch):
    calls = count_computations(monkeypatch)
    i = 100
    d = bar_date(i)
    originals = {sym: sample_data.HISTORIES[sym] for sym in EQUITIES}
    with breadth_cache_scope():
        reference = compute_universe_breadth(as_of_date=d)

        for sym in EQUITIES:
            set_close(sym, i, 10.0)  # every as-of close far above its SMA50
        high = compute_universe_breadth(as_of_date=d)
        assert high == uncached(d) and high["pct_above_sma50"] == 1.0

        for sym, frame in originals.items():
            sample_data.HISTORIES[sym] = frame
            set_close(sym, i, 0.01)  # every as-of close far below its SMA50
        low = compute_universe_breadth(as_of_date=d)
        assert low == uncached(d) and low["pct_above_sma50"] == 0.0

        sample_data.HISTORIES.update(originals)
        restored = compute_universe_breadth(as_of_date=d)
    assert restored == reference == uncached(d)
    assert calls == [d, d, d]  # restoring the bars restores the original key (a hit, not a stale value)


def test_changed_future_bar_recomputes_conservatively_and_breadth_is_unchanged(monkeypatch):
    calls = count_computations(monkeypatch)
    d = bar_date(100)
    with breadth_cache_scope():
        before = compute_universe_breadth(as_of_date=d)
        set_close("AAA", 120, 10.0)  # after the as-of session: invisible to breadth, but in the fingerprint
        after = compute_universe_breadth(as_of_date=d)
    assert after == before == uncached(d)
    assert calls == [d, d]


def test_benchmark_bars_are_not_constituents_and_do_not_invalidate(monkeypatch):
    sample_data.HISTORIES["NIFTY500_PROXY"] = walk(99)
    sample_data.SYMBOLS.append("NIFTY500_PROXY")
    sampled: list = []
    real_window = market_breadth.get_history_window

    def spy(symbol, *, end, lookback_bars=520):
        sampled.append(symbol)
        return real_window(symbol, end=end, lookback_bars=lookback_bars)

    monkeypatch.setattr(market_breadth, "get_history_window", spy)
    calls = count_computations(monkeypatch)
    d = bar_date(100)
    with breadth_cache_scope():
        before = compute_universe_breadth(as_of_date=d)
        set_close("NIFTY500_PROXY", 100, 10.0)
        after = compute_universe_breadth(as_of_date=d)
    assert set(sampled) == set(EQUITIES)
    assert before["symbols_sampled"] == len(EQUITIES)
    assert after == before == uncached(d)
    assert calls == [d]  # the benchmark is outside the key, so its bars cannot invalidate equity breadth


# --------------------------------------------------------------------------- isolation


def test_cache_does_not_mutate_shared_data_or_leak_mutable_results(monkeypatch):
    snapshot = {sym: frame.copy() for sym, frame in sample_data.HISTORIES.items()}
    symbols_before = list(sample_data.SYMBOLS)
    d = bar_date(100)
    with breadth_cache_scope():
        first = compute_universe_breadth(as_of_date=d)
        first["pct_above_sma50"] = -1.0  # a caller mutating its result must not poison the cache
        second = compute_universe_breadth(as_of_date=d)
    assert second == uncached(d)
    assert list(sample_data.SYMBOLS) == symbols_before
    assert set(sample_data.HISTORIES) == set(snapshot)
    for sym, frame in snapshot.items():
        pd.testing.assert_frame_equal(sample_data.HISTORIES[sym], frame, check_exact=True)


def test_nested_scopes_share_one_memo_and_the_memo_ends_with_the_outer_scope(monkeypatch):
    calls = count_computations(monkeypatch)
    d = bar_date(100)
    with breadth_cache_scope():
        compute_universe_breadth(as_of_date=d)
        with breadth_cache_scope():
            compute_universe_breadth(as_of_date=d)
        compute_universe_breadth(as_of_date=d)
    with breadth_cache_scope():
        compute_universe_breadth(as_of_date=d)
    assert calls == [d, d]  # one per outer scope; a new scope never sees the previous scope's memo
    assert market_breadth._SCOPED_CACHE.get() is None  # noqa: SLF001


# --------------------------------------------------------------------------- simulator wiring


def install_breadth_stub(monkeypatch, seen: list) -> None:
    """Stub signal whose score depends on as-of breadth, recording what each candidate saw."""

    def fake(symbol, df, horizon="swing", *, as_of_index=-1):
        session = pd.Timestamp(df["date"].iloc[-1]).date()
        breadth = compute_universe_breadth(as_of_date=session)
        pct = breadth["pct_above_sma50"] or 0.0
        seen.append((symbol, session.isoformat(), breadth["symbols_sampled"], pct))
        close = float(df["close"].iloc[-1])
        return SimpleNamespace(
            symbol=symbol,
            category=SignalCategory.BUY,
            overall_score=int(40 + 20 * pct + EQUITY_BONUS[symbol]),
            stop_reference=close * 0.96,
            target_reference=close * 1.06,
        )

    monkeypatch.setattr("app.backtesting.simulator.generate_unified_signal", fake)


def make_cfg() -> BacktestConfig:
    return BacktestConfig(
        name="m14_f4",
        start_date=bar_date(70),
        end_date=bar_date(N - 1),
        shariah_mode=ShariahBacktestMode.RESEARCH_ONLY,
        cost_scenario=CostScenario.ZERO,
        max_positions=2,
        hold_days=8,
    )


def run_evidence(monkeypatch) -> dict:
    seen: list = []
    install_breadth_stub(monkeypatch, seen)
    calls = count_computations(monkeypatch)
    run = run_backtest(make_cfg())
    assert run.status.value == "COMPLETED"
    return {
        "calls": list(calls),
        "seen": seen,
        "trades": [t.model_dump(mode="json") for t in run.trades],
        "metrics": run.metrics.model_dump(mode="json"),
        "equity": [p.model_dump(mode="json") for p in run.equity_curve],
    }


def test_backtest_with_cache_matches_backtest_without_cache(monkeypatch):
    cached = run_evidence(monkeypatch)
    monkeypatch.setattr(simulator, "breadth_cache_scope", contextlib.nullcontext)
    plain = run_evidence(monkeypatch)

    assert cached["trades"], "the comparison is only meaningful if the run traded"
    for part in ("seen", "trades", "metrics", "equity"):
        assert cached[part] == plain[part], f"{part} differs between cached and uncached runs"

    # Uncached: one computation per candidate. Cached: one per session that had candidates.
    assert len(plain["calls"]) == len(plain["seen"])
    sessions_with_candidates = sorted({s for _, s, _, _ in cached["seen"]})
    assert [d.isoformat() for d in cached["calls"]] == sessions_with_candidates
    assert len(cached["calls"]) < len(plain["calls"])


def test_consecutive_backtests_never_share_cached_breadth(monkeypatch):
    first = run_evidence(monkeypatch)
    second = run_evidence(monkeypatch)
    assert first == second  # the second run recomputed every session itself
    assert market_breadth._SCOPED_CACHE.get() is None  # noqa: SLF001


# --------------------------------------------------------------------------- database mode


def seed_database(session) -> None:
    for sym, seed in EQUITIES.items():
        session.add(Stock(symbol=sym, exchange="NSE", company_name=sym, is_active=True))
        session.add_all(
            OHLCVCandle(
                symbol=sym,
                exchange="NSE",
                trading_date=pd.Timestamp(row.date).date(),
                open=Decimal(str(round(float(row.open), 4))),
                high=Decimal(str(round(float(row.high), 4))),
                low=Decimal(str(round(float(row.low), 4))),
                close=Decimal(str(round(float(row.close), 4))),
                volume=int(row.volume),
            )
            for row in walk(seed).itertuples()
        )
    session.commit()


def test_database_mode_hit_loads_no_candles_and_an_edited_bar_recomputes(monkeypatch):
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with factory() as seeding:
        seed_database(seeding)
    monkeypatch.setattr(repository, "settings", SimpleNamespace(database_enabled=True))
    monkeypatch.setattr(repository, "SessionLocal", factory)

    loads: list = []
    real_fetch = repository.fetch_candles

    def counting_fetch(session, symbol, **kw):
        loads.append(symbol)
        return real_fetch(session, symbol, **kw)

    monkeypatch.setattr(repository, "fetch_candles", counting_fetch)
    calls = count_computations(monkeypatch)
    i = 100
    d = bar_date(i)

    with breadth_cache_scope():
        reference = compute_universe_breadth(as_of_date=d)
        assert reference["symbols_sampled"] == len(EQUITIES)
        loads.clear()
        assert compute_universe_breadth(as_of_date=d) == reference
        assert loads == []  # a hit is decided from the aggregate fingerprint, without loading candles

        with factory() as session:
            row = session.execute(
                select(OHLCVCandle).where(OHLCVCandle.symbol == "AAA", OHLCVCandle.trading_date == d)
            ).scalar_one()
            session.execute(  # updated_at held fixed: only the OHLCV content signals the change
                update(OHLCVCandle)
                .where(OHLCVCandle.id == row.id)
                .values(updated_at=row.updated_at, close=row.close * 10)
            )
            session.commit()
        changed = compute_universe_breadth(as_of_date=d)
        assert changed == uncached(d)
    assert calls == [d, d]
