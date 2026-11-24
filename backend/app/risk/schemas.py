from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.portfolio.money import D


class SleeveRiskLimits(BaseModel):
    risk_per_trade_pct: Decimal = D("0.0075")  # 0.75% initial default
    max_stock_exposure_pct: Decimal = D("0.10")
    max_sector_exposure_pct: Decimal = D("0.25")
    max_open_positions: int = 8
    max_portfolio_open_risk_pct: Decimal = D("0.06")
    min_cash_reserve_pct: Decimal = D("0.10")
    max_drawdown_pct: Decimal = D("0.15")
    max_daily_loss_pct: Decimal = D("0.03")
    max_adv_participation_pct: Decimal = D("0.05")
    unclassified_sector_cap_pct: Decimal = D("0.15")


class RiskConfiguration(BaseModel):
    swing: SleeveRiskLimits = Field(default_factory=SleeveRiskLimits)
    positional: SleeveRiskLimits = Field(
        default_factory=lambda: SleeveRiskLimits(
            risk_per_trade_pct=D("0.005"),
            max_open_positions=12,
            max_portfolio_open_risk_pct=D("0.08"),
        )
    )
    swing_capital_pct: Decimal = D("0.40")
    positional_capital_pct: Decimal = D("0.40")
    cash_reserve_pct: Decimal = D("0.20")

    def validate_allocations(self) -> None:
        total = self.swing_capital_pct + self.positional_capital_pct + self.cash_reserve_pct
        if total > Decimal("1.0001"):
            raise ValueError(f"Sleeve + reserve allocations exceed 100%: {total}")


class RiskEvent(BaseModel):
    event_id: int | None = None
    event_type: str
    message: str
    detail: dict = Field(default_factory=dict)
    created_at: datetime | None = None


class ValidationResult(BaseModel):
    approved: bool
    rejections: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    metrics: dict = Field(default_factory=dict)