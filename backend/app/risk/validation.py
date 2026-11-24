from __future__ import annotations

from decimal import Decimal

from app.portfolio.exposure import exposure_by_sector, exposure_by_stock, exposure_pct
from app.portfolio.money import D
from app.portfolio.schemas import AllocationProposal, SleeveHolding
from app.portfolio.sectors import sector_for
from app.risk.limits import limits_for_sleeve
from app.risk.liquidity import liquidity_check
from app.risk.schemas import RiskConfiguration, ValidationResult


def validate_allocation(
    proposal: AllocationProposal,
    *,
    sleeve_equity: Decimal,
    sleeve_holdings: list[SleeveHolding],
    all_holdings: list[SleeveHolding],
    combined_equity: Decimal,
    open_risk_total: Decimal,
    prices: dict[str, Decimal],
    df,
    cfg: RiskConfiguration,
    drawdown_locked: bool,
) -> ValidationResult:
    limits = limits_for_sleeve(proposal.sleeve, cfg)
    rejections: list[str] = list(proposal.rejections)
    warnings: list[str] = list(proposal.warnings)

    if drawdown_locked:
        rejections.append("Portfolio drawdown lock active — new allocations blocked")

    if proposal.quantity <= 0:
        rejections.append("Quantity must be positive")

    stock_exp = exposure_by_stock(sleeve_holdings, prices)
    sym_val = stock_exp.get(proposal.symbol.upper(), D(0)) + proposal.notional
    sym_pct = exposure_pct(sym_val, sleeve_equity)
    if sym_pct > limits.max_stock_exposure_pct:
        rejections.append(f"Stock exposure {sym_pct:.2%} exceeds {limits.max_stock_exposure_pct:.2%}")

    sector = sector_for(proposal.symbol) or "UNCLASSIFIED"
    sec_exp = exposure_by_sector(sleeve_holdings, prices)
    sec_val = sec_exp.get(sector, D(0)) + proposal.notional
    cap = limits.max_sector_exposure_pct
    if sector == "UNCLASSIFIED":
        cap = min(cap, cfg.swing.unclassified_sector_cap_pct)  # conservative
    if exposure_pct(sec_val, sleeve_equity) > cap:
        rejections.append(f"Sector {sector} exposure exceeds limit")

    if len(sleeve_holdings) >= limits.max_open_positions:
        rejections.append("Maximum open positions for sleeve")

    for h in sleeve_holdings:
        if h.symbol.upper() == proposal.symbol.upper():
            rejections.append("Duplicate holding in sleeve")

    new_open = open_risk_total + proposal.risk_amount
    if combined_equity > 0 and (new_open / combined_equity) > limits.max_portfolio_open_risk_pct:
        rejections.append("Combined open risk limit breached")

    ok_liq, liq_notes, liq_metrics = liquidity_check(
        proposal.quantity, proposal.entry_reference, df, limits.max_adv_participation_pct
    )
    if not ok_liq:
        rejections.extend(liq_notes)
    warnings.extend([n for n in liq_notes if n not in rejections])

    approved = len(rejections) == 0 and proposal.quantity > 0
    return ValidationResult(
        approved=approved,
        rejections=rejections,
        warnings=warnings,
        metrics={
            "stock_exposure_pct": float(sym_pct),
            "sector": sector,
            "liquidity": liq_metrics,
        },
    )