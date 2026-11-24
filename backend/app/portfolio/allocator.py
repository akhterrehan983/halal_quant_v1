from __future__ import annotations

from datetime import date

from app.portfolio import store
from app.portfolio.money import D
from app.portfolio.position_sizing import compute_position_quantity
from app.portfolio.schemas import AllocationProposal, ProposalStatus
from app.risk.limits import limits_for_sleeve
from app.risk.manager import validate_proposal
from app.risk.stop_loss import resolve_stop_reference
from app.signals.persistence import list_persisted_signals
from app.signals.schemas import SignalCategory


def eligible_signals(horizon: str | None = None) -> list:
    cats = (SignalCategory.BUY, SignalCategory.STRONG_BUY)
    active = list_persisted_signals(lifecycle="ACTIVE", horizon=horizon)
    return [s for s in active if s.category in cats]


def build_proposal_from_signal(signal) -> AllocationProposal:
    cfg = store.get_risk_config()
    sleeve = signal.horizon
    limits = limits_for_sleeve(sleeve, cfg)
    state = store.load_book()
    prices = store.mark_prices()
    summary = store.build_summary_from_state(state, prices, persist=False)
    sleeve_snap = summary.swing if sleeve == "swing" else summary.positional
    available = sleeve_snap.available_cash

    df = store.get_history(signal.symbol)
    entry = D(signal.entry_reference)
    stop, stop_src = resolve_stop_reference(entry, signal.stop_reference, df)
    proposal = AllocationProposal(
        signal_id=signal.signal_id,
        symbol=signal.symbol,
        sleeve=sleeve,
        entry_reference=entry,
        stop_reference=stop or D(0),
        target_reference=D(signal.target_reference) if signal.target_reference else None,
        risk_per_trade_pct=limits.risk_per_trade_pct,
    )
    if stop is None:
        proposal.rejections.append("No valid stop reference (signal, ATR, or structure)")
        proposal.status = ProposalStatus.REJECTED
        return proposal

    max_stock_val = sleeve_snap.allocated_capital * limits.max_stock_exposure_pct
    sizing = compute_position_quantity(
        sleeve_equity=sleeve_snap.allocated_capital,
        risk_per_trade_pct=limits.risk_per_trade_pct,
        entry_price=entry,
        stop_price=stop,
        available_cash=available,
        max_position_value=max_stock_val,
    )
    proposal.quantity = sizing.quantity
    proposal.notional = sizing.notional
    proposal.risk_amount = sizing.risk_amount
    proposal.rejections.extend(sizing.rejections)
    proposal.exposure_checks = sizing.diagnostics
    proposal.exposure_checks["stop_source"] = stop_src

    val = validate_proposal(proposal)
    proposal.rejections = val.rejections
    proposal.warnings = val.warnings
    proposal.validations = ["passed"] if val.approved else []
    proposal.status = ProposalStatus.PENDING if val.approved else ProposalStatus.REJECTED
    return proposal


def generate_allocation_proposals(*, horizon: str | None = None, limit: int = 20) -> list[AllocationProposal]:
    state = store.load_book()
    from app.risk.manager import check_portfolio_controls

    check_portfolio_controls(state)
    if state.drawdown_locked:
        return []
    out: list[AllocationProposal] = []
    for sig in eligible_signals(horizon)[: limit * 2]:
        prop = build_proposal_from_signal(sig)
        prop = store.persist_proposal(prop)
        if prop.status != ProposalStatus.REJECTED or prop.rejections:
            out.append(prop)
        if len(out) >= limit:
            break
    return out