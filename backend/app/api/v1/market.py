from fastapi import APIRouter, HTTPException

from app.market_data.repository import SymbolNotFoundError, get_history_dataframe, iter_symbol_histories
from app.strategies.engine import evaluate_all

router = APIRouter(tags=["market"])


@router.get("/market-data/{symbol}")
def market_data(symbol: str, limit: int = 260):
    symbol = symbol.upper()
    try:
        df = get_history_dataframe(symbol, limit=min(max(limit, 60), 520))
        meta_source = "postgresql" if len(df) else "unknown"
    except SymbolNotFoundError:
        raise HTTPException(404, "Unknown symbol") from None
    from app.market_data.repository import symbol_metadata

    try:
        meta = symbol_metadata(symbol)
        meta_source = meta.get("source", meta_source)
        is_synthetic = meta.get("is_synthetic", False)
    except KeyError:
        is_synthetic = True
        meta_source = "demo"
    return {
        "symbol": symbol,
        "exchange": "NSE",
        "data_source": meta_source,
        "is_synthetic": is_synthetic,
        "candles": [
            {
                "trading_date": r.date.strftime("%Y-%m-%d"),
                "open": round(r.open, 2),
                "high": round(r.high, 2),
                "low": round(r.low, 2),
                "close": round(r.close, 2),
                "volume": int(r.volume),
            }
            for r in df.itertuples()
        ],
    }


@router.get("/market/regime")
def market_regime():
    from app.regime.classifier import classify_market

    c = classify_market()
    return c.model_dump(mode="json")