"""M14 Phase 2 tests: walk-forward v2 (training-only selection, independent test segments).

The signal generator is replaced by a causal stub (score and stops depend only on the as-of history it is
handed), and prices are fixed seeded random walks. These tests prove the walk-forward machinery and its leakage
protections, not strategy validity. Evidence grade for this data stays DEMO.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.backtesting import simulator
from app.backtesting import walk_forward_v2 as wf2
from app.backtesting.metrics import compute_metrics
from app.backtesting.schemas import (
    BacktestConfig,
    BacktestMetrics,
    BacktestRun,
    BacktestStatus,
    CostScenario,
    EquityPoint,
    ShariahBacktestMode,
)
from app.backtesting.simulator import run_backtest
from app.backtesting.walk_forward import walk_forward as walk_forward_v1
from app.backtesting.walk_forward_schemas import (
    MAX_SEGMENT_RUNS,
    WalkForwardAutoFoldSpec,
    WalkForwardFoldInput,
    WalkForwardGrid,
    WalkForwardSelectionSpec,
    WalkForwardV2Request,
)
from app.backtesting.walk_forward_v2 import (
    Candidate,
    WalkForwardIntegrityError,
    WalkForwardValidationError,
    build_candidates,
    effective_config_hash,
    evaluate_candidates,
    execute_plan,
    generate_auto_folds,
    plan_walk_forward,
    stitch_oos,
    validate_folds,
)
from app.data import sample_data
from app.portfolio.money import D
from app.regime import benchmark as benchmark_mod
from app.regime import market_breadth
from app.signals.config import DEFAULT_WEIGHTS
from app.signals.schemas import SignalCategory

BASE_DATE = "2023-01-02"
N = 260
SYMS = {"AAA": 11, "BBB": 22, "CCC": 33}
SESSIONS = list(pd.bdate_range(start=BASE_DATE, periods=N).date)


def bar_date(i: int) -> date:
    return SESSIONS[i]


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


def install_market(monkeypatch, *, corrupt_from: date | None = None, factors: dict[str, float] | None = None) -> None:
    """Fresh seeded market; optionally scale every price on/after ``corrupt_from`` (the mutation proof-tests)."""
    frames = {sym: walk(seed) for sym, seed in SYMS.items()}
    if corrupt_from is not None:
        for sym, factor in (factors or {"AAA": 2.5, "BBB": 0.4, "CCC": 1.7}).items():
            mask = pd.to_datetime(frames[sym]["date"]).dt.date >= corrupt_from
            frames[sym].loc[mask, ["open", "high", "low", "close"]] *= factor
    monkeypatch.setattr(sample_data, "HISTORIES", {k: v.copy() for k, v in frames.items()})
    monkeypatch.setattr(sample_data, "SYMBOLS", list(frames))
    benchmark_mod.clear_benchmark_cache()


def install_stub(monkeypatch, calls: list | None = None) -> None:
    """Causal stub: BUY with a score derived only from the as-of history passed in."""

    def fake(symbol, df, horizon="swing", *, as_of_index=-1):
        close = float(df["close"].iloc[-1])
        if calls is not None:
            calls.append((symbol, pd.Timestamp(df["date"].iloc[-1]).date(), len(df)))
        return SimpleNamespace(
            symbol=symbol,
            category=SignalCategory.BUY,
            overall_score=76 + int(round(close * 100)) % 24,
            stop_reference=close * 0.96,
            target_reference=close * 1.06,
        )

    monkeypatch.setattr("app.backtesting.simulator.generate_unified_signal", fake)


@pytest.fixture(autouse=True)
def _clean_cache():
    benchmark_mod.clear_benchmark_cache()
    yield
    benchmark_mod.clear_benchmark_cache()


@pytest.fixture
def market(monkeypatch):
    install_market(monkeypatch)
    install_stub(monkeypatch)


def make_cfg(**kw) -> BacktestConfig:
    base = dict(
        name="wf2",
        start_date=bar_date(0),
        end_date=bar_date(N - 1),
        shariah_mode=ShariahBacktestMode.RESEARCH_ONLY,
        cost_scenario=CostScenario.ZERO,
        slippage_bps=10,
        max_positions=2,
        hold_days=8,
        min_signal_score=0,
    )
    base.update(kw)
    return BacktestConfig(**base)


def fold(tr_s: int, tr_e: int, te_s: int, te_e: int, label: str | None = None) -> WalkForwardFoldInput:
    return WalkForwardFoldInput(
        label=label, train_start=bar_date(tr_s), train_end=bar_date(tr_e), test_start=bar_date(te_s), test_end=bar_date(te_e)
    )


FOLD1 = fold(80, 139, 142, 181, "f1")  # 60 train sessions, 2-session embargo, 40 test sessions
FOLD2 = fold(120, 179, 182, 221, "f2")

GRID_SEL = WalkForwardSelectionSpec(
    mode="grid_search", grid=WalkForwardGrid(hold_days=[5, 10, 20, 40], min_signal_score=[80])
)


def req(folds=None, selection=None, **kw) -> WalkForwardV2Request:
    return WalkForwardV2Request(folds=folds or [FOLD1], selection=selection or WalkForwardSelectionSpec(), **kw)


def metrics(ret="0.1", dd="0.05", sharpe: str | None = "1.0", trades=10) -> BacktestMetrics:
    return BacktestMetrics(
        initial_capital=D(100000),
        final_capital=D(100000),
        total_return=Decimal(ret),
        max_drawdown=Decimal(dd),
        sharpe=None if sharpe is None else Decimal(sharpe),
        total_trades=trades,
    )


def cands(n: int) -> list[Candidate]:
    return [Candidate(i, i == 0, 10 + i, 80, 5) for i in range(n)]


# --------------------------------------------------------------------------- fold generation


def test_auto_folds_rolling_are_chronological_and_complete(market):
    spec = WalkForwardAutoFoldSpec(train_sessions=60, embargo_sessions=2, test_sessions=40, step_sessions=40)
    plan = plan_walk_forward(make_cfg(), WalkForwardV2Request(auto_folds=spec))
    assert len(plan.folds) == 3
    for i, (f, b) in enumerate(zip(plan.folds, plan.boundaries, strict=True)):
        assert f.train_start < f.train_end < f.test_start < f.test_end
        assert (b.train_sessions, b.test_sessions, b.embargo_sessions_actual) == (60, 40, 2)
        assert b.warmup_sessions_before_train == 60 + 40 * i
        if i:
            prev = plan.folds[i - 1]
            assert f.train_start > prev.train_start and f.train_end > prev.train_end
            assert f.test_start > prev.test_end  # disjoint, increasing test windows
    # 260 sessions, last complete test window ends at index 241: 18 trailing sessions reported, none shortened
    assert plan.fold_generation["dropped_trailing_sessions"] == 18
    assert any("18 trailing session" in w for w in plan.warnings)
    assert plan.folds[-1].test_end == bar_date(241)


def test_auto_folds_expanding_keeps_train_start_and_grows(market):
    spec = WalkForwardAutoFoldSpec(mode="expanding", train_sessions=60, embargo_sessions=2, test_sessions=40, step_sessions=40)
    plan = plan_walk_forward(make_cfg(), WalkForwardV2Request(auto_folds=spec))
    assert len({f.train_start for f in plan.folds}) == 1
    assert [b.train_sessions for b in plan.boundaries] == [60, 100, 140]


def test_auto_folds_insufficient_history_rejected_with_counts(market):
    spec = WalkForwardAutoFoldSpec(train_sessions=200, test_sessions=40)
    with pytest.raises(WalkForwardValidationError, match="Insufficient history"):
        plan_walk_forward(make_cfg(), WalkForwardV2Request(auto_folds=spec))


def test_auto_step_smaller_than_test_rejected():
    cal = SESSIONS
    spec = WalkForwardAutoFoldSpec(train_sessions=60, test_sessions=40, step_sessions=10)
    with pytest.raises(WalkForwardValidationError, match="step_sessions"):
        generate_auto_folds(cal, spec, overall_start=cal[0], overall_end=cal[-1])


def test_explicit_folds_are_planned_with_boundaries(market):
    plan = plan_walk_forward(make_cfg(), req([FOLD1, FOLD2]))
    assert [b.embargo_sessions_actual for b in plan.boundaries] == [2, 2]
    assert plan.labels == ["f1", "f2"]
    assert plan.fold_generation["source"] == "explicit"


@pytest.mark.parametrize(
    "bad, match",
    [
        (fold(80, 139, 139, 181), "train_start < train_end < test_start < test_end"),
        (fold(139, 80, 142, 181), "train_start < train_end < test_start < test_end"),
    ],
)
def test_invalid_fold_chronology_rejected(market, bad, match):
    with pytest.raises(WalkForwardValidationError, match=match):
        plan_walk_forward(make_cfg(), req([bad]))


def test_minimum_sessions_per_segment_enforced(market):
    assert bar_date(84).weekday() == 4  # a Friday: Friday..Saturday spans exactly one session
    sat = timedelta(days=1)
    one_session_train = WalkForwardFoldInput(
        train_start=bar_date(84), train_end=bar_date(84) + sat, test_start=bar_date(142), test_end=bar_date(181)
    )
    with pytest.raises(WalkForwardValidationError, match="training window has 1 tradable sessions"):
        plan_walk_forward(make_cfg(), req([one_session_train]))
    one_session_test = WalkForwardFoldInput(
        train_start=bar_date(80), train_end=bar_date(139), test_start=bar_date(184), test_end=bar_date(184) + sat
    )
    with pytest.raises(WalkForwardValidationError, match="test window has 1 tradable sessions"):
        plan_walk_forward(make_cfg(), req([one_session_test]))
    plan = plan_walk_forward(make_cfg(), req([fold(80, 139, 142, 143)]))  # exactly 2 sessions is the minimum
    assert plan.boundaries[0].test_sessions == 2


def test_insufficient_warmup_rejected_and_partial_warmup_warned(market):
    with pytest.raises(WalkForwardValidationError, match="history precede train_start"):
        plan_walk_forward(make_cfg(), req([fold(30, 89, 92, 131)]))
    plan = plan_walk_forward(make_cfg(), req([FOLD1]))
    assert any("warm-up" in w for w in plan.warnings)  # 80 < 252


def test_embargo_requirement_counts_sessions_not_calendar_days(market):
    with pytest.raises(WalkForwardValidationError, match="embargo is 2 complete tradable sessions"):
        plan_walk_forward(make_cfg(), req([FOLD1], min_embargo_sessions=5))
    ok = plan_walk_forward(make_cfg(), req([FOLD1], min_embargo_sessions=2))
    assert ok.boundaries[0].embargo_sessions_actual == 2


def test_embargo_uses_the_session_calendar_across_weekends_and_holidays():
    cal = [d for d in SESSIONS if d != date(2023, 3, 1)]  # a removed session is not an embargo session
    fri = date(2023, 2, 24)
    mon = date(2023, 2, 27)
    assert wf2._sessions_strictly_between(cal, fri, mon) == 0  # 3 calendar days, zero sessions
    assert wf2._sessions_strictly_between(cal, date(2023, 2, 27), date(2023, 3, 3)) == 2  # Tue, Thu (no Mar 1)
    assert wf2._sessions_strictly_between(SESSIONS, date(2023, 2, 27), date(2023, 3, 3)) == 3
    f = WalkForwardFoldInput(train_start=cal[80], train_end=cal[139], test_start=cal[140], test_end=cal[179])
    bounds, _ = validate_folds([f], cal, min_embargo_sessions=0)
    assert bounds[0].embargo_sessions_actual == 0


def test_incomplete_trailing_window_is_rejected_not_shortened(market):
    beyond = WalkForwardFoldInput(
        train_start=bar_date(80), train_end=bar_date(139), test_start=bar_date(142), test_end=bar_date(N - 1) + timedelta(days=30)
    )
    with pytest.raises(WalkForwardValidationError, match="incomplete trailing windows are rejected"):
        plan_walk_forward(make_cfg(end_date=bar_date(N - 1) + timedelta(days=30)), req([beyond]))


def test_overlapping_or_reordered_folds_rejected(market):
    overlap = fold(130, 189, 192, 200)  # test window 192..200 sits inside the previous 182..221 range
    with pytest.raises(WalkForwardValidationError, match="overlaps the previous fold's test window"):
        plan_walk_forward(make_cfg(), req([FOLD2, overlap]))
    with pytest.raises(WalkForwardValidationError, match="train_start must not precede"):
        plan_walk_forward(make_cfg(), req([FOLD2, FOLD1]))
    with pytest.raises(WalkForwardValidationError, match="train_end must be after"):
        plan_walk_forward(make_cfg(), req([FOLD2, fold(130, 150, 152, 175, "f3")]))
    with pytest.raises(WalkForwardValidationError, match="labels must be unique"):
        plan_walk_forward(make_cfg(), req([FOLD2, fold(150, 199, 222, 241, "f2")]))


def test_request_requires_exactly_one_fold_source():
    with pytest.raises(ValidationError):
        WalkForwardV2Request()
    with pytest.raises(ValidationError):
        WalkForwardV2Request(folds=[FOLD1], auto_folds=WalkForwardAutoFoldSpec())
    with pytest.raises(ValidationError):
        WalkForwardSelectionSpec(mode="grid_search")
    with pytest.raises(ValidationError):
        WalkForwardGrid(hold_days=[2])  # outside 4..120
    with pytest.raises(ValidationError):
        WalkForwardGrid()


# --------------------------------------------------------------------------- candidates, dedupe, hash


def test_candidates_dedupe_by_effective_config_and_warn_on_nonbinding_scores():
    base = make_cfg(hold_days=10, min_signal_score=0, max_positions=5)
    spec = WalkForwardSelectionSpec(
        mode="grid_search", grid=WalkForwardGrid(hold_days=[10, 20], min_signal_score=[0, 75, 80])
    )
    cands_, dropped, warnings = build_candidates(base, spec)
    assert [c.is_base for c in cands_] == [True, False, False, False]
    assert [(c.hold_days, c.min_signal_score) for c in cands_] == [(10, 0), (10, 80), (20, 0), (20, 80)]
    assert len(dropped) == 3 and all(d["reason"] == "equivalent effective configuration" for d in dropped)
    assert any("min_signal_score=0" in w for w in warnings) and any("min_signal_score=75" in w for w in warnings)
    # deterministic: same input, same order and same drops
    assert build_candidates(base, spec)[0] == cands_


def test_candidate_limit_counts_base_and_dedupes_first():
    base = make_cfg()
    ok = WalkForwardGrid(hold_days=list(range(10, 21)), min_signal_score=[80])  # 11 + base = 12
    assert len(build_candidates(base, WalkForwardSelectionSpec(mode="grid_search", grid=ok))[0]) == 12
    too_many = WalkForwardGrid(hold_days=list(range(10, 22)), min_signal_score=[80])  # 12 + base = 13
    with pytest.raises(WalkForwardValidationError, match="exceed the limit of 12"):
        build_candidates(base, WalkForwardSelectionSpec(mode="grid_search", grid=too_many))


def test_hash_ignores_segment_fields_and_equivalent_knobs_but_covers_everything_else(monkeypatch):
    a = make_cfg(min_signal_score=0, hold_days=None)
    assert effective_config_hash(a) == effective_config_hash(
        make_cfg(name="other", start_date=bar_date(5), end_date=bar_date(50), min_signal_score=75, hold_days=10)
    )
    assert effective_config_hash(make_cfg(hold_days=None, horizon="positional")) == effective_config_hash(
        make_cfg(hold_days=60, horizon="positional")
    )
    for change in (
        dict(hold_days=11),
        dict(min_signal_score=80),
        dict(max_positions=3),
        dict(cost_scenario=CostScenario.REALISTIC),
        dict(slippage_bps=25),
        dict(max_adv_participation=Decimal("0.07")),  # not tuned, still part of the effective config
        dict(shariah_mode=ShariahBacktestMode.STRICT),
        dict(symbols=["AAA"]),
        dict(random_seed=7),
    ):
        assert effective_config_hash(make_cfg(**change)) != effective_config_hash(make_cfg(hold_days=8)), change
    before = effective_config_hash(make_cfg())
    monkeypatch.setattr(wf2, "DEFAULT_WEIGHTS", replace(DEFAULT_WEIGHTS, momentum_quality=24, trend_quality=21))
    assert effective_config_hash(make_cfg()) != before  # global scoring context is part of the hash


# --------------------------------------------------------------------------- selection (pure, training metrics only)


def test_selection_picks_best_training_objective_and_reports_ranking():
    spec = WalkForwardSelectionSpec(mode="grid_search", objective="sharpe", grid=WalkForwardGrid(hold_days=[5, 6, 7]))
    ms = [metrics(sharpe="0.5"), metrics(sharpe="1.4"), metrics(sharpe="0.9"), metrics(sharpe="1.1")]
    reports, sel = evaluate_candidates(cands(4), ["h0", "h1", "h2", "h3"], ms, spec, "swing", [])
    assert sel.status == "selected_on_train" and sel.tuned and not sel.no_candidate_qualified
    assert sel.selected_candidate_index == 1 and sel.selected_config_hash == "h1"
    assert sel.ranking == [1, 3, 2, 0]
    assert [r.eligible for r in reports] == [True] * 4


def test_selection_tie_breaks_deterministically():
    spec = WalkForwardSelectionSpec(mode="grid_search", grid=WalkForwardGrid(hold_days=[5, 6, 7]))
    # equal sharpe: higher total_return, then lower drawdown, then lower candidate index
    ms = [
        metrics(sharpe="1.0", ret="0.10", dd="0.05"),
        metrics(sharpe="1.0", ret="0.12", dd="0.09"),
        metrics(sharpe="1.0", ret="0.12", dd="0.04"),
        metrics(sharpe="1.0", ret="0.12", dd="0.04"),
    ]
    _, sel = evaluate_candidates(cands(4), list("abcd"), ms, spec, "swing", [])
    assert sel.ranking == [2, 3, 1, 0]
    assert sel.selected_candidate_index == 2
    again = evaluate_candidates(cands(4), list("abcd"), ms, spec, "swing", [])[1]
    assert again.ranking == sel.ranking


def test_selection_excludes_candidates_below_min_train_trades_and_undefined_objective():
    spec = WalkForwardSelectionSpec(mode="grid_search", min_train_trades=3, grid=WalkForwardGrid(hold_days=[5, 6, 7]))
    ms = [metrics(sharpe="0.5", trades=5), metrics(sharpe="9.9", trades=2), metrics(sharpe=None, trades=8), metrics(sharpe="0.7", trades=3)]
    reports, sel = evaluate_candidates(cands(4), list("abcd"), ms, spec, "swing", [])
    assert [r.eligible for r in reports] == [True, False, False, True]
    assert "min_train_trades" in (reports[1].ineligible_reason or "")
    assert "undefined" in (reports[2].ineligible_reason or "")
    assert sel.selected_candidate_index == 3


def test_selection_fallback_is_base_not_tuned_and_explicit():
    spec = WalkForwardSelectionSpec(mode="grid_search", min_train_trades=3, grid=WalkForwardGrid(hold_days=[5, 6]))
    ms = [metrics(trades=1), metrics(trades=2), metrics(trades=0)]
    _, sel = evaluate_candidates(cands(3), list("abc"), ms, spec, "swing", [])
    assert sel.status == "fallback_no_candidate_qualified"
    assert sel.no_candidate_qualified and not sel.tuned
    assert sel.selected_candidate_index == 0 and sel.ranking == []
    assert any("NOT tuned" in w for w in sel.warnings)


def test_selection_warns_below_ten_training_trades_and_not_above():
    spec = WalkForwardSelectionSpec(mode="grid_search", grid=WalkForwardGrid(hold_days=[5]))
    _, low = evaluate_candidates(cands(2), ["a", "b"], [metrics(sharpe="0.1", trades=4), metrics(sharpe="2", trades=9)], spec, "swing", [])
    assert any("only 9 training trade" in w for w in low.warnings)
    _, high = evaluate_candidates(cands(2), ["a", "b"], [metrics(trades=12), metrics(sharpe="2", trades=10)], spec, "swing", [])
    assert not any("training trade" in w for w in high.warnings)


def test_selection_fixed_and_single_candidate_statuses():
    fixed = WalkForwardSelectionSpec()
    _, sel = evaluate_candidates(cands(1), ["a"], [metrics(trades=1)], fixed, "swing", [])
    assert sel.status == "fixed_config" and not sel.tuned and not sel.no_candidate_qualified
    grid1 = WalkForwardSelectionSpec(mode="grid_search", grid=WalkForwardGrid(hold_days=[10]))
    _, sel1 = evaluate_candidates(cands(1), ["a"], [metrics()], grid1, "swing", [])
    assert sel1.status == "single_candidate_no_selection" and not sel1.tuned


def test_return_over_drawdown_objective_orders_zero_drawdown_first():
    spec = WalkForwardSelectionSpec(
        mode="grid_search", objective="return_over_max_drawdown", grid=WalkForwardGrid(hold_days=[5, 6])
    )
    ms = [metrics(ret="0.10", dd="0.02"), metrics(ret="0.03", dd="0"), metrics(ret="0.20", dd="0.05")]
    reports, sel = evaluate_candidates(cands(3), list("abc"), ms, spec, "swing", [])
    assert sel.ranking == [1, 0, 2]  # zero-drawdown gain, then 5.0, then 4.0
    assert reports[1].objective_value is None


# --------------------------------------------------------------------------- run budget


def test_run_budget_is_counted_per_invocation_and_enforced_before_any_run(market, monkeypatch):
    calls: list = []
    monkeypatch.setattr(wf2, "run_backtest", lambda cfg: calls.append(cfg) or pytest.fail("no run may start"))
    twelve = WalkForwardSelectionSpec(mode="grid_search", grid=WalkForwardGrid(hold_days=list(range(10, 21)), min_signal_score=[80]))
    # 1 fold x (12 candidates + 1 test run) = 13 runs: allowed
    plan = plan_walk_forward(make_cfg(), req([FOLD1], twelve))
    assert len(plan.candidates) == 12 and plan.planned_runs == 13
    # 2 folds x 13 = 26 > 24: rejected at planning time, before any run
    with pytest.raises(WalkForwardValidationError, match="Run budget exceeded.*= 26"):
        plan_walk_forward(make_cfg(), req([FOLD1, FOLD2], twelve))
    eleven = WalkForwardSelectionSpec(mode="grid_search", grid=WalkForwardGrid(hold_days=list(range(10, 20)), min_signal_score=[80]))
    exact = plan_walk_forward(make_cfg(), req([FOLD1, FOLD2], eleven))  # 2 x (11 + 1) = 24 == limit
    assert exact.planned_runs == MAX_SEGMENT_RUNS == 24
    assert calls == []


def test_fixed_mode_fold_costs_two_runs_and_executed_equals_planned(market, monkeypatch):
    seen: list = []

    def counting(cfg):
        seen.append(cfg)
        return run_backtest(cfg)

    out = execute_plan(plan_walk_forward(make_cfg(), req([FOLD1, FOLD2])), runner=counting)
    assert out.run_budget.planned == 4 and out.run_budget.executed == 4 == len(seen)
    assert out.run_budget.max == 24


def test_grid_run_count_includes_every_candidate_and_test_run(market):
    seen: list = []

    def counting(cfg):
        seen.append(cfg)
        return run_backtest(cfg)

    plan = plan_walk_forward(make_cfg(), req([FOLD1, FOLD2], GRID_SEL))
    assert len(plan.candidates) == 5 and plan.planned_runs == 12
    out = execute_plan(plan, runner=counting)
    assert len(seen) == out.run_budget.executed == out.run_budget.planned == 12


def test_engine_refuses_runs_beyond_the_planned_budget(market):
    plan = plan_walk_forward(make_cfg(), req([FOLD1]))
    object.__setattr__(plan, "planned_runs", 1)
    with pytest.raises(WalkForwardIntegrityError, match="run budget exhausted"):
        execute_plan(plan)


def test_api_rejects_over_budget_before_running_anything(market, monkeypatch):
    from app.main import app

    ran: list = []
    monkeypatch.setattr(wf2, "run_backtest", lambda cfg: ran.append(cfg))
    body = {
        "base_config": make_cfg().model_dump(mode="json"),
        "folds": [f.model_dump(mode="json") for f in (FOLD1, FOLD2)],
        "selection": {
            "mode": "grid_search",
            "grid": {"hold_days": list(range(10, 21)), "min_signal_score": [80]},
        },
    }
    res = TestClient(app).post("/api/v2/backtests/walk-forward", json=body)
    assert res.status_code == 400 and "Run budget exceeded" in res.json()["detail"]
    assert ran == []


# --------------------------------------------------------------------------- segment isolation


def test_every_segment_gets_a_fresh_simbook_and_fresh_breadth_scope(market, monkeypatch):
    books: list = []
    real_book = simulator.SimBook

    class TrackingBook(real_book):
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            books.append(self)
            self.initial_cash = self.cash

    monkeypatch.setattr(simulator, "SimBook", TrackingBook)
    scopes: list = []
    real_scope = market_breadth.breadth_cache_scope

    @contextmanager
    def tracking_scope():
        outer_active = market_breadth._SCOPED_CACHE.get() is not None
        with real_scope():
            memo = market_breadth._SCOPED_CACHE.get()
            scopes.append((outer_active, dict(memo), memo))
            yield

    monkeypatch.setattr(simulator, "breadth_cache_scope", tracking_scope)

    out = execute_plan(plan_walk_forward(make_cfg(), req([FOLD1, FOLD2], GRID_SEL)))
    runs = out.run_budget.executed
    assert len(books) == len(scopes) == runs == 12
    assert all(b.initial_cash == D(100000) for b in books)
    assert len({id(b) for b in books}) == runs
    assert all(not outer and start == {} for outer, start, _ in scopes)  # never nested, always empty at entry
    memos = [m for _, _, m in scopes]
    assert all(memos[i] is not memos[j] for i in range(runs) for j in range(i + 1, runs))
    assert market_breadth._SCOPED_CACHE.get() is None  # nothing leaks out of the last run
    for f in out.folds:  # no holdings or cash carried into any segment
        for seg in (f.train_result, f.test_result):
            assert seg.equity_points >= 2
    full = execute_plan(plan_walk_forward(make_cfg(), req([FOLD1, FOLD2], include_segment_curves=True)))
    for f in full.folds:
        for seg in (f.train_result, f.test_result):
            first = seg.equity_curve[0]
            assert first.equity == D(100000) and first.invested == D(0)


def test_engine_refuses_to_run_inside_an_active_breadth_scope(market):
    plan = plan_walk_forward(make_cfg(), req([FOLD1]))
    with market_breadth.breadth_cache_scope(), pytest.raises(WalkForwardIntegrityError, match="active breadth-cache scope"):
        execute_plan(plan)


def test_segment_windows_are_exact_and_warmup_never_trades(market, monkeypatch):
    calls: list = []
    install_stub(monkeypatch, calls)
    out = execute_plan(plan_walk_forward(make_cfg(), req([FOLD1], include_segment_curves=True)))
    f = out.folds[0]
    for seg, (s, e) in ((f.train_result, (FOLD1.train_start, FOLD1.train_end)), (f.test_result, (FOLD1.test_start, FOLD1.test_end))):
        assert seg.equity_curve[0].date == s and seg.equity_curve[-1].date == e
        assert all(s <= p.date <= e for p in seg.equity_curve)
        assert all(s <= t.entry_date and (t.exit_date or t.entry_date) <= e for t in seg.trades)
        assert seg.equity_points == (f.boundaries.train_sessions if seg.segment == "train" else f.boundaries.test_sessions)
        assert seg.metrics.total_trades == len(seg.trades)
    # signals are only evaluated on sessions inside the evaluated segments, yet see the full as-of history
    test_calls = [c for c in calls if FOLD1.test_start <= c[1] <= FOLD1.test_end]
    assert test_calls and min(n for _, _, n in test_calls) >= SESSIONS.index(FOLD1.test_start) + 1
    assert not any(FOLD1.train_end < d < FOLD1.test_start for _, d, _ in calls)  # embargo sessions are never simulated
    assert not any(d < FOLD1.train_start for _, d, _ in calls)  # warm-up sessions are never simulated
    assert not any(d > FOLD1.test_end for _, d, _ in calls)


def test_segment_metrics_equal_a_standalone_run_of_the_same_window(market):
    out = execute_plan(plan_walk_forward(make_cfg(), req([FOLD1])))
    f = out.folds[0]
    solo_train = run_backtest(make_cfg(start_date=FOLD1.train_start, end_date=FOLD1.train_end))
    solo_test = run_backtest(make_cfg(start_date=FOLD1.test_start, end_date=FOLD1.test_end))
    assert f.train_result.metrics.model_dump() == solo_train.metrics.model_dump()
    assert f.test_result.metrics.model_dump() == solo_test.metrics.model_dump()
    assert f.test_result.trade_count == len(solo_test.trades)


def test_a_failed_segment_run_fails_closed(market):
    def failing(cfg):
        return BacktestRun(config=cfg, status=BacktestStatus.FAILED)

    with pytest.raises(WalkForwardValidationError, match="did not complete"):
        execute_plan(plan_walk_forward(make_cfg(), req([FOLD1])), runner=failing)


def test_out_of_window_trade_or_equity_point_fails_closed(market):
    def leaky(cfg):
        run = run_backtest(cfg)
        run.equity_curve.append(EquityPoint(date=cfg.end_date + timedelta(days=1), equity=D(1), cash=D(1), invested=D(0)))
        return run

    with pytest.raises(WalkForwardIntegrityError, match="outside segment"):
        execute_plan(plan_walk_forward(make_cfg(), req([FOLD1])), runner=leaky)


# --------------------------------------------------------------------------- selection happens before the test run


def test_selected_hash_is_logged_before_the_test_segment_runs(market):
    timeline: list = []

    def spy_run(cfg):
        timeline.append(("run", cfg.start_date, cfg.end_date, effective_config_hash(cfg)))
        return run_backtest(cfg)

    out = execute_plan(
        plan_walk_forward(make_cfg(), req([FOLD1, FOLD2], GRID_SEL)),
        runner=spy_run,
        on_event=lambda e: timeline.append(("event", e["event"], e.get("selected_config_hash"), e.get("fold_index"))),
    )
    for k, fr in enumerate(out.folds):
        frozen_pos = next(i for i, t in enumerate(timeline) if t[:2] == ("event", "selection_frozen") and t[3] == k)
        test_pos = next(
            i
            for i, t in enumerate(timeline)
            if t[0] == "run" and (t[1], t[2]) == (fr.boundaries.test_start, fr.boundaries.test_end)
        )
        assert frozen_pos < test_pos
        assert timeline[frozen_pos][2] == fr.selection.selected_config_hash == timeline[test_pos][3] == fr.test_result.config_hash
        # no train run of any later fold happens between freezing and testing: test is the next run after freezing
        assert test_pos == frozen_pos + 2  # frozen, test_run event, then the run itself
    assert [e["event"] for e in out.run_log if e["fold_index"] == 0][-3:] == ["train_run", "selection_frozen", "test_run"]


# --------------------------------------------------------------------------- leakage mutation proof-tests


def _fingerprint(out):
    f = out.folds[0]
    return {
        "candidate_train_metrics": [c.train_metrics.model_dump(mode="json") for c in f.candidates],
        "candidate_hashes": [c.config_hash for c in f.candidates],
        "ranking": f.selection.ranking,
        "selected_params": f.selection.selected_params,
        "selected_hash": f.selection.selected_config_hash,
        "status": f.selection.status,
        "train_equity": f.train_result.equity_sha256,
        "train_trades": [t.model_dump(mode="json") for t in f.train_result.trades],
    }


def test_test_window_price_corruption_cannot_change_training_or_selection(monkeypatch):
    install_stub(monkeypatch)
    install_market(monkeypatch)
    clean = execute_plan(plan_walk_forward(make_cfg(), req([FOLD1], GRID_SEL)))
    install_market(monkeypatch, corrupt_from=FOLD1.test_start)  # every bar from test_start onward is corrupted
    corrupted = execute_plan(plan_walk_forward(make_cfg(), req([FOLD1], GRID_SEL)))
    assert _fingerprint(clean) == _fingerprint(corrupted)
    assert clean.folds[0].selection.tuned  # a genuine selection took place
    # sanity: the corruption is real and does reach the test segment
    assert clean.folds[0].test_result.equity_sha256 != corrupted.folds[0].test_result.equity_sha256


def test_prices_after_the_test_window_change_nothing_at_all(monkeypatch):
    install_stub(monkeypatch)
    install_market(monkeypatch)
    clean = execute_plan(plan_walk_forward(make_cfg(), req([FOLD1], GRID_SEL)))
    install_market(monkeypatch, corrupt_from=FOLD1.test_end + timedelta(days=1))
    corrupted = execute_plan(plan_walk_forward(make_cfg(), req([FOLD1], GRID_SEL)))
    assert _fingerprint(clean) == _fingerprint(corrupted)
    assert clean.folds[0].test_result.equity_sha256 == corrupted.folds[0].test_result.equity_sha256
    assert clean.oos_summary.oos_equity_sha256 == corrupted.oos_summary.oos_equity_sha256


def test_later_fold_test_corruption_leaves_earlier_folds_unchanged(monkeypatch):
    """Corrupting bars from fold 2's test window onward leaves fold 1 and fold 2's training untouched."""
    install_stub(monkeypatch)
    install_market(monkeypatch)
    clean = execute_plan(plan_walk_forward(make_cfg(), req([FOLD1, FOLD2], GRID_SEL)))
    install_market(monkeypatch, corrupt_from=FOLD2.test_start)
    corrupted = execute_plan(plan_walk_forward(make_cfg(), req([FOLD1, FOLD2], GRID_SEL)))
    a, b = clean.folds[0], corrupted.folds[0]
    assert a.test_result.equity_sha256 == b.test_result.equity_sha256
    assert a.selection.selected_config_hash == b.selection.selected_config_hash
    assert clean.folds[1].train_result.equity_sha256 == corrupted.folds[1].train_result.equity_sha256


def test_selection_function_signature_admits_training_data_only():
    import inspect

    params = set(inspect.signature(evaluate_candidates).parameters)
    assert params == {"candidates", "candidate_hashes", "train_metrics", "spec", "horizon", "deduplicated"}


# --------------------------------------------------------------------------- OOS aggregation


def test_oos_summary_is_built_from_test_segments_only(market):
    out = execute_plan(plan_walk_forward(make_cfg(), req([FOLD1, FOLD2], GRID_SEL, include_segment_curves=True)))
    oos = out.oos_summary
    test_trades = [t for f in out.folds for t in f.test_result.trades]
    train_trades = [t for f in out.folds for t in f.train_result.trades]
    assert [t.model_dump() for t in oos.oos_trades] == [t.model_dump() for t in test_trades]
    assert oos.oos_metrics.total_trades == len(test_trades) == sum(f.test_result.metrics.total_trades for f in out.folds)
    assert len(train_trades) > 0
    test_dates = [p.date for f in out.folds for p in f.test_result.equity_curve]
    assert [p.date for p in oos.oos_equity_curve] == test_dates
    assert len(oos.oos_equity_curve) == oos.total_test_sessions == 80
    assert oos.scope == "stitched_test_windows_only"
    assert all(FOLD1.test_start <= t.entry_date for t in oos.oos_trades)
    assert oos.fold_count == 2 and len(oos.fold_test_returns) == 2


def test_stitch_chains_fold_returns_multiplicatively_with_fresh_start_per_fold():
    cfg = make_cfg()
    d = [bar_date(i) for i in range(6)]

    def fold_run(values, offset):
        # each fold starts from a fresh book at 100000, as the engine guarantees
        curve = [EquityPoint(date=d[offset + i], equity=D(v), cash=D(v), invested=D(0)) for i, v in enumerate(values)]
        m = compute_metrics(curve, [], D(100000), benchmark_return=None, stats={})
        return BacktestRun(config=cfg, status=BacktestStatus.COMPLETED, metrics=m, equity_curve=curve)

    curve, trades, m = stitch_oos([fold_run([100000, 110000], 0), fold_run([100000, 90000, 99000], 2)], D(100000))
    assert [p.equity for p in curve] == [D(100000), D(110000), D(110000), D(99000), D(108900)]
    assert trades == []
    assert m.final_capital == D(108900)
    assert abs(m.max_drawdown - Decimal("0.1")) < Decimal("0.0001")  # 110000 -> 99000


# --------------------------------------------------------------------------- evidence, provenance, reporting


def test_response_reports_boundaries_selection_provenance_and_demo_grade(market):
    out = execute_plan(plan_walk_forward(make_cfg(), req([FOLD1], GRID_SEL)))
    dumped = out.model_dump(mode="json")
    assert dumped["schema_version"] == "2.0"
    assert dumped["evidence_grade"] == "demo"
    assert dumped["data_provenance"]["kind"] == "synthetic"
    assert out.disclosures["survivorship_biased"] and out.disclosures["results_persisted"] is False
    f = dumped["folds"][0]
    assert {"train_start", "train_end", "test_start", "test_end", "embargo_sessions_actual"} <= set(f["boundaries"])
    assert f["selection"]["selected_config_hash"] == f["test_result"]["config_hash"] == f["train_result"]["config_hash"]
    assert f["train_result"]["segment"] == "train" and f["test_result"]["segment"] == "test"
    assert f["train_result"]["trade_count"] == f["train_result"]["metrics"]["total_trades"]
    assert f["test_result"]["evidence_grade"] == "demo"
    text = " ".join(dumped["warnings"])
    for needle in ("B-09", "B-14", "B-10", "B-15", "B-05", "DEMO", "multiple-testing"):
        assert needle in text, needle
    assert "Passing software tests proves the walk-forward machinery, not strategy validity" in text


def test_fallback_is_reported_not_labelled_tuned(market):
    sel = WalkForwardSelectionSpec(
        mode="grid_search", min_train_trades=1000, grid=WalkForwardGrid(hold_days=[5, 10], min_signal_score=[80])
    )
    out = execute_plan(plan_walk_forward(make_cfg(), req([FOLD1], sel)))
    s = out.folds[0].selection
    assert s.status == "fallback_no_candidate_qualified" and not s.tuned and s.no_candidate_qualified
    assert s.selected_candidate_index == 0 and s.selected_params["hold_days"] == 8  # the base configuration
    assert out.disclosures["any_fold_tuned"] is False and out.disclosures["any_fold_fell_back_to_base"] is True
    assert any("fell back to base_config" in w for w in out.warnings)


def test_grid_selection_runs_end_to_end_and_selected_matches_ranking_head(market):
    out = execute_plan(plan_walk_forward(make_cfg(), req([FOLD1], GRID_SEL)))
    s = out.folds[0].selection
    assert s.status == "selected_on_train" and s.tuned
    assert s.selected_candidate_index == s.ranking[0]
    ordered = [out.folds[0].candidates[i].objective_value for i in s.ranking]
    assert ordered == sorted(ordered, reverse=True)


def test_walk_forward_is_deterministic_across_repeated_runs(monkeypatch):
    install_stub(monkeypatch)
    install_market(monkeypatch)
    one = execute_plan(plan_walk_forward(make_cfg(), req([FOLD1, FOLD2], GRID_SEL)))
    install_market(monkeypatch)
    two = execute_plan(plan_walk_forward(make_cfg(), req([FOLD1, FOLD2], GRID_SEL)))
    assert one.model_dump(mode="json") == two.model_dump(mode="json")


# --------------------------------------------------------------------------- v1 compatibility and API


def test_v1_walk_forward_behaviour_is_unchanged(market):
    cfg = make_cfg()
    out = walk_forward_v1(
        cfg,
        [
            {
                "label": "a",
                "train_start": FOLD1.train_start.isoformat(),
                "train_end": FOLD1.train_end.isoformat(),
                "test_end": FOLD1.test_end.isoformat(),
            }
        ],
    )
    assert set(out) == {"folds", "notice"} and out["notice"] == "Out-of-sample segments embedded per fold end_date"
    blended = run_backtest(make_cfg(start_date=FOLD1.train_start, end_date=FOLD1.test_end))
    assert out["folds"][0]["metrics"] == blended.metrics.model_dump(mode="json")
    assert set(out["folds"][0]) == {"fold", "metrics", "status"}


def test_v1_endpoint_still_served_and_v2_is_additive(market):
    from app.main import app

    paths = set(app.openapi()["paths"])
    assert "/api/v1/backtests/{backtest_id}/walk-forward" in paths
    assert "/api/v2/backtests/{backtest_id}/walk-forward" in paths
    assert "/api/v2/backtests/walk-forward" in paths
    client = TestClient(app)
    created = client.post("/api/v1/backtests", json=make_cfg().model_dump(mode="json")).json()
    bid = created["backtest_id"]
    v1 = client.post(
        f"/api/v1/backtests/{bid}/walk-forward",
        json={"folds": [{"train_start": FOLD1.train_start.isoformat(), "test_end": FOLD1.test_end.isoformat()}]},
    )
    assert v1.status_code == 200 and "notice" in v1.json() and "oos_summary" not in v1.json()

    v2 = client.post(
        f"/api/v2/backtests/{bid}/walk-forward",
        json={"folds": [FOLD1.model_dump(mode="json")], "selection": {"mode": "grid_search", "grid": {"hold_days": [5, 20]}}},
    )
    assert v2.status_code == 200, v2.text
    body = v2.json()
    assert body["schema_version"] == "2.0" and body["run_budget"] == {"max": 24, "planned": 4, "executed": 4}
    assert client.post("/api/v2/backtests/999999/walk-forward", json={"folds": [FOLD1.model_dump(mode="json")]}).status_code == 404


def test_v2_stateless_endpoint_and_validation_errors(market):
    from app.main import app

    client = TestClient(app)
    ok = client.post(
        "/api/v2/backtests/walk-forward",
        json={
            "base_config": make_cfg().model_dump(mode="json"),
            "auto_folds": {"train_sessions": 60, "embargo_sessions": 2, "test_sessions": 40, "step_sessions": 40},
        },
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["run_budget"]["planned"] == 6 and len(ok.json()["folds"]) == 3
    bad_fold = client.post(
        "/api/v2/backtests/walk-forward",
        json={"base_config": make_cfg().model_dump(mode="json"), "folds": [fold(80, 139, 139, 181).model_dump(mode="json")]},
    )
    assert bad_fold.status_code == 400
    bad_shape = client.post(
        "/api/v2/backtests/walk-forward", json={"base_config": make_cfg().model_dump(mode="json")}
    )
    assert bad_shape.status_code == 422
