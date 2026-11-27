"""Typed request/response models for walk-forward v2 (M14 Phase 2).

Requests are validated for types and ranges here (HTTP 422). Domain rules that need the session calendar
(fold chronology, embargo, warm-up, coverage, run budget) are enforced in ``walk_forward_v2`` (HTTP 400).
The v1 walk-forward module and the core backtest schemas are not touched.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.backtesting.schemas import (
    BacktestConfig,
    BacktestMetrics,
    CompletedTrade,
    DataProvenance,
    EquityPoint,
    EvidenceGrade,
)

SCHEMA_VERSION = "2.0"

# Every actual run_backtest() call counts: all training candidate runs plus one test run per fold.
MAX_SEGMENT_RUNS = 24
# Deduplicated candidates per fold, including the base configuration.
MAX_CANDIDATES_PER_FOLD = 12
# Mechanical-verification floor, not a statistical standard.
DEFAULT_MIN_TRAIN_TRADES = 3
LOW_TRAIN_TRADES_WARNING = 10
MIN_WARMUP_SESSIONS = 60  # matches the simulator's MIN_SIGNAL_BARS
PARTIAL_WARMUP_SESSIONS = 252  # sma200 / 52-week features need about a year of history
MIN_SEGMENT_SESSIONS = 2
MAX_RAW_GRID_SIZE = 64
MAX_FOLDS = MAX_SEGMENT_RUNS // 2

SelectionMode = Literal["fixed", "grid_search"]
Objective = Literal["sharpe", "total_return", "return_over_max_drawdown"]
FoldMode = Literal["rolling", "expanding"]
SelectionStatus = Literal[
    "fixed_config",
    "single_candidate_no_selection",
    "selected_on_train",
    "fallback_no_candidate_qualified",
]


# --------------------------------------------------------------------------- request


class WalkForwardFoldInput(BaseModel):
    label: str | None = Field(default=None, max_length=64)
    train_start: date
    train_end: date
    test_start: date
    test_end: date


class WalkForwardAutoFoldSpec(BaseModel):
    """Generate rolling or expanding folds from the tradable session calendar."""

    mode: FoldMode = "rolling"
    overall_start: date | None = None  # defaults to base_config.start_date
    overall_end: date | None = None  # defaults to base_config.end_date
    warmup_sessions: int = Field(default=MIN_WARMUP_SESSIONS, ge=MIN_WARMUP_SESSIONS, le=2000)
    train_sessions: int = Field(default=120, ge=20, le=2000)
    embargo_sessions: int = Field(default=0, ge=0, le=60)
    test_sessions: int = Field(default=40, ge=5, le=2000)
    step_sessions: int | None = Field(default=None, ge=1, le=2000)  # defaults to test_sessions


class WalkForwardGrid(BaseModel):
    """Predeclared candidate values. Only BacktestConfig knobs that change simulated behaviour today."""

    hold_days: list[int] | None = Field(default=None, max_length=12)
    min_signal_score: list[int] | None = Field(default=None, max_length=12)
    max_positions: list[int] | None = Field(default=None, max_length=10)

    @field_validator("hold_days")
    @classmethod
    def _hold_days(cls, v: list[int] | None) -> list[int] | None:
        if v is None:
            return None
        if not v or any(x < 4 or x > 120 for x in v):
            raise ValueError("hold_days values must be non-empty and within 4..120")
        return sorted(set(v))

    @field_validator("min_signal_score")
    @classmethod
    def _min_signal_score(cls, v: list[int] | None) -> list[int] | None:
        if v is None:
            return None
        if not v or any(x < 0 or x > 100 for x in v):
            raise ValueError("min_signal_score values must be non-empty and within 0..100")
        return sorted(set(v))

    @field_validator("max_positions")
    @classmethod
    def _max_positions(cls, v: list[int] | None) -> list[int] | None:
        if v is None:
            return None
        if not v or any(x < 1 or x > 10 for x in v):
            raise ValueError("max_positions values must be non-empty and within 1..10")
        return sorted(set(v))

    @model_validator(mode="after")
    def _bounded(self) -> WalkForwardGrid:
        dims = [d for d in (self.hold_days, self.min_signal_score, self.max_positions) if d is not None]
        if not dims:
            raise ValueError("grid must set at least one of hold_days, min_signal_score, max_positions")
        size = 1
        for d in dims:
            size *= len(d)
        if size > MAX_RAW_GRID_SIZE:
            raise ValueError(f"grid has {size} combinations; the schema limit is {MAX_RAW_GRID_SIZE}")
        return self


class WalkForwardSelectionSpec(BaseModel):
    mode: SelectionMode = "fixed"
    objective: Objective = "sharpe"
    min_train_trades: int = Field(default=DEFAULT_MIN_TRAIN_TRADES, ge=0, le=1000)
    grid: WalkForwardGrid | None = None

    @model_validator(mode="after")
    def _mode_matches_grid(self) -> WalkForwardSelectionSpec:
        if self.mode == "grid_search" and self.grid is None:
            raise ValueError("grid_search requires a grid")
        if self.mode == "fixed" and self.grid is not None:
            raise ValueError("fixed mode takes no grid; use mode='grid_search'")
        return self


class WalkForwardV2Request(BaseModel):
    folds: list[WalkForwardFoldInput] | None = Field(default=None, max_length=MAX_FOLDS)
    auto_folds: WalkForwardAutoFoldSpec | None = None
    min_embargo_sessions: int = Field(default=0, ge=0, le=60)
    selection: WalkForwardSelectionSpec = Field(default_factory=WalkForwardSelectionSpec)
    include_segment_curves: bool = False

    @model_validator(mode="after")
    def _one_fold_source(self) -> WalkForwardV2Request:
        if (self.folds is None) == (self.auto_folds is None):
            raise ValueError("provide exactly one of folds or auto_folds")
        if self.folds is not None and not self.folds:
            raise ValueError("folds must not be empty")
        return self


class WalkForwardStatelessV2Request(WalkForwardV2Request):
    base_config: BacktestConfig


# --------------------------------------------------------------------------- response


class FoldBoundaries(BaseModel):
    train_start: date
    train_end: date
    test_start: date
    test_end: date
    train_sessions: int
    test_sessions: int
    embargo_sessions_actual: int
    gap_calendar_days: int
    warmup_sessions_before_train: int


class CandidateReport(BaseModel):
    candidate_index: int
    is_base: bool
    params: dict  # values applied to BacktestConfig (hold_days may be None for the base)
    effective_params: dict  # normalised values used for deduplication and hashing
    config_hash: str
    eligible: bool
    ineligible_reason: str | None = None
    objective_value: Decimal | None = None
    train_trades: int
    train_metrics: BacktestMetrics


class SelectionReport(BaseModel):
    status: SelectionStatus
    tuned: bool
    no_candidate_qualified: bool
    objective: Objective
    min_train_trades: int
    selected_candidate_index: int
    selected_params: dict
    selected_config_hash: str
    selected_objective_value: Decimal | None = None
    selected_train_trades: int
    ranking: list[int]  # eligible candidate indices, best first
    deduplicated_candidates: list[dict]
    warnings: list[str] = Field(default_factory=list)


class SegmentResult(BaseModel):
    segment: Literal["train", "test"]
    start_date: date
    end_date: date
    config_hash: str
    status: str
    metrics: BacktestMetrics | None
    trade_count: int
    trades: list[CompletedTrade]
    equity_points: int
    equity_sha256: str
    equity_curve: list[EquityPoint] | None = None
    open_invested_at_end: Decimal
    evidence_grade: EvidenceGrade
    data_provenance: DataProvenance
    warnings: list[str] = Field(default_factory=list)


class FoldResult(BaseModel):
    fold_index: int
    label: str
    boundaries: FoldBoundaries
    candidates: list[CandidateReport]
    selection: SelectionReport
    train_result: SegmentResult  # the selected candidate's training run, training window only
    test_result: SegmentResult  # the frozen selected configuration, test window only


class OOSSummary(BaseModel):
    """The only block allowed to be called out-of-sample: stitched, disjoint test windows."""

    scope: Literal["stitched_test_windows_only"] = "stitched_test_windows_only"
    fold_count: int
    total_test_sessions: int
    positive_test_folds: int
    zero_trade_test_folds: int
    fold_test_returns: list[str]
    folds_with_open_end_positions: list[int]
    open_invested_at_fold_ends_total: Decimal
    oos_metrics: BacktestMetrics
    oos_trades: list[CompletedTrade]
    oos_equity_curve: list[EquityPoint]
    oos_equity_sha256: str
    notes: list[str]


class RunBudget(BaseModel):
    max: int
    planned: int
    executed: int


class WalkForwardV2Response(BaseModel):
    schema_version: str = SCHEMA_VERSION
    status: str = "COMPLETED"
    notice: str
    base_config: BacktestConfig
    base_config_hash: str
    selection_spec: WalkForwardSelectionSpec
    fold_generation: dict
    run_budget: RunBudget
    evidence_grade: EvidenceGrade
    data_provenance: DataProvenance
    disclosures: dict
    warnings: list[str]
    folds: list[FoldResult]
    oos_summary: OOSSummary
    run_log: list[dict]


def raw_grid_size(grid: WalkForwardGrid | None) -> int:
    if grid is None:
        return 1
    size = 1
    for dim in (grid.hold_days, grid.min_signal_score, grid.max_positions):
        if dim is not None:
            size *= len(dim)
    return size


__all__ = [
    "CandidateReport",
    "DEFAULT_MIN_TRAIN_TRADES",
    "FoldBoundaries",
    "FoldResult",
    "LOW_TRAIN_TRADES_WARNING",
    "MAX_CANDIDATES_PER_FOLD",
    "MAX_FOLDS",
    "MAX_RAW_GRID_SIZE",
    "MAX_SEGMENT_RUNS",
    "MIN_SEGMENT_SESSIONS",
    "MIN_WARMUP_SESSIONS",
    "OOSSummary",
    "PARTIAL_WARMUP_SESSIONS",
    "RunBudget",
    "SCHEMA_VERSION",
    "SegmentResult",
    "SelectionReport",
    "WalkForwardAutoFoldSpec",
    "WalkForwardFoldInput",
    "WalkForwardGrid",
    "WalkForwardSelectionSpec",
    "WalkForwardStatelessV2Request",
    "WalkForwardV2Request",
    "WalkForwardV2Response",
    "raw_grid_size",
]
