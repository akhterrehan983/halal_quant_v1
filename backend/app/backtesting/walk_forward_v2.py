"""Walk-forward v2 (M14 Phase 2): training-only parameter selection, independent test segments.

Design rules (see ``docs/m14_phase2_plan.md``, sections 0 and 5):

* Every segment is one independent ``run_backtest`` call over exactly ``[segment_start, segment_end]``. Bars before the
  segment start are only indicator history. Each call builds a fresh ``SimBook`` and breadth-cache scope, so no cash,
  holdings, pending orders, delayed stops, or caches carry between segments.
* Candidate selection (``evaluate_candidates``) receives training runs only. Test-window data cannot reach it.
* The selected configuration is hashed and logged before the test segment runs.
* Out-of-sample metrics, trades, and the chained equity curve are built from test segments only.
* Every ``run_backtest`` call counts toward ``MAX_SEGMENT_RUNS``; the budget is enforced before any run starts.

Nothing here persists results or touches the live portfolio.
"""

from __future__ import annotations

import hashlib
import json
from bisect import bisect_left, bisect_right
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import date
from decimal import Decimal
from itertools import product

import pandas as pd

from app.backtesting.metrics import compute_metrics
from app.backtesting.schemas import (
    BacktestConfig,
    BacktestMetrics,
    BacktestRun,
    BacktestStatus,
    CompletedTrade,
    CostScenario,
    DataProvenance,
    EquityPoint,
    EvidenceGrade,
)
from app.backtesting.simulator import (
    COVERAGE_GAP_DAYS,
    MIN_SIGNAL_BARS,
    SIGNAL_LOOKBACK_BARS,
    run_backtest,
)
from app.backtesting.universe import universe_for_backtest
from app.backtesting.walk_forward_schemas import (
    LOW_TRAIN_TRADES_WARNING,
    MAX_CANDIDATES_PER_FOLD,
    MAX_SEGMENT_RUNS,
    MIN_SEGMENT_SESSIONS,
    MIN_WARMUP_SESSIONS,
    PARTIAL_WARMUP_SESSIONS,
    SCHEMA_VERSION,
    CandidateReport,
    FoldBoundaries,
    FoldResult,
    OOSSummary,
    RunBudget,
    SegmentResult,
    SelectionReport,
    WalkForwardAutoFoldSpec,
    WalkForwardFoldInput,
    WalkForwardSelectionSpec,
    WalkForwardV2Request,
    WalkForwardV2Response,
)
from app.market_data import repository as repo
from app.market_data.benchmarks import benchmark_symbols
from app.portfolio.money import D, money
from app.regime import market_breadth
from app.signals.config import DEFAULT_CATEGORIES, DEFAULT_WEIGHTS
from app.strategies.config import get_horizon_config
from app.strategies.registry import enabled_strategies

CONFIG_HASH_SCHEMA = "wf2-config-v1"
DEFAULT_SWING_HOLD_DAYS = 10  # mirrors simulator.py
DEFAULT_POSITIONAL_HOLD_DAYS = 60


class WalkForwardValidationError(ValueError):
    """Deterministic rejection of an invalid request, fold layout, or run budget (HTTP 400)."""


class WalkForwardIntegrityError(RuntimeError):
    """A leakage or isolation invariant was violated at run time (never expected; fails closed)."""


# --------------------------------------------------------------------------- effective configuration


def effective_min_signal_score(value: int) -> int:
    """Unified signals are BUY only at score >= the BUY threshold, so lower floors behave identically."""
    return max(int(value), DEFAULT_CATEGORIES.buy)


def effective_hold_days(hold_days: int | None, horizon: str) -> int:
    if hold_days is not None:
        return int(hold_days)
    return DEFAULT_SWING_HOLD_DAYS if horizon == "swing" else DEFAULT_POSITIONAL_HOLD_DAYS


def effective_config_payload(config: BacktestConfig) -> dict:
    """The complete effective configuration, excluding only the segment-specific name and dates."""
    body = config.model_dump(mode="json")
    for key in ("name", "start_date", "end_date"):
        body.pop(key, None)
    body["min_signal_score"] = effective_min_signal_score(config.min_signal_score)
    body["hold_days"] = effective_hold_days(config.hold_days, config.horizon)
    if body.get("symbols") is not None:
        body["symbols"] = sorted({s.strip().upper() for s in body["symbols"] if s.strip()})
    context = {
        "schema": CONFIG_HASH_SCHEMA,
        "horizon_config": asdict(get_horizon_config(config.horizon)),
        "scoring_weights": asdict(DEFAULT_WEIGHTS),
        "category_thresholds": asdict(DEFAULT_CATEGORIES),
        "enabled_strategies": sorted(s.strategy_id for s in enabled_strategies()),
        "benchmark_symbols": sorted(benchmark_symbols()),
        "signal_lookback_bars": SIGNAL_LOOKBACK_BARS,
        "min_signal_bars": MIN_SIGNAL_BARS,
    }
    return {"config": body, "context": context}


