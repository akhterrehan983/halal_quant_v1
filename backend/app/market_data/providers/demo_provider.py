from datetime import date

from app.market_data.repository import get_history_dataframe, list_universe_symbols
from app.market_data.providers.base import CandleRecord, MarketDataProvider


class DemoDataProvider(MarketDataProvider):
    """In-memory synthetic demo universe (clearly not NSE production data)."""

    def list_symbols(self) -> list[dict]:
        return [
            {
                "symbol": s,
                "exchange": "NSE",
                "data_source": "synthetic",
                "is_synthetic": True,
            }
            for s in list_universe_symbols()
        ]

    def fetch_history(self, symbol: str, exchange: str = "NSE") -> list[CandleRecord]:
        symbol = symbol.upper()
        try:
            df = get_history_dataframe(symbol, limit=5000)
        except KeyError:
            return []
        records: list[CandleRecord] = []
        for row in df.itertuples():
            records.append(
                CandleRecord(
                    symbol=symbol,
                    exchange=exchange,
                    trading_date=row.date.date() if hasattr(row.date, "date") else row.date,
                    open=float(row.open),
                    high=float(row.high),
                    low=float(row.low),
                    close=float(row.close),
                    volume=int(row.volume),
                    data_source="synthetic",
                    is_synthetic=True,
                )
            )
        return records