from __future__ import annotations

from datetime import datetime

from app.portfolio import store
from app.portfolio.money import D
from app.portfolio.schemas import ProposalStatus, RebalanceProposal
from app.risk.limits import DEFAULT_RISK_CONFIG


def propose_rebalance() -> RebalanceProposal:
    state = store.load_book()
    cfg = store.get_risk_config()
    prices = store.mark_prices()
    summary = store.build_summary_from_state(state, prices)
    actions: list[dict] = []
    reserve_target = state.total_capital * cfg.cash_reserve_pct
    if summary.cash_reserve < reserve_target:
        shortfall = reserve_target - summary.cash_reserve
        actions.append(
            {
                "type": "INCREASE_RESERVE",
                "amount_rupees": float(shortfall),
                "reason": "Cash reserve below configured minimum",
            }
        )

    sw_target = state.total_capital * cfg.swing_capital_pct
    po_target = state.total_capital * cfg.positional_capital_pct
    sw_gap = sw_target - (summary.swing.market_value + summary.swing.available_cash)
    po_gap = po_target - (summary.positional.market_value + summary.positional.available_cash)
    if abs(sw_gap) > sw_target * D("0.05"):
        actions.append({"type": "SLEEVE_DRIFT", "sleeve": "swing", "gap_rupees": float(sw_gap)})
    if abs(po_gap) > po_target * D("0.05"):
        actions.append({"type": "SLEEVE_DRIFT", "sleeve": "positional", "gap_rupees": float(po_gap)})

    from app.portfolio.exposure import exposure_by_stock

    stock_exp = exposure_by_stock(state.all_holdings(), prices)
    for sym, val in stock_exp.items():
        pct = val / summary.portfolio_value if summary.portfolio_value > 0 else D(0)
        if pct > DEFAULT_RISK_CONFIG.swing.max_stock_exposure_pct:
            actions.append({"type": "CONCENTRATION", "symbol": sym, "exposure_pct": float(pct)})

    prop = RebalanceProposal(
        status=ProposalStatus.PENDING,
        actions=actions,
        reason="Automated research rebalance scan — proposals only",
        created_at=datetime.utcnow(),
    )
    state.rebalance.insert(0, prop)
    store.save_book(state)
    return prop