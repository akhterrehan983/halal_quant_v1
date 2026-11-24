from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.core.exceptions import HalalQuantError
from app.market_data.repository import SymbolNotFoundError, get_history_dataframe, iter_symbol_histories
from app.signals.generator import generate_batch, generate_unified_signal
from app.signals.persistence import get_signal_by_id, list_persisted_signals, persist_signal, signal_history
from app.signals.ranking import rank_signals
from app.strategies.engine import evaluate_all

router = APIRouter(tags=["signals"])


class GenerateRequest(BaseModel):
    symbol: str | None = None
    symbols: list[str] | None = None
    horizon: str = "swing"
    persist: bool = True


@router.post("/signals/generate")
def generate_signals(body: GenerateRequest | None = None, horizon: str | None = None):
    """Generate unified research signals (M4). Legacy query horizon still accepted."""
    req = body or GenerateRequest(horizon=horizon or "swing")
    hz = req.horizon
    if hz not in ("swing", "positional"):
        raise HTTPException(400, "horizon must be swing or positional")
    pairs = []
    if req.symbol:
        try:
            pairs.append((req.symbol.upper(), get_history_dataframe(req.symbol, limit=520)))
        except SymbolNotFoundError:
            raise HTTPException(404, "Unknown symbol") from None
    else:
        symbols = req.symbols
        for sym, df in iter_symbol_histories():
            if symbols and sym not in [s.upper() for s in symbols]:
                continue
            pairs.append((sym, df))
    generated = generate_batch(pairs, hz)
    ranked = rank_signals(generated)
    if req.persist:
        ranked = [persist_signal(s) for s in ranked]
    return {
        "horizon": hz,
        "count": len(ranked),
        "signals": [s.model_dump(mode="json") for s in ranked],
        "notice": "Research candidates only — not executed trades.",
    }


@router.post("/signals/generate/batch")
def generate_batch_endpoint(body: GenerateRequest):
    return generate_signals(body)


@router.get("/signals")
def list_signals(
    horizon: str = "swing",
    min_score: int = 0,
    mode: str = "legacy",
    symbol: str | None = None,
    category: str | None = None,
    lifecycle: str | None = None,
):
    if horizon not in ("swing", "positional"):
        raise HTTPException(400, "horizon must be swing or positional")
    if mode == "unified":
        items = list_persisted_signals(symbol=symbol, horizon=horizon, lifecycle=lifecycle, category=category)
        items = [s for s in items if s.overall_score >= min_score]
        return {"horizon": horizon, "mode": "unified", "items": [s.model_dump(mode="json") for s in items], "total": len(items)}

    rows = []
    for sym, df in iter_symbol_histories():
        if symbol and sym != symbol.upper():
            continue
        try:
            strategies, _ = evaluate_all(df, horizon)
        except ValueError:
            continue
        for s in strategies:
            if s["score"] >= min_score:
                rows.append({"symbol": sym, "horizon": horizon, **s})
    rows.sort(key=lambda x: x["score"], reverse=True)
    return {"horizon": horizon, "mode": "legacy", "items": rows, "total": len(rows)}


@router.get("/signals/rankings")
def signal_rankings(horizon: str = "swing", limit: int = 50):
    stored = list_persisted_signals(horizon=horizon, lifecycle="ACTIVE")
    ranked = rank_signals(stored)[:limit]
    return {"horizon": horizon, "items": [s.model_dump(mode="json") for s in ranked], "total": len(ranked)}


@router.get("/signals/{signal_id}")
def get_signal(signal_id: int):
    try:
        sig = get_signal_by_id(signal_id)
    except HalalQuantError as e:
        raise HTTPException(e.status_code, e.message) from e
    return sig.model_dump(mode="json")


@router.get("/signals/{signal_id}/history")
def get_signal_lifecycle_history(signal_id: int):
    try:
        get_signal_by_id(signal_id)
    except HalalQuantError as e:
        raise HTTPException(e.status_code, e.message) from e
    return {"signal_id": signal_id, "events": signal_history(signal_id)}