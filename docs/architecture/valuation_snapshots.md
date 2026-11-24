# Valuation snapshots (M13)

## Authority

- **Quantities and cash:** `BookState` in `portfolio_books` (unchanged).
- **Execution overlay:** `execution_state` (unchanged).
- **Valuation history:** append-only `portfolio_valuation_snapshots` — never updated in place.

## Methodology

1. Resolve per-held-symbol closes from market data (`get_history_dataframe`, last bar).
2. **VALID** if last bar ≤ 5 calendar days old; **STALE** if older; **UNAVAILABLE** if no series.
3. Snapshot generation with `strict=True` **rejects** unavailable symbols (HTTP 422) — no entry-price fabrication.
4. `build_summary` computes equity as cash (incl. reserve) + marked market value.
5. Peak equity on snapshot: `max(prior_book_peak, current_equity)`; drawdown vs that peak.
6. Historical drawdown analytics read **stored** `portfolio_equity` only — no repricing.

## Triggers

| Trigger | Idempotency |
|---------|-------------|
| `daily` | One row per `(book_name, valuation_date)` |
| `on_demand` | Multiple per day allowed |

## Operations

```bash
# On demand
curl -X POST http://localhost:8000/api/v1/portfolio/valuations/snapshot \
  -H 'Content-Type: application/json' -d '{"trigger":"daily"}'

# Daily (idempotent for today)
curl -X POST ... -d '{"trigger":"daily","valuation_date":"2026-11-24"}'
```

## Limitations

- No cross-store transaction with `portfolio_books` / `execution_state`.
- Demo mode: snapshots in process memory unless `DATABASE_URL` set.
- No built-in cron; run daily snapshot via external scheduler or manual API.
- Sleeve allocation percentages from `risk_configurations` at snapshot time.