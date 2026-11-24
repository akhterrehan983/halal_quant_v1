from app.risk.schemas import RiskConfiguration, SleeveRiskLimits

DEFAULT_RISK_CONFIG = RiskConfiguration()
DEFAULT_RISK_CONFIG.validate_allocations()


def limits_for_sleeve(sleeve: str, cfg: RiskConfiguration = DEFAULT_RISK_CONFIG) -> SleeveRiskLimits:
    if sleeve == "positional":
        return cfg.positional
    return cfg.swing