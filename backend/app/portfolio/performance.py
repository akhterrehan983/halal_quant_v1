from __future__ import annotations

from decimal import Decimal

from app.portfolio.money import D, money
from app.portfolio.schemas import PortfolioSummary, SleeveHolding, SleeveSnapshot
from app.portfolio.exposure import holding_market_value, open_risk_for_holding
from app.risk.drawdown import drawdown_pct


def sleeve_snapshot(
    name: str,
    allocated: Decimal,
    cash: Decimal,
    reserved: Decimal,
    holdings: list[SleeveHolding],
    prices: dict[str, Decimal],
) -> SleeveSnapshot:
    invested = D(0)
    mkt = D(0)
    unreal = D(0)
    risk = D(0)
    for h in holdings:
        px = prices.get(h.symbol.upper(), D(h.average_entry))
        mv = holding_market_value(h, px)
        invested += D(h.quantity) * D(h.average_entry)
        mkt += mv
        unreal += mv - D(h.quantity) * D(h.average_entry)
        risk += open_risk_for_holding(h, px)
    return SleeveSnapshot(
        name=name,
        allocated_capital=allocated,
        available_cash=cash,
        reserved_cash=reserved,
        invested_value=money(invested),
        market_value=money(mkt),
        unrealized_pnl=money(unreal),
        position_count=len(holdings),
        open_risk=money(risk),
    )


def build_summary(
    *,
    total_capital: Decimal,
    balances: dict[str, Decimal],
    reserved: dict[str, Decimal],
    holdings_swing: list[SleeveHolding],
    holdings_pos: list[SleeveHolding],
    prices: dict[str, Decimal],
    realized_pnl: Decimal,
    peak_value: Decimal,
    drawdown_locked: bool,
    swing_alloc: Decimal,
    pos_alloc: Decimal,
) -> PortfolioSummary:
    swing_cash = balances.get("swing", D(0)) - reserved.get("swing", D(0))
    pos_cash = balances.get("positional", D(0)) - reserved.get("positional", D(0))
    reserve = balances.get("reserve", D(0))
    sw = sleeve_snapshot("swing", total_capital * swing_alloc, swing_cash, reserved.get("swing", D(0)), holdings_swing, prices)
    po = sleeve_snapshot("positional", total_capital * pos_alloc, pos_cash, reserved.get("positional", D(0)), holdings_pos, prices)
    market_value = sw.market_value + po.market_value
    portfolio_value = market_value + swing_cash + pos_cash + reserve
    unreal = sw.unrealized_pnl + po.unrealized_pnl
    open_risk = sw.open_risk + po.open_risk
    dd = drawdown_pct(portfolio_value, peak_value) if peak_value > 0 else D(0)
    return PortfolioSummary(
        total_capital=total_capital,
        cash_reserve=reserve,
        available_cash=swing_cash + pos_cash + reserve,
        invested_capital=sw.invested_value + po.invested_value,
        market_value=market_value,
        portfolio_value=portfolio_value,
        realized_pnl=realized_pnl,
        unrealized_pnl=unreal,
        open_risk=open_risk,
        current_drawdown_pct=dd,
        peak_value=peak_value,
        drawdown_locked=drawdown_locked,
        swing=sw,
        positional=po,
        sleeves_valid=True,
    )