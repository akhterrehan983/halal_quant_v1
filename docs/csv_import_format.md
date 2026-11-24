# CSV Import Format

## Required columns

Each row must include daily OHLCV:

- `date` (or `Date`, `trading_date`)
- `open`, `high`, `low`, `close`
- `volume`

## Optional

- `symbol` (or `Ticker`) — required for multi-symbol files; otherwise use filename stem (e.g. `TCS.csv`).
- `adj_close` / `Adj Close` — stored when provided; raw `close` is never replaced.

## Example (single symbol)

```csv
date,open,high,low,close,volume
2024-01-01,100.5,101.2,99.8,100.9,125000
2024-01-02,100.9,102.1,100.4,101.8,138400
```

## Example (multi symbol)

```csv
symbol,date,open,high,low,close,volume
TCS,2024-01-01,3500,3520,3488,3510,2100000
INFY,2024-01-01,1450,1462,1445,1458,1800000
```

## Import endpoints

- Legacy: `POST /api/data/upload` (dashboard + backward compatible).
- Versioned: `POST /api/v1/market-data/import/csv?conflict_policy=skip|update|reject`
- Validate only: `POST /api/v1/market-data/validate`

## Rules

- Minimum **60** rows per symbol for research endpoints.
- Invalid OHLC relationships are rejected with structured errors.
- Duplicate symbol/date rows in file are rejected.
- Re-import with `skip` is idempotent.