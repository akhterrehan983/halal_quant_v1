from __future__ import annotations

from datetime import date

from app.backtesting.schemas import BacktestConfig, BacktestRun
from app.backtesting.simulator import run_backtest


def walk_forward(config: BacktestConfig, folds: list[dict]) -> dict:
    """Chronological folds: each {train_end, val_end, test_end} dates as ISO strings."""
    results = []
    for fold in folds:
        c = config.model_copy()
        c.start_date = date.fromisoformat(fold["train_start"])
        c.end_date = date.fromisoformat(fold["test_end"])
        c.name = f"{config.name}_wf_{fold.get('label', '')}"
        run = run_backtest(c)
        results.append(
            {
                "fold": fold,
                "metrics": run.metrics.model_dump(mode="json") if run.metrics else None,
                "status": run.status.value,
            }
        )
    return {"folds": results, "notice": "Out-of-sample segments embedded per fold end_date"}