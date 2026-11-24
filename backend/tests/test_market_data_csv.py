from datetime import date, timedelta

import pandas as pd
import pytest

from app.data.sample_data import make_history
from app.market_data.ingestion import ingest_csv_bytes
from app.market_data.normalization import read_csv_normalized
from app.market_data.persistence import fetch_candles, persist_candles
from app.market_data.schemas import CandleRow
from app.market_data.validation import validate_dataframe


def _csv_bytes(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False).encode()


def _sample_df(symbol: str = "TESTCO", rows: int = 80) -> pd.DataFrame:
    base = make_history(symbol, periods=rows)
    base["symbol"] = symbol
    return base.rename(columns={"date": "date"})


def test_read_csv_column_aliases():
    df = _sample_df()
    df = df.rename(columns={"symbol": "Ticker", "open": "Open", "volume": "Vol"})
    content = _csv_bytes(df)
    out = read_csv_normalized(content, default_symbol="IGNORED")
    assert "symbol" in out.columns
    assert len(out) == len(df)


def test_validate_invalid_ohlc():
    df = _sample_df(rows=5)
    df.loc[0, "high"] = 1
    df.loc[0, "low"] = 100
    _, report = validate_dataframe(df)
    assert report.rejected_rows >= 1
    assert any(i.code == "ohlc_inconsistent" for i in report.issues)


def test_validate_negative_volume():
    df = _sample_df(rows=5)
    df.loc[0, "volume"] = -1
    _, report = validate_dataframe(df)
    assert report.rejected_rows >= 1


def test_duplicate_rows_in_file():
    df = _sample_df(rows=10)
    dup = pd.concat([df, df.iloc[[0]]], ignore_index=True)
    _, report = validate_dataframe(dup)
    assert report.duplicate_rows_in_file >= 1


def test_ingest_demo_mode_updates_memory():
    df = _sample_df("NEWSTK", rows=80)
    content = _csv_bytes(df[["date", "open", "high", "low", "close", "volume"]])
    summary = ingest_csv_bytes(content, filename="NEWSTK.csv")
    assert summary.status == "completed"
    assert "NEWSTK" in summary.symbols
    from app.market_data.repository import get_history_dataframe

    hist = get_history_dataframe("NEWSTK", limit=500)
    assert len(hist) >= 60


def test_persist_idempotent_skip(sqlite_session):
    rows = []
    start = date.today() - timedelta(days=90)
    for i in range(60):
        d = start + timedelta(days=i)
        rows.append(
            CandleRow(
                symbol="IDEM",
                trading_date=d,
                open=100 + i,
                high=101 + i,
                low=99 + i,
                close=100.5 + i,
                volume=1000 + i,
            )
        )
    ins, upd, skip, _ = persist_candles(
        sqlite_session, rows, data_source="test", is_synthetic=False, conflict_policy="skip"
    )
    sqlite_session.commit()
    assert ins == 60
    ins2, _, skip2, _ = persist_candles(
        sqlite_session, rows, data_source="test", is_synthetic=False, conflict_policy="skip"
    )
    sqlite_session.commit()
    assert ins2 == 0
    assert skip2 == 60
    stored = fetch_candles(sqlite_session, "IDEM")
    assert len(stored) == 60


def test_malformed_csv_raises():
    with pytest.raises(ValueError):
        read_csv_normalized(b"not,a,valid\n1,2", default_symbol="X")