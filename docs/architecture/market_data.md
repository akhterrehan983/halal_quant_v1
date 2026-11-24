# Market Data Architecture (Milestone 2)

## Goals

- Provider-independent daily OHLCV for NSE equities.
- PostgreSQL as source of truth when `DATABASE_URL` is set.
- Demo in-memory mode when database is disabled.
- Raw prices never overwritten by adjustments.

## Layers

| Layer | Module | Responsibility |
|--------|--------|----------------|
| Providers | `app/market_data/providers/*` | Demo, CSV ingest surfaces |
| Normalization | `normalization.py` | Column aliases, dtypes, symbols |
| Validation | `validation.py` | OHLC rules, duplicates, outliers |
| Persistence | `persistence.py` | SQLAlchemy bulk insert, conflict policy |
| Ingestion | `ingestion.py` | Orchestration, import metadata |
| Repository | `repository.py` | Unified reads for API + strategies |
| Adjustments | `adjustments.py` | Separate adjusted series (no raw overwrite) |
| Calendar | `calendar.py` | Weekday sessions; approximate holiday hints |
| Features | `app/features/*` | Indicators (via `add_indicators` facade) |

## Data flow

```text
CSV upload → normalize → validate → persist (transaction)
                                    ↓
                          market_data_imports row
                                    ↓
              repository.get_history_dataframe() → evaluate_all()
```

## Conflict policies

- `skip` (default): existing `(symbol, trading_date)` unchanged.
- `update`: replace OHLCV on conflict.
- `reject`: abort transaction on first conflict.

## Raw vs adjusted

- `ohlcv_candles` stores **raw** observations.
- `corporate_actions` stores verified action metadata (empty until imported).
- `adjustments.apply_adjustments()` returns a **copy** with `adjusted_close`.

## Demo mode

Without `DATABASE_URL`, imports update `sample_data.HISTORIES` only. API responses label `source` accordingly.

## Limitations

- NSE holiday calendar is **approximate** (partial static list).
- No licensed live NSE feed in M2.
- Corporate actions are not auto-populated.