def effective_config_hash(config: BacktestConfig) -> str:
    payload = json.dumps(effective_config_payload(config), sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------- session calendar


def build_session_calendar(base_config: BacktestConfig, end: date) -> list[date]:
    """Sorted union of trading dates (<= ``end``) over the tradable universe: the simulator's session calendar."""
    _, tradable = universe_for_backtest(base_config.start_date, end, base_config.symbols)
    dates: set[date] = set()
    for sym in tradable:
        try:
            frame = repo.history_upto(sym, end=end)
        except repo.SymbolNotFoundError:
            continue
        if frame is None or frame.empty:
            continue
        dates.update(pd.to_datetime(frame["date"]).dt.date)
    return sorted(dates)


def _sessions_between(calendar: list[date], start: date, end: date) -> int:
    """Complete tradable sessions ``d`` with ``start <= d <= end``."""
    return max(0, bisect_right(calendar, end) - bisect_left(calendar, start))


def _sessions_strictly_between(calendar: list[date], after: date, before: date) -> int:
    """Complete tradable sessions ``d`` with ``after < d < before`` (the embargo definition)."""
    return max(0, bisect_left(calendar, before) - bisect_right(calendar, after))


# --------------------------------------------------------------------------- folds


def generate_auto_folds(
    calendar: list[date],
    spec: WalkForwardAutoFoldSpec,
    *,
    overall_start: date,
    overall_end: date,
) -> tuple[list[WalkForwardFoldInput], dict]:
    """Rolling or expanding folds laid out on session indices. Incomplete trailing windows are reported, not shortened."""
    sessions = [d for d in calendar if d <= overall_end]
    n = len(sessions)
    prior = bisect_left(sessions, overall_start)
    first = max(spec.warmup_sessions, prior)
    step = spec.step_sessions if spec.step_sessions is not None else spec.test_sessions
    if step < spec.test_sessions:
        raise WalkForwardValidationError("step_sessions must be >= test_sessions so test windows stay disjoint")
    if spec.mode == "expanding" and spec.train_sessions < 1:
        raise WalkForwardValidationError("train_sessions must be positive")

    folds: list[WalkForwardFoldInput] = []
    k = 0
    last_test_idx = -1
    while True:
        if spec.mode == "rolling":
            tr_s = first + k * step
            tr_e = tr_s + spec.train_sessions - 1
        else:
            tr_s = first
            tr_e = first + spec.train_sessions - 1 + k * step
        te_s = tr_e + 1 + spec.embargo_sessions
        te_e = te_s + spec.test_sessions - 1
        if te_e >= n:
            break
        folds.append(
            WalkForwardFoldInput(
                label=f"fold_{k + 1}",
                train_start=sessions[tr_s],
                train_end=sessions[tr_e],
                test_start=sessions[te_s],
                test_end=sessions[te_e],
            )
        )
        last_test_idx = te_e
        k += 1
    needed = first + spec.train_sessions + spec.embargo_sessions + spec.test_sessions
    if not folds:
        raise WalkForwardValidationError(
            f"Insufficient history for one complete fold: need {needed} sessions "
            f"({first} warm-up/prior + {spec.train_sessions} train + {spec.embargo_sessions} embargo + "
            f"{spec.test_sessions} test) but only {n} sessions exist up to {overall_end.isoformat()}."
        )
    dropped = n - 1 - last_test_idx
    info = {
        "source": "auto",
        "mode": spec.mode,
        "total_sessions_in_range": n,
        "first_train_session_index": first,
        "train_sessions": spec.train_sessions,
        "embargo_sessions": spec.embargo_sessions,
        "test_sessions": spec.test_sessions,
        "step_sessions": step,
        "dropped_trailing_sessions": dropped,
        "fold_count": len(folds),
    }
    return folds, info


def validate_folds(
    folds: list[WalkForwardFoldInput],
    calendar: list[date],
    *,
    min_embargo_sessions: int,
) -> tuple[list[FoldBoundaries], list[str]]:
    """Reject invalid or insufficient folds deterministically. Never shortens or repairs a fold."""
    if not folds:
        raise WalkForwardValidationError("At least one fold is required")
    if not calendar:
        raise WalkForwardValidationError("No trading sessions with data for the tradable universe")
    labels = [f.label or f"fold_{i + 1}" for i, f in enumerate(folds)]
    if len(set(labels)) != len(labels):
        raise WalkForwardValidationError("Fold labels must be unique")

    boundaries: list[FoldBoundaries] = []
    warnings: list[str] = []
    last_session = calendar[-1]
    for i, (f, label) in enumerate(zip(folds, labels, strict=True)):
        if not (f.train_start < f.train_end < f.test_start < f.test_end):
            raise WalkForwardValidationError(
                f"{label}: require train_start < train_end < test_start < test_end "
                f"(got {f.train_start}, {f.train_end}, {f.test_start}, {f.test_end})"
            )
        train_n = _sessions_between(calendar, f.train_start, f.train_end)
        test_n = _sessions_between(calendar, f.test_start, f.test_end)
        if train_n < MIN_SEGMENT_SESSIONS:
            raise WalkForwardValidationError(
                f"{label}: training window has {train_n} tradable sessions (minimum {MIN_SEGMENT_SESSIONS})"
            )
        if test_n < MIN_SEGMENT_SESSIONS:
            raise WalkForwardValidationError(
                f"{label}: test window has {test_n} tradable sessions (minimum {MIN_SEGMENT_SESSIONS})"
            )
        embargo = _sessions_strictly_between(calendar, f.train_end, f.test_start)
        if embargo < min_embargo_sessions:
            raise WalkForwardValidationError(
                f"{label}: embargo is {embargo} complete tradable sessions between train_end and test_start; "
                f"minimum required is {min_embargo_sessions}"
            )
        if (f.test_end - last_session).days > COVERAGE_GAP_DAYS:
            raise WalkForwardValidationError(
                f"{label}: test window ends {f.test_end.isoformat()} but data end {last_session.isoformat()}; "
                f"incomplete trailing windows are rejected, not shortened"
            )
        warmup = bisect_left(calendar, f.train_start)
        if warmup < MIN_WARMUP_SESSIONS:
            raise WalkForwardValidationError(
                f"{label}: only {warmup} sessions of history precede train_start; "
                f"at least {MIN_WARMUP_SESSIONS} are required for indicators"
            )
        if warmup < PARTIAL_WARMUP_SESSIONS:
            warnings.append(
                f"{label}: only {warmup} sessions of warm-up precede train_start (< {PARTIAL_WARMUP_SESSIONS}); "
                "long-window indicators (e.g. sma200, 52-week high) may be unavailable early in the training window."
            )
        if i > 0:
            prev = folds[i - 1]
            if f.train_start < prev.train_start:
                raise WalkForwardValidationError(f"{label}: train_start must not precede the previous fold's train_start")
            if f.train_end <= prev.train_end:
                raise WalkForwardValidationError(f"{label}: train_end must be after the previous fold's train_end")
            if f.test_start <= prev.test_end:
                raise WalkForwardValidationError(f"{label}: test window overlaps the previous fold's test window")
        boundaries.append(
            FoldBoundaries(
                train_start=f.train_start,
                train_end=f.train_end,
                test_start=f.test_start,
                test_end=f.test_end,
                train_sessions=train_n,
                test_sessions=test_n,
                embargo_sessions_actual=embargo,
                gap_calendar_days=(f.test_start - f.train_end).days,
                warmup_sessions_before_train=warmup,
            )
        )
    return boundaries, warnings


# --------------------------------------------------------------------------- candidates


@dataclass(frozen=True)
class Candidate:
    index: int
    is_base: bool
    hold_days: int | None
    min_signal_score: int
    max_positions: int

    def params(self) -> dict:
        return {
            "hold_days": self.hold_days,
            "min_signal_score": self.min_signal_score,
            "max_positions": self.max_positions,
        }

    def effective_params(self, horizon: str) -> dict:
        return {
            "hold_days": effective_hold_days(self.hold_days, horizon),
            "min_signal_score": effective_min_signal_score(self.min_signal_score),
            "max_positions": self.max_positions,
        }

    def apply(self, base: BacktestConfig, *, name: str, start: date, end: date) -> BacktestConfig:
        return base.model_copy(
            deep=True,
            update={
                "name": name,
                "start_date": start,
                "end_date": end,
                "hold_days": self.hold_days,
                "min_signal_score": self.min_signal_score,
                "max_positions": self.max_positions,
            },
        )


def build_candidates(
    base: BacktestConfig, spec: WalkForwardSelectionSpec
) -> tuple[list[Candidate], list[dict], list[str]]:
    """Base is always candidate 0; grid candidates follow in a fixed order; equivalents are dropped."""
    horizon = base.horizon
    raw: list[tuple[int | None, int, int]] = [(base.hold_days, base.min_signal_score, base.max_positions)]
    if spec.mode == "grid_search" and spec.grid is not None:
        holds = spec.grid.hold_days if spec.grid.hold_days is not None else [base.hold_days]
        scores = spec.grid.min_signal_score if spec.grid.min_signal_score is not None else [base.min_signal_score]
        maxes = spec.grid.max_positions if spec.grid.max_positions is not None else [base.max_positions]
        raw.extend(product(holds, scores, maxes))

    candidates: list[Candidate] = []
    dropped: list[dict] = []
    seen: dict[tuple, int] = {}
    warnings: list[str] = []
    warned_scores: set[int] = set()
    for hold, score, maxp in raw:
        if score <= DEFAULT_CATEGORIES.buy and score not in warned_scores:
            warned_scores.add(score)
            warnings.append(
                f"min_signal_score={score} is <= {DEFAULT_CATEGORIES.buy}: it cannot filter anything because unified "
                f"signals are BUY only at score >= {DEFAULT_CATEGORIES.buy}; effective value is "
                f"{DEFAULT_CATEGORIES.buy}."
            )
        key = (effective_hold_days(hold, horizon), effective_min_signal_score(score), maxp)
        if key in seen:
            dropped.append(
                {
                    "params": {"hold_days": hold, "min_signal_score": score, "max_positions": maxp},
                    "duplicate_of": seen[key],
                    "reason": "equivalent effective configuration",
                }
            )
            continue
        idx = len(candidates)
        seen[key] = idx
        candidates.append(Candidate(idx, idx == 0, hold, score, maxp))
    if len(candidates) > MAX_CANDIDATES_PER_FOLD:
        raise WalkForwardValidationError(
            f"{len(candidates)} distinct candidates per fold exceed the limit of {MAX_CANDIDATES_PER_FOLD} "
            "(the base configuration counts as one)"
        )
    return candidates, dropped, warnings


def planned_run_count(n_folds: int, n_candidates: int) -> int:
    """Every training candidate run plus one test run per fold. Fallback to base needs no extra run."""
    return n_folds * (n_candidates + 1)


def _check_budget(n_folds: int, n_candidates: int) -> int:
    planned = planned_run_count(n_folds, n_candidates)
    if planned > MAX_SEGMENT_RUNS:
        raise WalkForwardValidationError(
            f"Run budget exceeded: {n_folds} fold(s) x ({n_candidates} candidate(s) + 1 test run) = {planned} "
            f"run_backtest calls, limit {MAX_SEGMENT_RUNS}"
        )
    return planned


# --------------------------------------------------------------------------- plan


@dataclass(frozen=True)
class WalkForwardPlan:
    base_config: BacktestConfig
    base_config_hash: str
    selection: WalkForwardSelectionSpec
    folds: list[WalkForwardFoldInput]
    labels: list[str]
    boundaries: list[FoldBoundaries]
    candidates: list[Candidate]
    candidate_hashes: list[str]
    deduplicated: list[dict]
    planned_runs: int
    fold_generation: dict
    warnings: list[str]
    include_segment_curves: bool = False
    calendar_summary: dict = field(default_factory=dict)


def plan_walk_forward(base_config: BacktestConfig, request: WalkForwardV2Request) -> WalkForwardPlan:
    """Validate everything (folds, embargo, warm-up, candidates, run budget) before any simulation runs."""
    try:
        base_config.validate_dates()
    except ValueError as exc:
        raise WalkForwardValidationError(str(exc)) from exc

    candidates, dropped, cand_warnings = build_candidates(base_config, request.selection)

    warnings: list[str] = list(cand_warnings)
    if request.folds is not None:
        _check_budget(len(request.folds), len(candidates))  # cheap check before touching market data
        calendar_end = max(f.test_end for f in request.folds)
        calendar = build_session_calendar(base_config, calendar_end)
        folds = list(request.folds)
        generation = {"source": "explicit", "fold_count": len(folds)}
    else:
        spec = request.auto_folds
        assert spec is not None
        if spec.embargo_sessions < request.min_embargo_sessions:
            raise WalkForwardValidationError(
                f"auto_folds.embargo_sessions ({spec.embargo_sessions}) is below min_embargo_sessions "
                f"({request.min_embargo_sessions})"
            )
        o_start = spec.overall_start or base_config.start_date
        o_end = spec.overall_end or base_config.end_date
        if o_start >= o_end:
            raise WalkForwardValidationError("auto_folds overall_start must precede overall_end")
        calendar = build_session_calendar(base_config, o_end)
        folds, generation = generate_auto_folds(calendar, spec, overall_start=o_start, overall_end=o_end)
        if generation["dropped_trailing_sessions"]:
            warnings.append(
                f"{generation['dropped_trailing_sessions']} trailing session(s) did not form a complete test window "
                "and are not evaluated; no window was shortened."
            )
    planned = _check_budget(len(folds), len(candidates))
    boundaries, fold_warnings = validate_folds(folds, calendar, min_embargo_sessions=request.min_embargo_sessions)
    warnings.extend(fold_warnings)

    labels = [f.label or f"fold_{i + 1}" for i, f in enumerate(folds)]
    base_hash = effective_config_hash(base_config)
    cand_hashes = [
        effective_config_hash(c.apply(base_config, name="hash", start=base_config.start_date, end=base_config.end_date))
        for c in candidates
    ]
    generation = {
        **generation,
        "min_embargo_sessions": request.min_embargo_sessions,
        "calendar_first_session": calendar[0].isoformat(),
        "calendar_last_session": calendar[-1].isoformat(),
        "calendar_sessions": len(calendar),
    }
    return WalkForwardPlan(
        base_config=base_config,
        base_config_hash=base_hash,
        selection=request.selection,
        folds=folds,
        labels=labels,
        boundaries=boundaries,
        candidates=candidates,
        candidate_hashes=cand_hashes,
        deduplicated=dropped,
        planned_runs=planned,
        fold_generation=generation,
        warnings=warnings,
        include_segment_curves=request.include_segment_curves,
    )


# --------------------------------------------------------------------------- selection (training data only)


def _objective(metrics: BacktestMetrics, objective: str) -> tuple[tuple[int, Decimal] | None, Decimal | None]:
    """Returns (rank key as (tier, value) or None if undefined, reported objective value)."""
    if objective == "sharpe":
        return (None, None) if metrics.sharpe is None else ((0, metrics.sharpe), metrics.sharpe)
    if objective == "total_return":
        return (0, metrics.total_return), metrics.total_return
    if objective == "return_over_max_drawdown":
        if metrics.max_drawdown > 0:
            ratio = metrics.total_return / metrics.max_drawdown
            return (0, ratio), ratio
        if metrics.total_return > 0:
            return (1, metrics.total_return), None  # positive return with zero drawdown outranks any finite ratio
        return (0, Decimal(0)), Decimal(0)
    raise WalkForwardValidationError(f"Unknown objective {objective}")


def evaluate_candidates(
    candidates: list[Candidate],
    candidate_hashes: list[str],
    train_metrics: list[BacktestMetrics],
    spec: WalkForwardSelectionSpec,
    horizon: str,
    deduplicated: list[dict],
) -> tuple[list[CandidateReport], SelectionReport]:
    """Rank candidates using TRAINING metrics only. The signature admits no test-window input."""
    if not (len(candidates) == len(candidate_hashes) == len(train_metrics)):
        raise WalkForwardIntegrityError("candidate, hash, and training-metric lists must align")
    reports: list[CandidateReport] = []
    keys: dict[int, tuple[int, Decimal]] = {}
    for cand, h, m in zip(candidates, candidate_hashes, train_metrics, strict=True):
        key, value = _objective(m, spec.objective)
        reason: str | None = None
        if m.total_trades < spec.min_train_trades:
            reason = f"train_trades {m.total_trades} < min_train_trades {spec.min_train_trades}"
        elif key is None:
            reason = f"objective {spec.objective} undefined on training window"
        eligible = reason is None
        if eligible and key is not None:
            keys[cand.index] = key
        reports.append(
            CandidateReport(
                candidate_index=cand.index,
                is_base=cand.is_base,
                params=cand.params(),
                effective_params=cand.effective_params(horizon),
                config_hash=h,
                eligible=eligible,
                ineligible_reason=reason,
                objective_value=value,
                train_trades=m.total_trades,
                train_metrics=m,
            )
        )

    def sort_key(idx: int) -> tuple:
        tier, value = keys[idx]
        m = train_metrics[idx]
        return (-tier, -value, -m.total_return, m.max_drawdown, idx)

    ranking = sorted(keys, key=sort_key)
    warnings: list[str] = []
    if spec.mode == "fixed":
        status, tuned, selected = "fixed_config", False, 0
    elif len(candidates) == 1:
        status, tuned, selected = "single_candidate_no_selection", False, 0
        warnings.append("Grid collapsed to the base configuration after deduplication; nothing was selected.")
    elif ranking:
        status, tuned, selected = "selected_on_train", True, ranking[0]
    else:
        status, tuned, selected = "fallback_no_candidate_qualified", False, 0
        warnings.append(
            f"No candidate had at least {spec.min_train_trades} training trade(s) with a defined objective; "
            "fell back to base_config. The result is NOT tuned."
        )
    sel_trades = train_metrics[selected].total_trades
    if sel_trades < LOW_TRAIN_TRADES_WARNING:
        warnings.append(
            f"Selected configuration has only {sel_trades} training trade(s) (< {LOW_TRAIN_TRADES_WARNING}); "
            "the training objective is statistically fragile."
        )
    selection = SelectionReport(
        status=status,
        tuned=tuned,
        no_candidate_qualified=status == "fallback_no_candidate_qualified",
        objective=spec.objective,
        min_train_trades=spec.min_train_trades,
        selected_candidate_index=selected,
        selected_params=candidates[selected].params(),
        selected_config_hash=candidate_hashes[selected],
        selected_objective_value=reports[selected].objective_value,
        selected_train_trades=sel_trades,
        ranking=ranking,
        deduplicated_candidates=deduplicated,
        warnings=warnings,
    )
    return reports, selection


# --------------------------------------------------------------------------- segment helpers


def _equity_digest(curve: list[EquityPoint]) -> str:
    h = hashlib.sha256()
    for p in curve:
        h.update(f"{p.date.isoformat()}|{p.equity}|{p.cash}|{p.invested}|{p.drawdown}\n".encode())
    return h.hexdigest()


def _assert_inside_window(run: BacktestRun, start: date, end: date, label: str) -> None:
    for p in run.equity_curve:
        if not (start <= p.date <= end):
            raise WalkForwardIntegrityError(f"{label}: equity point {p.date} outside segment {start}..{end}")
    for t in run.trades:
        exit_date = t.exit_date or t.entry_date
        if t.entry_date < start or exit_date > end:
            raise WalkForwardIntegrityError(
                f"{label}: trade {t.symbol} {t.entry_date}..{exit_date} outside segment {start}..{end}"
            )


def _require_completed(run: BacktestRun, label: str) -> BacktestMetrics:
    if run.status != BacktestStatus.COMPLETED or run.metrics is None:
        raise WalkForwardValidationError(f"{label}: segment run did not complete (status {run.status.value})")
    return run.metrics


def _segment_result(
    kind: str, run: BacktestRun, config_hash: str, start: date, end: date, include_curve: bool
) -> SegmentResult:
    assert run.metrics is not None
    curve = run.equity_curve
    return SegmentResult(
        segment=kind,  # type: ignore[arg-type]
        start_date=start,
        end_date=end,
        config_hash=config_hash,
        status=run.status.value,
        metrics=run.metrics,
        trade_count=len(run.trades),
        trades=run.trades,
        equity_points=len(curve),
        equity_sha256=_equity_digest(curve),
        equity_curve=curve if include_curve else None,
        open_invested_at_end=curve[-1].invested if curve else D(0),
        evidence_grade=run.evidence_grade,
        data_provenance=run.data_provenance,
        warnings=list(run.warnings),
    )


def _aggregate_provenance(runs: list[BacktestRun]) -> tuple[EvidenceGrade, DataProvenance]:
    grade = (
        EvidenceGrade.DEMO
        if (not runs or any(r.evidence_grade == EvidenceGrade.DEMO for r in runs))
        else EvidenceGrade.IMPORTED_UNVERIFIED
    )
    kinds = {r.data_provenance.kind for r in runs}
    sources = sorted({r.data_provenance.source for r in runs})
    symbols: dict[str, str] = {}
    for r in runs:
        symbols.update(r.data_provenance.symbols)
    kind = next(iter(kinds)) if len(kinds) == 1 else ("mixed" if kinds else "unknown")
    return grade, DataProvenance(kind=kind, source=",".join(sources) if sources else "unknown", symbols=symbols)


# --------------------------------------------------------------------------- OOS stitching


def stitch_oos(test_runs: list[BacktestRun], initial: Decimal) -> tuple[list[EquityPoint], list[CompletedTrade], BacktestMetrics]:
    """Chain disjoint test-window equity curves multiplicatively. Test segments only.

    Each fold was simulated from a fresh book at ``initial`` capital. Chaining rescales a fold's curve so it starts
    from the previous fold's ending equity; this is a presentation device, not a single continuous simulation.
    """
    curve: list[EquityPoint] = []
    trades: list[CompletedTrade] = []
    stats: dict = {"max_stale_days": 0}
    anchor = initial
    peak = initial
    for run in test_runs:
        scale = anchor / initial
        for p in run.equity_curve:
            eq = money(p.equity * scale)
            cash = money(p.cash * scale)
            peak = max(peak, eq)
            dd = (peak - eq) / peak if peak > 0 else D(0)
            curve.append(EquityPoint(date=p.date, equity=eq, cash=cash, invested=money(eq - cash), drawdown=D(dd)))
        if run.equity_curve:
            anchor = curve[-1].equity
        trades.extend(run.trades)
        m = run.metrics
        assert m is not None
        for key in (
            "shariah_rejections",
            "risk_rejections",
            "ownership_blocked_exits",
            "unfilled_orders",
            "fill_rejections",
            "stale_marks",
        ):
            stats[key] = stats.get(key, 0) + getattr(m, key)
        stats["max_stale_days"] = max(stats["max_stale_days"], m.max_stale_days)
    metrics = compute_metrics(curve, trades, initial, benchmark_return=None, stats=stats)
    return curve, trades, metrics


# --------------------------------------------------------------------------- execution


def execute_plan(
    plan: WalkForwardPlan,
    runner: Callable[[BacktestConfig], BacktestRun] | None = None,
    on_event: Callable[[dict], None] | None = None,
) -> WalkForwardV2Response:
    """Run a validated plan. ``runner`` defaults to ``run_backtest`` (resolved at call time)."""
    if market_breadth._SCOPED_CACHE.get() is not None:
        raise WalkForwardIntegrityError("walk-forward v2 must not run inside an active breadth-cache scope")
    run_fn = runner if runner is not None else run_backtest
    base = plan.base_config
    initial = D(base.initial_capital)
    run_log: list[dict] = []
    executed = 0

    def log(event: str, **info: object) -> None:
        entry = {"seq": len(run_log) + 1, "event": event, **info}
        run_log.append(entry)
        if on_event is not None:
            on_event(entry)

    def call(cfg: BacktestConfig) -> BacktestRun:
        nonlocal executed
        if executed >= plan.planned_runs:
            raise WalkForwardIntegrityError("run budget exhausted: refusing to start an unplanned run")
        executed += 1
        return run_fn(cfg)

    fold_results: list[FoldResult] = []
    test_runs: list[BacktestRun] = []
    all_runs: list[BacktestRun] = []
    cand_counts: list[int] = []

    for k, fold in enumerate(plan.folds):
        label = plan.labels[k]
        bounds = plan.boundaries[k]
        train_runs: list[BacktestRun] = []
        train_metrics: list[BacktestMetrics] = []
        for cand, c_hash in zip(plan.candidates, plan.candidate_hashes, strict=True):
            cfg = cand.apply(
                base, name=f"{base.name}_wf2_{label}_train_c{cand.index}", start=fold.train_start, end=fold.train_end
            )
            log(
                "train_run",
                fold_index=k,
                candidate_index=cand.index,
                config_hash=c_hash,
                start_date=fold.train_start.isoformat(),
                end_date=fold.train_end.isoformat(),
            )
            run = call(cfg)
            m = _require_completed(run, f"{label} train candidate {cand.index}")
            _assert_inside_window(run, fold.train_start, fold.train_end, f"{label} train c{cand.index}")
            train_runs.append(run)
            train_metrics.append(m)
        all_runs.extend(train_runs)
        cand_counts.append(len(plan.candidates))

        reports, selection = evaluate_candidates(
            plan.candidates, plan.candidate_hashes, train_metrics, plan.selection, base.horizon, plan.deduplicated
        )
        sel = plan.candidates[selection.selected_candidate_index]
        test_cfg = sel.apply(base, name=f"{base.name}_wf2_{label}_test", start=fold.test_start, end=fold.test_end)
        test_hash = effective_config_hash(test_cfg)
        if test_hash != selection.selected_config_hash:
            raise WalkForwardIntegrityError(f"{label}: test configuration hash differs from the frozen selection")
        log(
            "selection_frozen",
            fold_index=k,
            selected_candidate_index=sel.index,
            selected_config_hash=selection.selected_config_hash,
            status=selection.status,
        )
        log(
            "test_run",
            fold_index=k,
            candidate_index=sel.index,
            config_hash=test_hash,
            start_date=fold.test_start.isoformat(),
            end_date=fold.test_end.isoformat(),
        )
        test_run = call(test_cfg)
        _require_completed(test_run, f"{label} test")
        _assert_inside_window(test_run, fold.test_start, fold.test_end, f"{label} test")
        test_runs.append(test_run)
        all_runs.append(test_run)

        fold_results.append(
            FoldResult(
                fold_index=k,
                label=label,
                boundaries=bounds,
                candidates=reports,
                selection=selection,
                train_result=_segment_result(
                    "train",
                    train_runs[sel.index],
                    selection.selected_config_hash,
                    fold.train_start,
                    fold.train_end,
                    plan.include_segment_curves,
                ),
                test_result=_segment_result(
                    "test", test_run, test_hash, fold.test_start, fold.test_end, plan.include_segment_curves
                ),
            )
        )

    curve, trades, oos_metrics = stitch_oos(test_runs, initial)
    returns = [r.metrics.total_return for r in test_runs if r.metrics is not None]
    open_invested = [r.equity_curve[-1].invested if r.equity_curve else D(0) for r in test_runs]
    oos = OOSSummary(
        fold_count=len(test_runs),
        total_test_sessions=sum(b.test_sessions for b in plan.boundaries),
        positive_test_folds=sum(1 for r in returns if r > 0),
        zero_trade_test_folds=sum(1 for r in test_runs if r.metrics is not None and r.metrics.total_trades == 0),
        fold_test_returns=[str(r) for r in returns],
        folds_with_open_end_positions=[i for i, v in enumerate(open_invested) if v > 0],
        open_invested_at_fold_ends_total=sum(open_invested, D(0)),
        oos_metrics=oos_metrics,
        oos_trades=trades,
        oos_equity_curve=curve,
        oos_equity_sha256=_equity_digest(curve),
        notes=[
            "Built from test windows only; training runs contribute nothing to these figures.",
            "Not one continuous simulation: every fold ran from a fresh book at initial capital and the equity curve "
            "is chained by rescaling each fold to the previous fold's ending equity.",
            "Positions still open at a test window's end are marked but not liquidated or counted as trades (B-15); "
            "see open_invested_at_fold_ends_total.",
            "CAGR spans the first to last stitched test date and ignores embargo/gap periods between folds.",
        ],
    )

    grade, provenance = _aggregate_provenance(all_runs)
    tuned_any = any(f.selection.tuned for f in fold_results)
    fallback_any = any(f.selection.no_candidate_qualified for f in fold_results)
    warnings = list(plan.warnings)
    for f in fold_results:
        warnings.extend(f"{f.label}: {w}" for w in f.selection.warnings)
    warnings.extend(
        [
            "Survivorship bias (B-09): the universe is the current membership for all historical dates.",
            "Benchmark and regime proxy is an equal-weight proxy of surviving constituents (B-14).",
            "Shariah screening uses stored snapshots without verified publication dates (B-10).",
            "Positions open at a segment's end are marked, not liquidated or counted as trades (B-15).",
        ]
    )
    if base.cost_scenario == CostScenario.ZERO:
        warnings.append("Cost scenario ZERO: results exclude transaction costs (B-05); not a net-of-cost estimate.")
    if max(cand_counts, default=1) > 1:
        warnings.append(
            "Parameter search on training windows adds selection (multiple-testing) risk; the test windows are the "
            "only out-of-sample evidence (B-23: no overfitting adjustment is applied)."
        )
    if grade == EvidenceGrade.DEMO:
        warnings.append(
            "Evidence grade DEMO: synthetic or unknown-provenance data. Passing software tests proves the "
            "walk-forward machinery, not strategy validity."
        )
    if fallback_any:
        warnings.append("At least one fold fell back to base_config because no candidate qualified; those folds are not tuned.")

    disclosures = {
        "evidence_grade_note": "DEMO grade is retained for synthetic or unknown-provenance data.",
        "survivorship_biased": True,
        "benchmark_is_survivor_proxy": True,
        "shariah_publication_dates_unverified": True,
        "shariah_mode": base.shariah_mode.value,
        "cost_scenario": base.cost_scenario.value,
        "end_of_segment_positions_unliquidated": True,
        "candidates_per_fold": cand_counts,
        "any_fold_tuned": tuned_any,
        "any_fold_fell_back_to_base": fallback_any,
        "results_persisted": False,
    }
    return WalkForwardV2Response(
        schema_version=SCHEMA_VERSION,
        status="COMPLETED",
        notice=(
            "Walk-forward v2: parameters are chosen on training windows only; out-of-sample figures come from "
            "disjoint, independently simulated test windows. Research evidence only; no orders are placed."
        ),
        base_config=base,
        base_config_hash=plan.base_config_hash,
        selection_spec=plan.selection,
        fold_generation=plan.fold_generation,
        run_budget=RunBudget(max=MAX_SEGMENT_RUNS, planned=plan.planned_runs, executed=executed),
        evidence_grade=grade,
        data_provenance=provenance,
        disclosures=disclosures,
        warnings=warnings,
        folds=fold_results,
        oos_summary=oos,
        run_log=run_log,
    )


def run_walk_forward_v2(base_config: BacktestConfig, request: WalkForwardV2Request) -> WalkForwardV2Response:
    return execute_plan(plan_walk_forward(base_config, request))
