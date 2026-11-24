"""Load synthetic demo universe into PostgreSQL when DATABASE_URL is set."""

from decimal import Decimal

from app.core.config import settings
from app.core.database import SessionLocal, engine
from app.data.sample_data import HISTORIES, SYMBOLS
from app.models import OHLCVCandle, Stock


def main() -> None:
    if not settings.database_enabled or engine is None or SessionLocal is None:
        raise SystemExit("DATABASE_URL is not configured")

    with SessionLocal() as session:
        for symbol in SYMBOLS:
            stock = session.query(Stock).filter_by(symbol=symbol).one_or_none()
            if not stock:
                stock = Stock(symbol=symbol, exchange="NSE", data_source="synthetic", is_synthetic=True)
                session.add(stock)
                session.flush()
            df = HISTORIES[symbol]
            for row in df.itertuples():
                td = row.date.date() if hasattr(row.date, "date") else row.date
                exists = (
                    session.query(OHLCVCandle)
                    .filter_by(symbol=symbol, exchange="NSE", trading_date=td)
                    .one_or_none()
                )
                if exists:
                    continue
                session.add(
                    OHLCVCandle(
                        stock_id=stock.id,
                        symbol=symbol,
                        exchange="NSE",
                        trading_date=td,
                        open=Decimal(str(round(row.open, 4))),
                        high=Decimal(str(round(row.high, 4))),
                        low=Decimal(str(round(row.low, 4))),
                        close=Decimal(str(round(row.close, 4))),
                        volume=int(row.volume),
                        data_source="synthetic",
                        is_synthetic=True,
                    )
                )
        session.commit()
    print(f"Seeded {len(SYMBOLS)} demo symbols into PostgreSQL.")


if __name__ == "__main__":
    main()