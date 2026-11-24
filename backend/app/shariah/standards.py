"""Named screening standards — thresholds are configurable, not scholarly rulings."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.portfolio.money import D


@dataclass(frozen=True)
class ScreeningStandard:
    standard_id: str
    name: str
    version: str
    provider: str
    review_days: int
    business_exclusions: tuple[str, ...]
    debt_ratio_max: Decimal
    non_compliant_income_max: Decimal
    cash_receivables_max: Decimal | None
    source_ref: str


BUILTIN_STANDARDS: dict[str, ScreeningStandard] = {
    "aaoifi_demo_v1": ScreeningStandard(
        standard_id="aaoifi_demo_v1",
        name="AAOIFI-style (demo config)",
        version="1.0.0",
        provider="config_template",
        review_days=90,
        business_exclusions=(
            "conventional_banking",
            "conventional_insurance",
            "alcohol",
            "gambling",
            "pork",
            "adult_entertainment",
        ),
        debt_ratio_max=D("0.30"),
        non_compliant_income_max=D("0.05"),
        cash_receivables_max=D("0.33"),
        source_ref="Template only — requires user/Shariah board approval before production use.",
    ),
    "ftse_shariah_demo_v1": ScreeningStandard(
        standard_id="ftse_shariah_demo_v1",
        name="FTSE Shariah-style (demo config)",
        version="1.0.0",
        provider="config_template",
        review_days=90,
        business_exclusions=("conventional_banking", "alcohol", "gambling", "tobacco"),
        debt_ratio_max=D("0.3333"),
        non_compliant_income_max=D("0.05"),
        cash_receivables_max=None,
        source_ref="Template only — not licensed FTSE data.",
    ),
}


def list_standards() -> list[dict]:
    return [
        {
            "standard_id": s.standard_id,
            "name": s.name,
            "version": s.version,
            "provider": s.provider,
            "source_ref": s.source_ref,
        }
        for s in BUILTIN_STANDARDS.values()
    ]