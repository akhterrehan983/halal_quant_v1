from __future__ import annotations

import math
from decimal import Decimal

import pandas as pd

from app.backtesting.schemas import BacktestMetrics, CompletedTrade, EquityPoint
from app.portfolio.money import D


def compute_metrics(
    curve: list[EquityPoint],
    trades: list[CompletedTrade],
    initial: Decimal,
    *,
    benchmark_return: Decimal | None,
    stats: dict,
) -> BacktestMetrics:
    if not curve:
        return BacktestMetrics(initial_capital=initial, final_capital=initial, total_return=D(0), max_drawdown=D(0))
    final = curve[-1].equity
    total_ret = (final - initial) / initial if initial > 0 else D(0)
    rets = []
    for i in range(1, len(curve)):
        if curve[i - 1].equity > 0:
            rets.append(float((curve[i].equity - curve[i - 1].equity) / curve[i - 1].equity))
    vol = Decimal(str(pd.Series(rets).std() * math.sqrt(252))) if len(rets) > 1 else None
    sharpe = None
    if vol and vol > 0 and rets:
        sharpe = Decimal(str((pd.Series(rets).mean() * 252) / float(vol)))
    dd = max((p.drawdown for p in curve), default=D(0))
    wins = [t for t in trades if t.net_pnl > 0]
    losses = [t for t in trades if t.net_pnl <= 0]
    wr = Decimal(len(wins)) / Decimal(len(trades)) if trades else None
    gp = sum(t.net_pnl for t in wins)
    gl = abs(sum(t.net_pnl for t in losses))
    pf = (gp / gl) if gl > 0 else None
    years = max((curve[-1].date - curve[0].date).days / 365.25, 0.01)
    cagr = (final / initial) ** Decimal(str(1 / years)) - 1 if initial > 0 and years > 0 else None
    costs = sum((t.costs for t in trades), D(0))
    hold = Decimal(str(sum(t.holding_days for t in trades) / len(trades))) if trades else None
    return BacktestMetrics(
        initial_capital=initial,
        final_capital=final,
        total_return=total_ret.quantize(Decimal("0.0001")),
        cagr=cagr.quantize(Decimal("0.0001")) if cagr is not None else None,
        max_drawdown=dd,
        volatility=vol,
        sharpe=sharpe,
        win_rate=wr.quantize(Decimal("0.0001")) if wr is not None else None,
        profit_factor=pf.quantize(Decimal("0.01")) if pf is not None else None,
        total_trades=len(trades),
        avg_holding_days=hold,
        transaction_costs=costs,
        benchmark_return=benchmark_return,
        shariah_rejections=stats.get("shariah_rejections", 0),
        risk_rejections=stats.get("risk_rejections", 0),
        ownership_blocked_exits=stats.get("ownership_blocked_exits", 0),
        unfilled_orders=stats.get("unfilled_orders", 0),
        fill_rejections=stats.get("fill_rejections", 0),
        stale_marks=stats.get("stale_marks", 0),
        max_stale_days=stats.get("max_stale_days", 0),
    )