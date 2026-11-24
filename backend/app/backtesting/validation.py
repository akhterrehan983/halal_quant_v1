from __future__ import annotations

from app.backtesting.schemas import BacktestConfig, BacktestRun


def build_validation_report(run: BacktestRun) -> dict:
    warnings = list(run.warnings)
    cfg = run.config
    warnings.append(
        "Settlement dates use business-day approximation — not authoritative NSE holiday calendar."
    )
    if cfg.universe_mode == "current_snapshot_with_survivorship_warning":
        warnings.append("Survivorship bias: backtest uses current universe membership.")
    if cfg.shariah_mode.value == "RESEARCH_ONLY":
        warnings.append("RESEARCH_ONLY Shariah mode — results not Shariah-validated.")
    return {
        "warnings": warnings,
        "look_ahead_protections": [
            "Signals evaluated with as_of_index",
            "Fills on session after signal date open",
            "No signal-close fills",
        ],
        "shariah_mode": cfg.shariah_mode.value,
    }