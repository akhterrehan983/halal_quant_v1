from app.market_data.ingestion import ingest_csv_bytes
from app.market_data.providers.base import CandleRecord, MarketDataProvider
from app.market_data.repository import get_history_dataframe


class CsvIngestProvider(MarketDataProvider):
    """Provider that surfaces data after CSV ingestion into persistence/demo memory."""

    def list_symbols(self) -> list[dict]:
        from app.market_data.repository import list_universe_symbols

        return [{"symbol": s, "exchange": "NSE", "data_source": "csv_upload"} for s in list_universe_symbols()]

    def fetch_history(self, symbol: str, exchange: str = "NSE") -> list[CandleRecord]:
        df = get_history_dataframe(symbol, limit=5000)
        records: list[CandleRecord] = []
        for row in df.itertuples():
            td = row.date.date() if hasattr(row.date, "date") else row.date
            records.append(
                CandleRecord(
                    symbol=symbol.upper(),
                    exchange=exchange,
                    trading_date=td,
                    open=float(row.open),
                    high=float(row.high),
                    low=float(row.low),
                    close=float(row.close),
                    volume=int(row.volume),
                    data_source="csv_upload",
                    is_synthetic=False,
                )
            )
        return records

    def ingest(self, content: bytes, filename: str | None = None):
        return ingest_csv_bytes(content, filename=filename)