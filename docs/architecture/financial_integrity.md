# Financial Integrity

## Cash ledger

- **Decimal** types via `app.portfolio.money` for balances, reserves, and notionals.
- **Reservations:** `reserve_cash` rejects amounts above sleeve available cash (`balance - reserved`).
- **Atomic updates:** `portfolio.store.update_book()` applies reserve, release, buy fill, and sell fill in one optimistic versioned write.
- **BUY fills:** Release matching reservation, debit sleeve cash, append ledger entry, **merge** holdings (VWAP average cost).
- **SELL fills:** Credit proceeds minus fees, reduce quantity, accumulate realized P&L on the research book.

## Concurrency

- `BookState.state_version` incremented on every successful save.
- `save_book(..., expected_version=)` raises `ConcurrentBookUpdate` (HTTP 409) on mismatch.
- PostgreSQL path uses `SELECT … FOR UPDATE` on `portfolio_books` during save.

## Valuation

- `read_summary()` computes metrics without persistence.
- `persist_valuation()` / `build_summary_from_state(persist=True)` updates peak equity and `last_valuation_date`.
- Risk validation and proposal building use `persist=False` to avoid accidental writes during read-only checks.
- `check_portfolio_controls()` runs before allocation proposal generation and on portfolio summary API.

## Single book (M12)

- Legacy BUY/SELL **always rejected** (403). GET `/api/portfolio` maps research book for compat.
- Holdings **quantity** lives only on `BookState`; execution overlay synced via `app/execution/reconcile.py`.
- Fill pipeline: `app/execution/fill_processor.py` (idempotent markers; not one cross-store DB transaction).

See `docs/architecture/portfolio_consistency.md`.

## Valuation snapshots (M13)

- Append-only `portfolio_valuation_snapshots` (PostgreSQL) or in-memory list in demo mode.
- Strict mark: missing prices block snapshot creation (no zero/silent fallback).
- Drawdown history derived from stored snapshot equity — not recomputed with live prices.
- Book peak still updated when a snapshot is generated (`update_book_peak=True`).
- See `docs/architecture/valuation_snapshots.md`.

## Known gaps

- Snapshot not auto-run on every fill (use POST snapshot or external daily job).
- `PaperPortfolio` in `service.py` is unused for writes; may be removed in a later cleanup.