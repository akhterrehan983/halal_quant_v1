from app.backtesting.schemas import CostScenario
from app.execution.costs import CostConfig, transaction_costs


def scenario_config(scenario: CostScenario) -> CostConfig:
    if scenario == CostScenario.ZERO:
        return CostConfig(zero_cost_demo=True)
    if scenario == CostScenario.CONSERVATIVE:
        return CostConfig(zero_cost_demo=False, brokerage_pct=__import__("decimal").Decimal("0.001"))
    return CostConfig(zero_cost_demo=False)


def buy_cost(notional, scenario: CostScenario):
    return transaction_costs(notional, "BUY", scenario_config(scenario))


def sell_cost(notional, scenario: CostScenario):
    return transaction_costs(notional, "SELL", scenario_config(scenario))