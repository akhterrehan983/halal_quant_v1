"""Portfolio valuation — strict price handling for snapshots (M13)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal
from enum import Enum

from app.core.exceptions import HalalQuantError
from app.market_data.repository import get_history_dataframe
from app.portfolio.exposure import holding_market_value
from app.portfolio.money import D, money
from app.portfolio.performance import build_summary, sleeve_snapshot
from app.portfolio.schemas import SleeveHolding
from app.portfolio.store import BookState
from app.portfolio.store import get_risk_config
from app.risk.drawdown import drawdown_pct


class PriceStatus(str, Enum):
    VALID = "valid"
    STALE = "stale"
    UNAVAILABLE = "unavailable"


@dataclass
class ResolvedPrice:
    symbol: str
    price: Decimal | None
    status: PriceStatus
    as_of_date: date | None = None
    note: str = ""


@dataclass
class PriceResolution:
    prices: dict[str, Decimal] = field(default_factory=dict)
    resolutions: dict[str, ResolvedPrice] = field(default_factory=dict)
    max_stale_days: int = 5

    @property
    def complete(self) -> bool:
        return all(r.status in (PriceStatus.VALID, PriceStatus.STALE) for r in self.resolutions.values())

    def unavailable_symbols(self) -> list[str]:
        return [s for s, r in self.resolutions.items() if r.status == PriceStatus.UNAVAILABLE]

    def stale_symbols(self) -> list[str]:
        return [s for s, r in self.resolutions.items() if r.status == PriceStatus.STALE]

    def to_audit_json(self) -> dict:
        return {
            s: {
                "status": r.status.value,
                "price": str(r.price) if r.price is not None else None,
                "as_of_date": r.as_of_date.isoformat() if r.as_of_date else None,
                "note": r.note,
            }
            for s, r in self.resolutions.items()
        }


def _candle_as_of(df) -> date:
    ts = df["date"].iloc[-1]
    return ts.date() if hasattr(ts, "date") else ts


def resolve_holdings_prices(
    holdings: list[SleeveHolding],
    *,
    max_stale_days: int = 5,
    strict: bool = True,
) -> PriceResolution:
    """Resolve mark prices for held symbols. Does not use entry price as mark when strict."""
    symbols = sorted({h.symbol.upper() for h in holdings})
    today = datetime.now(timezone.utc).date()
    out = PriceResolution(max_stale_days=max_stale_days)
    for sym in symbols:
        try:
            df = get_history_dataframe(sym, limit=5)
            as_of = _candle_as_of(df)
            px = D(df.close.iloc[-1])
            age = (today - as_of).days
            if age > max_stale_days:
                out.resolutions[sym] = ResolvedPrice(
                    sym, px, PriceStatus.STALE, as_of, f"Last bar {age} calendar day(s) old"
                )
            else:
                out.resolutions[sym] = ResolvedPrice(sym, px, PriceStatus.VALID, as_of)
            out.prices[sym] = px
        except Exception as exc:  # noqa: BLE001 — aggregate per-symbol failures
            out.resolutions[sym] = ResolvedPrice(sym, None, PriceStatus.UNAVAILABLE, None, str(exc))
            if not strict:
                continue
    if strict and out.unavailable_symbols():
        raise HalalQuantError(
            "Cannot value portfolio: missing market prices",
            status_code=422,
            code="valuation_incomplete",
        )
    return out


def sleeve_equity(
    sleeve_name: str,
    allocated: Decimal,
    cash: Decimal,
    reserved: Decimal,
    holdings: list[SleeveHolding],
    prices: dict[str, Decimal],
) -> Decimal:
    snap = sleeve_snapshot(sleeve_name, allocated, cash, reserved, holdings, prices)
    return money(snap.market_value + snap.available_cash + snap.reserved_cash)


def compute_portfolio_valuation(
    state: BookState,
    resolution: PriceResolution,
) -> dict:
    """Build valuation metrics from book state and resolved prices."""
    cfg = get_risk_config()
    prices = resolution.prices
    summary = build_summary(
        total_capital=state.total_capital,
        balances=state.balances,
        reserved=state.reserved,
        holdings_swing=state.holdings_swing,
        holdings_pos=state.holdings_positional,
        prices=prices,
        realized_pnl=state.realized_pnl,
        peak_value=state.peak_value,
        drawdown_locked=state.drawdown_locked,
        swing_alloc=cfg.swing_capital_pct,
        pos_alloc=cfg.positional_capital_pct,
    )
    reserved_total = money(
        state.reserved.get("swing", D(0)) + state.reserved.get("positional", D(0))
    )
    swing_eq = sleeve_equity(
        "swing",
        state.total_capital * cfg.swing_capital_pct,
        summary.swing.available_cash,
        summary.swing.reserved_cash,
        state.holdings_swing,
        prices,
    )
    pos_eq = sleeve_equity(
        "positional",
        state.total_capital * cfg.positional_capital_pct,
        summary.positional.available_cash,
        summary.positional.reserved_cash,
        state.holdings_positional,
        prices,
    )
    peak_prior = state.peak_value
    equity = summary.portfolio_value
    peak_after = money(max(peak_prior, equity))
    dd_amt = money(max(D(0), peak_after - equity))
    dd_pct = drawdown_pct(equity, peak_after)
    total_pnl = money(summary.realized_pnl + summary.unrealized_pnl)
    return {
        "summary": summary,
        "portfolio_equity": equity,
        "available_cash": summary.available_cash,
        "reserved_cash": reserved_total,
        "invested_market_value": summary.market_value,
        "realized_pnl": summary.realized_pnl,
        "unrealized_pnl": summary.unrealized_pnl,
        "total_pnl": total_pnl,
        "swing_equity": swing_eq,
        "positional_equity": pos_eq,
        "cash_reserve": summary.cash_reserve,
        "equity_peak_prior": peak_prior,
        "equity_peak_at_snapshot": peak_after,
        "drawdown_amount": dd_amt,
        "drawdown_pct": dd_pct,
        "price_quality": resolution.to_audit_json(),
        "valuation_complete": resolution.complete,
    }


def unrealized_for_holding(h: SleeveHolding, prices: dict[str, Decimal]) -> Decimal:
    sym = h.symbol.upper()
    if sym not in prices:
        return D(0)
    mv = holding_market_value(h, prices[sym])
    return money(mv - D(h.quantity) * D(h.average_entry))