from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, Field, field_validator

from app.market_data.benchmarks import DEFAULT_BENCHMARK_SYMBOL
from app.portfolio.money import D


class ShariahBacktestMode(str, Enum):
    STRICT = "STRICT"
    RESEARCH_ONLY = "RESEARCH_ONLY"


class CostScenario(str, Enum):
    ZERO = "ZERO"
    REALISTIC = "REALISTIC"
    CONSERVATIVE = "CONSERVATIVE"


class EvidenceGrade(str, Enum):
    """How much a result can be trusted as evidence. Phase 1 never assigns a research-grade label."""

    DEMO = "demo"  # synthetic or unknown provenance: software-regression output only
    IMPORTED_UNVERIFIED = "imported_unverified"  # real imported bars, not yet validated for research


class DataProvenance(BaseModel):
    kind: str = "unknown"  # synthetic | imported | mixed | unknown
    source: str = "unknown"
    symbols: dict[str, str] = Field(default_factory=dict)


class BacktestStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class BacktestConfig(BaseModel):
    name: str
    start_date: date
    end_date: date
    initial_capital: Decimal = Field(default_factory=lambda: D(100000))
    horizon: str = "swing"
    strategies: list[str] = Field(default_factory=lambda: ["unified"])
    symbols: list[str] | None = None
    benchmark: str = DEFAULT_BENCHMARK_SYMBOL
    shariah_profile_id: str = "default"
    shariah_mode: ShariahBacktestMode = ShariahBacktestMode.STRICT
    ownership_policy: str = "conservative_delivery"
    cost_scenario: CostScenario = CostScenario.ZERO
    slippage_bps: int = 10
    max_positions: int = 5
    max_adv_participation: Decimal = Field(default_factory=lambda: D("0.05"))
    random_seed: int = 42
    universe_mode: str = "current_snapshot_with_survivorship_warning"
    min_signal_score: int = 0
    hold_days: int | None = None

    @field_validator("initial_capital")
    @classmethod
    def positive_capital(cls, v: Decimal) -> Decimal:
        if v <= 0:
            raise ValueError("initial_capital must be positive")
        return v

    def validate_dates(self) -> None:
        if self.start_date >= self.end_date:
            raise ValueError("start_date must precede end_date")


class CompletedTrade(BaseModel):
    symbol: str
    strategy: str
    horizon: str
    entry_date: date
    entry_price: Decimal
    quantity: int
    exit_date: date | None = None
    exit_price: Decimal | None = None
    gross_pnl: Decimal = Field(default_factory=lambda: D(0))
    net_pnl: Decimal = Field(default_factory=lambda: D(0))
    costs: Decimal = Field(default_factory=lambda: D(0))
    slippage: Decimal = Field(default_factory=lambda: D(0))
    holding_days: int = 0
    exit_reason: str = ""
    shariah_status: str = ""
    ownership_delayed_exit: bool = False
    signal_quantity: int = 0  # quantity sized at signal time, before fill-time validation
    # Stop reporting (None on legacy rows and on exits that are not stop-driven).
    stop_price: Decimal | None = None  # the protective stop the position carried
    stop_breach_date: date | None = None  # session whose low (or open) first traded at/through the stop
    delayed_exit_date: date | None = None  # set only when the sale was held back by ownership authorisation
    loss_beyond_stop: Decimal | None = None  # max(0, stop - actual fill) * quantity, before costs


class EquityPoint(BaseModel):
    date: date
    equity: Decimal
    cash: Decimal
    invested: Decimal
    drawdown: Decimal = Field(default_factory=lambda: D(0))


class BacktestMetrics(BaseModel):
    initial_capital: Decimal
    final_capital: Decimal
    total_return: Decimal
    cagr: Decimal | None = None
    max_drawdown: Decimal
    volatility: Decimal | None = None
    sharpe: Decimal | None = None
    sortino: Decimal | None = None
    win_rate: Decimal | None = None
    profit_factor: Decimal | None = None
    total_trades: int = 0
    avg_holding_days: Decimal | None = None
    transaction_costs: Decimal = Field(default_factory=lambda: D(0))
    benchmark_return: Decimal | None = None
    shariah_rejections: int = 0
    risk_rejections: int = 0
    ownership_blocked_exits: int = 0
    unfilled_orders: int = 0
    fill_rejections: int = 0
    stale_marks: int = 0
    max_stale_days: int = 0


class BacktestRun(BaseModel):
    backtest_id: int | None = None
    status: BacktestStatus = BacktestStatus.PENDING
    config: BacktestConfig
    created_at: datetime | None = None
    completed_at: datetime | None = None
    warnings: list[str] = Field(default_factory=list)
    metrics: BacktestMetrics | None = None
    equity_curve: list[EquityPoint] = Field(default_factory=list)
    trades: list[CompletedTrade] = Field(default_factory=list)
    validation: dict = Field(default_factory=dict)
    # Legacy rows without these fields load as DEMO / unknown provenance (conservative default).
    evidence_grade: EvidenceGrade = EvidenceGrade.DEMO
    data_provenance: DataProvenance = Field(default_factory=DataProvenance)