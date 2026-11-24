"""Drawdown episodes from immutable valuation snapshots (no repricing)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.portfolio.money import D, money
from app.portfolio.valuation_schemas import ValuationSnapshotRecord


@dataclass
class DrawdownEpisode:
    peak_equity: Decimal
    peak_date: date
    trough_equity: Decimal
    trough_date: date
    max_drawdown_pct: Decimal
    recovered: bool
    recovery_date: date | None = None
    drawdown_days: int = 0
    recovery_days: int | None = None


def max_drawdown_over_period(snapshots: list[ValuationSnapshotRecord]) -> Decimal:
    if not snapshots:
        return D(0)
    peak = D(0)
    max_dd = D(0)
    for s in sorted(snapshots, key=lambda x: x.valuation_date):
        eq = s.portfolio_equity
        if eq > peak:
            peak = eq
        if peak > 0:
            dd = (peak - eq) / peak
            if dd > max_dd:
                max_dd = dd
    return money(max_dd)


def current_drawdown_from_latest(latest: ValuationSnapshotRecord | None) -> dict:
    if not latest:
        return {
            "current_drawdown_pct": "0",
            "current_drawdown_amount": "0",
            "equity_peak_at_snapshot": "0",
            "portfolio_equity": "0",
        }
    return {
        "current_drawdown_pct": str(latest.drawdown_pct),
        "current_drawdown_amount": str(latest.drawdown_amount),
        "equity_peak_at_snapshot": str(latest.equity_peak_at_snapshot),
        "portfolio_equity": str(latest.portfolio_equity),
        "as_of_date": latest.valuation_date.isoformat(),
        "as_of_at": latest.valued_at.isoformat(),
    }


def episodes_from_snapshots(snapshots: list[ValuationSnapshotRecord]) -> list[DrawdownEpisode]:
    """Identify drawdown episodes using stored equity only."""
    ordered = sorted(snapshots, key=lambda x: (x.valuation_date, x.valued_at))
    if not ordered:
        return []
    episodes: list[DrawdownEpisode] = []
    peak_eq = ordered[0].portfolio_equity
    peak_d = ordered[0].valuation_date
    trough_eq = peak_eq
    trough_d = peak_d
    in_dd = False

    def flush(ep_peak, ep_peak_d, ep_trough, ep_trough_d, recovered, rec_d):
        if ep_peak <= 0:
            return
        dd_pct = money((ep_peak - ep_trough) / ep_peak)
        if dd_pct <= 0:
            return
        dd_days = (ep_trough_d - ep_peak_d).days
        rec_days = (rec_d - ep_trough_d).days if recovered and rec_d else None
        episodes.append(
            DrawdownEpisode(
                peak_equity=ep_peak,
                peak_date=ep_peak_d,
                trough_equity=ep_trough,
                trough_date=ep_trough_d,
                max_drawdown_pct=dd_pct,
                recovered=recovered,
                recovery_date=rec_d,
                drawdown_days=max(0, dd_days),
                recovery_days=rec_days,
            )
        )

    for s in ordered[1:]:
        eq = s.portfolio_equity
        d = s.valuation_date
        if eq >= peak_eq:
            if in_dd:
                flush(peak_eq, peak_d, trough_eq, trough_d, True, d)
                in_dd = False
            peak_eq = eq
            peak_d = d
            trough_eq = eq
            trough_d = d
        else:
            in_dd = True
            if eq < trough_eq:
                trough_eq = eq
                trough_d = d
    if in_dd:
        flush(peak_eq, peak_d, trough_eq, trough_d, False, None)
    return episodes