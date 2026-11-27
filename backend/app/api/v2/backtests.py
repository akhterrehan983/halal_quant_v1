"""Walk-forward v2 endpoints (M14 Phase 2). v1 endpoints are unchanged.

Errors: 422 request-shape validation, 400 invalid folds / run budget / incomplete segment, 404 unknown backtest.
Results are returned, not persisted, and never touch the live portfolio.
"""

from fastapi import APIRouter, HTTPException

from app.backtesting import store
from app.backtesting.schemas import BacktestConfig
from app.backtesting.walk_forward_schemas import WalkForwardStatelessV2Request, WalkForwardV2Request
from app.backtesting.walk_forward_v2 import (
    WalkForwardValidationError,
    execute_plan,
    plan_walk_forward,
)

router = APIRouter(tags=["backtests-v2"])


def _run(base_config: BacktestConfig, request: WalkForwardV2Request) -> dict:
    try:
        plan = plan_walk_forward(base_config, request)
        response = execute_plan(plan)
    except WalkForwardValidationError as e:
        raise HTTPException(400, str(e)) from e
    return response.model_dump(mode="json")


@router.post("/backtests/walk-forward")
def walk_forward_stateless(body: WalkForwardStatelessV2Request):
    base = body.base_config
    request = WalkForwardV2Request(**body.model_dump(exclude={"base_config"}))
    return _run(base, request)


@router.post("/backtests/{backtest_id}/walk-forward")
def walk_forward_for_backtest(backtest_id: int, body: WalkForwardV2Request):
    prev = store.get_run(backtest_id)
    if not prev:
        raise HTTPException(404, "Not found")
    return _run(prev.config, body)
