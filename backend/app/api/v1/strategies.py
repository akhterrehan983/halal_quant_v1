from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.market_data.repository import SymbolNotFoundError, get_history_dataframe
from app.strategies.config import STRATEGY_DESCRIPTIONS, get_horizon_config
from app.strategies.evaluator import evaluate_all_strategies, evaluate_strategy
from app.strategies.registry import get_strategy, is_enabled, list_strategies, set_enabled

router = APIRouter(tags=["strategies"])


class EvaluateRequest(BaseModel):
    symbol: str
    horizon: str = "swing"
    symbols: list[str] | None = None


class StrategyToggle(BaseModel):
    enabled: bool


@router.get("/strategies")
def strategies_list():
    items = []
    for s in list_strategies():
        items.append(
            {
                "id": s.strategy_id,
                "name": s.legacy_name,
                "description": STRATEGY_DESCRIPTIONS.get(s.strategy_id, s.description),
                "version": "0.3.0",
                "enabled": is_enabled(s.strategy_id),
                "profiles": ["swing", "positional"],
                "required_features": sorted(s.required_features),
            }
        )
    return {"items": items, "total": len(items)}


@router.get("/strategies/{strategy_id}")
def strategy_detail(strategy_id: str, horizon: str = "swing"):
    strategy = get_strategy(strategy_id)
    if not strategy:
        raise HTTPException(404, "Strategy not found")
    cfg = get_horizon_config(horizon)
    return {
        "id": strategy.strategy_id,
        "name": strategy.legacy_name,
        "description": STRATEGY_DESCRIPTIONS.get(strategy_id, strategy.description),
        "enabled": is_enabled(strategy_id),
        "horizon": horizon,
        "parameters": cfg.__dict__,
        "required_features": sorted(strategy.required_features),
    }


@router.patch("/strategies/{strategy_id}")
def strategy_toggle(strategy_id: str, body: StrategyToggle):
    try:
        set_enabled(strategy_id, body.enabled)
    except KeyError:
        raise HTTPException(404, "Strategy not found") from None
    return {"id": strategy_id, "enabled": body.enabled}


@router.post("/strategies/{strategy_id}/evaluate")
def evaluate_one(strategy_id: str, body: EvaluateRequest):
    if body.horizon not in ("swing", "positional"):
        raise HTTPException(400, "horizon must be swing or positional")
    try:
        df = get_history_dataframe(body.symbol, limit=520)
    except SymbolNotFoundError:
        raise HTTPException(404, "Unknown symbol") from None
    try:
        result = evaluate_strategy(strategy_id, body.symbol, df, body.horizon)
    except KeyError:
        raise HTTPException(404, "Strategy not found") from None
    if not is_enabled(strategy_id):
        raise HTTPException(400, "Strategy is disabled")
    return result.to_api_dict()


@router.post("/strategies/evaluate")
def evaluate_many(body: EvaluateRequest):
    if body.horizon not in ("swing", "positional"):
        raise HTTPException(400, "horizon must be swing or positional")
    symbols = body.symbols or [body.symbol]
    output = []
    for sym in symbols:
        try:
            df = get_history_dataframe(sym, limit=520)
        except SymbolNotFoundError:
            continue
        results = evaluate_all_strategies(sym, df, body.horizon)
        output.append(
            {
                "symbol": sym.upper(),
                "horizon": body.horizon,
                "strategies": [r.to_api_dict() for r in results],
            }
        )
    return {"count": len(output), "results": output}