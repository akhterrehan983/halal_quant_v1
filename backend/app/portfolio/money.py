"""Rupee amounts as Decimal — no float ledger math."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

TWOPL = Decimal("0.01")
FOURPL = Decimal("0.0001")


def D(value: str | int | float | Decimal) -> Decimal:
    return Decimal(str(value)).quantize(FOURPL, rounding=ROUND_HALF_UP)


def money(value: Decimal) -> Decimal:
    return value.quantize(TWOPL, rounding=ROUND_HALF_UP)