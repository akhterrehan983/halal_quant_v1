from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.backtesting.monte_carlo import monte_carlo_trade_returns
from app.backtesting.schemas import BacktestConfig, BacktestRun, BacktestStatus
from app.backtesting.simulator import run_backtest
from app.backtesting import store
from app.backtesting.validation_sensitivity import sensitivity_grid
from app.backtesting.walk_forward import walk_forward

router = APIRouter(tags=["backtests"])


class WalkForwardBody(BaseModel):
    folds: list[dict]


@router.post("/backtests")
def create_backtest(config: BacktestConfig, run_now: bool = False):
    run = BacktestRun(config=config)
    run = store.save_run(run)
    if run_now:
        try:
            result = run_backtest(config)
            result.backtest_id = run.backtest_id
            return store.save_run(result).model_dump(mode="json")
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
    return run.model_dump(mode="json")


@router.get("/backtests")
def list_backtests():
    return {"items": [r.model_dump(mode="json") for r in store.list_runs()]}


@router.get("/backtests/{backtest_id}")
def get_backtest(backtest_id: int):
    run = store.get_run(backtest_id)
    if not run:
        raise HTTPException(404, "Not found")
    return run.model_dump(mode="json")


@router.post("/backtests/{backtest_id}/run")
def execute_backtest(backtest_id: int):
    prev = store.get_run(backtest_id)
    if not prev:
        raise HTTPException(404, "Not found")
    prev.status = BacktestStatus.RUNNING
    store.save_run(prev)
    try:
        result = run_backtest(prev.config)
        result.backtest_id = backtest_id
        return store.save_run(result).model_dump(mode="json")
    except ValueError as e:
        prev.status = BacktestStatus.FAILED
        prev.warnings.append(str(e))
        store.save_run(prev)
        raise HTTPException(400, str(e)) from e


@router.get("/backtests/{backtest_id}/summary")
def summary(backtest_id: int):
    run = store.get_run(backtest_id)
    if not run or not run.metrics:
        raise HTTPException(404, "No results")
    return {"metrics": run.metrics.model_dump(mode="json"), "warnings": run.warnings}


@router.get("/backtests/{backtest_id}/equity-curve")
def equity_curve(backtest_id: int):
    run = store.get_run(backtest_id)
    if not run:
        raise HTTPException(404, "Not found")
    return {"points": [p.model_dump(mode="json") for p in run.equity_curve]}


@router.get("/backtests/{backtest_id}/drawdown")
def drawdown(backtest_id: int):
    run = store.get_run(backtest_id)
    if not run:
        raise HTTPException(404, "Not found")
    return {"points": [{"date": p.date.isoformat(), "drawdown": str(p.drawdown)} for p in run.equity_curve]}


@router.get("/backtests/{backtest_id}/trades")
def trades(backtest_id: int):
    run = store.get_run(backtest_id)
    if not run:
        raise HTTPException(404, "Not found")
    return {"trades": [t.model_dump(mode="json") for t in run.trades]}


@router.get("/backtests/{backtest_id}/metrics")
def metrics(backtest_id: int):
    return summary(backtest_id)


@router.get("/backtests/{backtest_id}/validation")
def validation(backtest_id: int):
    run = store.get_run(backtest_id)
    if not run:
        raise HTTPException(404, "Not found")
    return run.validation or {}


@router.post("/backtests/{backtest_id}/walk-forward")
def wf(backtest_id: int, body: WalkForwardBody):
    run = store.get_run(backtest_id)
    if not run:
        raise HTTPException(404, "Not found")
    return walk_forward(run.config, body.folds)


@router.post("/backtests/{backtest_id}/sensitivity")
def sensitivity(backtest_id: int):
    run = store.get_run(backtest_id)
    if not run:
        raise HTTPException(404, "Not found")
    return sensitivity_grid(run.config)


@router.post("/backtests/{backtest_id}/monte-carlo")
def mc(backtest_id: int, simulations: int = 200):
    run = store.get_run(backtest_id)
    if not run:
        raise HTTPException(404, "Not found")
    return monte_carlo_trade_returns(run.trades, simulations=simulations, seed=run.config.random_seed)