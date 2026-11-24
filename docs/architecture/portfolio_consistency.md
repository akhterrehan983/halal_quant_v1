# Portfolio book consistency (M12)

## Authority

| Domain | Source of truth |
|--------|-----------------|
| Cash, reserves, ledger, sleeve holdings qty & avg cost | `portfolio_books` / `BookState` |
| Orders, fills, settlements | `execution_state` JSON |
| Ownership FSM, sell reservations, authorized sell qty | Execution overlay (`ExecutionHolding`) — **qty mirrored from book** |

## Consistency model

Book and execution state are **separate persistence targets**. Fill processing uses **idempotent event markers** on orders (`book_fill_applied`, `overlay_synced`, `fill_persisted`). `reconcile_all()` repairs quantity drift; it **does not** grant or increase sell authorization.

## Disabled paths

- `POST /api/portfolio/buy|sell`
- `POST /api/v1/trades/buy|sell`

Only `POST /api/v1/execution/orders` (with existing gates) may mutate holdings.

## Recovery

1. Re-run fill processing only if order events show incomplete steps.
2. `GET /api/v1/portfolio/reconciliation?repair=true` to sync overlays from book.