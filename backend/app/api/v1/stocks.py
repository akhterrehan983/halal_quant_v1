from fastapi import APIRouter, HTTPException

from app.market_data.repository import SymbolNotFoundError, get_history_dataframe, list_universe_symbols, symbol_metadata
from app.strategies.engine import evaluate_all

router = APIRouter(tags=["stocks"])


@router.get("/stocks")
def list_stocks():
    items = []
    for s in list_universe_symbols():
        try:
            meta = symbol_metadata(s)
            items.append(
                {
                    "symbol": s,
                    "exchange": "NSE",
                    "data_source": meta.get("source"),
                    "is_synthetic": meta.get("is_synthetic", False),
                    "shariah_status": meta.get("shariah_status", "UNVERIFIED"),
                }
            )
        except KeyError:
            continue
    return {"items": items, "total": len(items)}


@router.get("/stocks/{symbol}")
def stock_detail(symbol: str, horizon: str = "swing"):
    symbol = symbol.upper()
    if horizon not in ("swing", "positional"):
        raise HTTPException(400, "horizon must be swing or positional")
    try:
        meta = symbol_metadata(symbol)
        df = get_history_dataframe(symbol, limit=520)
    except SymbolNotFoundError:
        raise HTTPException(404, "Unknown symbol") from None
    results, features = evaluate_all(df, horizon)
    last = df.iloc[-1]
    return {
        "symbol": symbol,
        "exchange": "NSE",
        "last_close": round(float(last.close), 2),
        "horizon": horizon,
        "features": features,
        "strategies": results,
        "shariah_status": meta.get("shariah_status", "UNVERIFIED"),
        "data_source": meta.get("source"),
    }