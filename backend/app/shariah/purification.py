from __future__ import annotations

from decimal import Decimal

from app.portfolio.money import D
from app.shariah.schemas import PurificationRecord


def calculate_purification(
    symbol: str,
    income_amount: Decimal,
    *,
    purification_ratio: Decimal | None,
    methodology: str,
    standard_id: str,
    reporting_period: str | None = None,
) -> PurificationRecord:
    if purification_ratio is None:
        return PurificationRecord(
            symbol=symbol.upper(),
            income_amount=D(income_amount),
            purification_ratio=None,
            purification_amount=None,
            methodology=methodology,
            standard_id=standard_id,
            reporting_period=reporting_period,
            note="Purification ratio not supplied — cannot calculate.",
        )
    amount = (D(income_amount) * D(purification_ratio)).quantize(Decimal("0.01"))
    return PurificationRecord(
        symbol=symbol.upper(),
        income_amount=D(income_amount),
        purification_ratio=D(purification_ratio),
        purification_amount=amount,
        methodology=methodology,
        standard_id=standard_id,
        reporting_period=reporting_period,
    )