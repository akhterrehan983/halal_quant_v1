from __future__ import annotations

from decimal import Decimal

from app.portfolio.money import D
from app.portfolio.schemas import SleeveHolding
from app.portfolio.sectors import sector_for


def holding_market_value(h: SleeveHolding, mark: Decimal) -> Decimal:
    return (D(h.quantity) * D(mark)).quantize(Decimal("0.01"))


def open_risk_for_holding(h: SleeveHolding, mark: Decimal) -> Decimal:
    if h.stop_reference and h.stop_reference < mark:
        return (D(h.quantity) * (D(mark) - D(h.stop_reference))).quantize(Decimal("0.01"))
    if h.risk_per_share:
        return (D(h.quantity) * D(h.risk_per_share)).quantize(Decimal("0.01"))
    return D(0)


def exposure_by_stock(holdings: list[SleeveHolding], prices: dict[str, Decimal]) -> dict[str, Decimal]:
    out: dict[str, Decimal] = {}
    for h in holdings:
        px = prices.get(h.symbol.upper(), D(h.average_entry))
        out[h.symbol.upper()] = out.get(h.symbol.upper(), D(0)) + holding_market_value(h, px)
    return out


def exposure_by_sector(holdings: list[SleeveHolding], prices: dict[str, Decimal]) -> dict[str, Decimal]:
    out: dict[str, Decimal] = {}
    for h in holdings:
        px = prices.get(h.symbol.upper(), D(h.average_entry))
        sector = sector_for(h.symbol) or "UNCLASSIFIED"
        out[sector] = out.get(sector, D(0)) + holding_market_value(h, px)
    return out


def exposure_pct(value: Decimal, equity: Decimal) -> Decimal:
    if equity <= 0:
        return D(0)
    return (value / equity).quantize(Decimal("0.0001"))