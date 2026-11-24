from __future__ import annotations

from decimal import Decimal

from app.portfolio.money import D
from app.portfolio.schemas import AllocationProposal
from app.risk.drawdown import breach_drawdown, breach_daily_loss
from app.risk.schemas import RiskConfiguration, RiskEvent, ValidationResult
from app.risk.validation import validate_allocation
from app.portfolio import store


def get_config() -> RiskConfiguration:
    return store.get_risk_config()


def update_config(cfg: RiskConfiguration) -> RiskConfiguration:
    cfg.validate_allocations()
    store.save_risk_config(cfg)
    return cfg


def check_portfolio_controls(state, daily_pnl: Decimal | None = None) -> list[RiskEvent]:
    cfg = store.get_risk_config()
    events: list[RiskEvent] = []
    prices = store.mark_prices()
    summary = store.build_summary_from_state(state, prices)
    swing_lim = cfg.swing
    if breach_drawdown(summary.current_drawdown_pct, swing_lim.max_drawdown_pct):
        if not state.drawdown_locked:
            state.drawdown_locked = True
            ev = store.record_risk_event(
                state,
                "DRAWDOWN_LOCK",
                "Max portfolio drawdown breached",
                {"drawdown_pct": float(summary.current_drawdown_pct)},
            )
            events.append(ev)
    if daily_pnl is not None and breach_daily_loss(daily_pnl, summary.portfolio_value, swing_lim.max_daily_loss_pct):
        events.append(
            store.record_risk_event(
                state,
                "DAILY_LOSS",
                "Daily loss limit breached",
                {"daily_pnl": str(daily_pnl)},
            )
        )
    return events


def validate_proposal(proposal: AllocationProposal) -> ValidationResult:
    state = store.load_book()
    prices = store.mark_prices()
    cfg = get_config()
    summary = store.build_summary_from_state(state, prices, persist=False)
    sleeve_holdings = state.holdings_for(proposal.sleeve)
    all_holdings = state.all_holdings()
    sleeve_equity = summary.swing.allocated_capital if proposal.sleeve == "swing" else summary.positional.allocated_capital
    df = store.get_history(proposal.symbol)
    return validate_allocation(
        proposal,
        sleeve_equity=sleeve_equity,
        sleeve_holdings=sleeve_holdings,
        all_holdings=all_holdings,
        combined_equity=summary.portfolio_value,
        open_risk_total=summary.open_risk,
        prices=prices,
        df=df,
        cfg=cfg,
        drawdown_locked=state.drawdown_locked,
    )


def exposure_report() -> dict:
    state = store.load_book()
    prices = store.mark_prices()
    from app.portfolio.exposure import exposure_by_sector, exposure_by_stock

    holdings = state.all_holdings()
    return {
        "by_stock": {k: float(v) for k, v in exposure_by_stock(holdings, prices).items()},
        "by_sector": {k: float(v) for k, v in exposure_by_sector(holdings, prices).items()},
        "open_risk": float(store.build_summary_from_state(state, prices, persist=False).open_risk),
        "drawdown_locked": state.drawdown_locked,
    }