"""Parameter sensitivity — varies simulator knobs that change entries/exits."""

from app.backtesting.schemas import BacktestConfig
from app.backtesting.simulator import run_backtest


def sensitivity_grid(
    config: BacktestConfig,
    *,
    hold_days_grid: list[int] | None = None,
    min_score_grid: list[int] | None = None,
) -> dict:
    hold_days_grid = hold_days_grid or [8, 10, 15]
    min_score_grid = min_score_grid or [55, 65, 75]
    rows = []
    for hold in hold_days_grid:
        c = config.model_copy()
        c.name = f"{config.name}_hold_{hold}"
        c.hold_days = hold
        run = run_backtest(c)
        rows.append(
            {
                "parameter": "hold_days",
                "value": hold,
                "behavior": "Earlier/later time-exit after sell authorization in simulator",
                "metrics": run.metrics.model_dump(mode="json") if run.metrics else None,
            }
        )
    for score in min_score_grid:
        c = config.model_copy()
        c.name = f"{config.name}_min_score_{score}"
        c.min_signal_score = score
        run = run_backtest(c)
        rows.append(
            {
                "parameter": "min_signal_score",
                "value": score,
                "behavior": "Filters unified BUY/STRONG_BUY candidates below threshold",
                "metrics": run.metrics.model_dump(mode="json") if run.metrics else None,
            }
        )
    return {
        "grid": rows,
        "notice": "Each row re-runs the event simulator with a different hold_days or min_signal_score.",
    }