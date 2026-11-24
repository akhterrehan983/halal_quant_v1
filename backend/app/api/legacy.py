"""Legacy v0.1 API — preserved for backward compatibility with the React dashboard."""

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.exceptions import HalalQuantError
from app.market_data.ingestion import ingest_csv_bytes
from app.market_data.repository import SymbolNotFoundError, get_history_dataframe, iter_symbol_histories
from app.market_data.repository import last_close_prices, list_universe_symbols, symbol_metadata
from app.portfolio.compat import legacy_portfolio_snapshot

LEGACY_TRADE_BLOCKED = (
    "Legacy paper BUY/SELL is disabled. Use POST /api/v1/execution/orders with Shariah, risk and ownership checks."
)
from app.strategies.engine import evaluate_all

router = APIRouter(tags=["legacy-v0"])


class TradeRequest(BaseModel):
    symbol: str
    quantity: int = Field(gt=0)
    price: float = Field(gt=0)


@router.get("/api/health")
def health():
    return {
        "status": "ok",
        "app": settings.app_name,
        "version": settings.version,
        "database_enabled": settings.database_enabled,
    }


@router.get("/api/universe")
def universe():
    items = []
    for s in list_universe_symbols():
        try:
            meta = symbol_metadata(s)
            items.append(
                {
                    "symbol": s,
                    "source": meta.get("source", "unknown"),
                    "shariah_status": meta.get("shariah_status", "UNVERIFIED"),
                }
            )
        except KeyError:
            continue
    return {"symbols": items}


@router.get("/api/history/{symbol}")
def history(symbol: str, limit: int = 260):
    symbol = symbol.upper()
    try:
        df = get_history_dataframe(symbol, limit=min(max(limit, 60), 520))
    except SymbolNotFoundError:
        raise HTTPException(404, "Unknown symbol. Use the demo universe or upload a CSV.") from None
    return {
        "symbol": symbol,
        "data": [
            {
                "date": r.date.strftime("%Y-%m-%d"),
                "open": round(r.open, 2),
                "high": round(r.high, 2),
                "low": round(r.low, 2),
                "close": round(r.close, 2),
                "volume": int(r.volume),
            }
            for r in df.itertuples()
        ],
    }


@router.get("/api/signals/{symbol}")
def signals(symbol: str, horizon: str = "swing"):
    symbol = symbol.upper()
    if horizon not in ("swing", "positional"):
        raise HTTPException(400, "horizon must be swing or positional")
    try:
        df = get_history_dataframe(symbol, limit=520)
    except SymbolNotFoundError:
        raise HTTPException(404, "Unknown symbol") from None
    results, features = evaluate_all(df, horizon)
    notice = (
        "Signals are educational rule-based outputs on synthetic demo data, not investment advice."
        if symbol_metadata(symbol).get("is_synthetic")
        else "Signals are rule-based research outputs; verify data source and Shariah eligibility."
    )
    return {
        "symbol": symbol,
        "horizon": horizon,
        "features": features,
        "strategies": results,
        "notice": notice,
    }


@router.get("/api/scan")
def scan(horizon: str = "swing"):
    if horizon not in ("swing", "positional"):
        raise HTTPException(400, "horizon must be swing or positional")
    rows = []
    for symbol, df in iter_symbol_histories():
        try:
            strategies, features = evaluate_all(df, horizon)
        except ValueError:
            continue
        active = [s for s in strategies if s["signal"] in ("BUY", "WATCHLIST")]
        best = max(active, key=lambda s: s["score"]) if active else max(strategies, key=lambda s: s["score"])
        rows.append(
            {
                "symbol": symbol,
                "price": features["close"],
                "regime": features["regime"],
                "best_strategy": best["strategy"],
                "signal": best["signal"],
                "score": best["score"],
                "return_3m": features["return_3m"],
            }
        )
    return {"horizon": horizon, "results": sorted(rows, key=lambda x: x["score"], reverse=True)}


@router.get("/api/portfolio")
def get_portfolio():
    return legacy_portfolio_snapshot()


@router.post("/api/portfolio/buy")
def buy(req: TradeRequest):
    raise HTTPException(403, LEGACY_TRADE_BLOCKED)


@router.post("/api/portfolio/sell")
def sell(req: TradeRequest):
    raise HTTPException(403, LEGACY_TRADE_BLOCKED)


@router.post("/api/data/upload")
async def upload_csv(file: UploadFile = File(...)):
    """Upload OHLCV CSV. Required columns: date, open, high, low, close, volume."""
    try:
        content = await file.read()
        summary = ingest_csv_bytes(content, filename=file.filename)
        sym = summary.symbols[0] if len(summary.symbols) == 1 else None
        return {
            "message": summary.message or "CSV import completed",
            "symbol": sym,
            "symbols": summary.symbols,
            "rows": summary.valid_rows,
            "summary": summary.model_dump(),
        }
    except HalalQuantError as e:
        raise HTTPException(e.status_code, e.message) from e
    except ValueError as e:
        raise HTTPException(400, str(e)) from e