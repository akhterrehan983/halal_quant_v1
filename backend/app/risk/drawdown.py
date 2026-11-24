from __future__ import annotations

from decimal import Decimal

from app.portfolio.money import D


def drawdown_pct(current: Decimal, peak: Decimal) -> Decimal:
    if peak <= 0:
        return D(0)
    dd = (peak - current) / peak
    return dd.quantize(Decimal("0.0001"))


def breach_drawdown(current_dd: Decimal, limit: Decimal) -> bool:
    return current_dd >= limit


def breach_daily_loss(daily_pnl: Decimal, equity: Decimal, limit_pct: Decimal) -> bool:
    if equity <= 0:
        return False
    loss_pct = (-daily_pnl / equity) if daily_pnl < 0 else D(0)
    return loss_pct >= limit_pct