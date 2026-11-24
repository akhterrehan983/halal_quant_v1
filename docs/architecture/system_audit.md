# Halal Quant V1 — System Audit (Milestone 9)

**Date:** 2026-11-20  
**Scope:** M1–M8 integrated platform (demo mode primary; PostgreSQL optional)

## Summary

| Severity | Found | Fixed in M9 | Deferred |
|----------|-------|-------------|----------|
| Critical | 4 | 3 | 1 |
| High | 12 | 6 | 6 |
| Medium | 10 | 1 | 9 |
| Low | 5 | 0 | 5 |

---

## Critical

### C1 — Backtest exit logic unreachable after sell-authorization date
- **Module:** `app/backtesting/simulator.py`
- **Repro:** Run backtest with hold period; no `time_exit_authorized` trades despite positions.
- **Root cause:** Outer `session < sell_authorized_date` caused exit block to skip when authorization date passed.
- **Fix:** **Fixed** — exit when hold met and `session >= sell_authorized_date`.
- **Test:** `test_backtest_can_exit_after_authorization`

### C2 — Execution Postgres bootstrap `set()` in JSON
- **Module:** `app/execution/store.py`
- **Repro:** First execution persist with `DATABASE_URL`.
- **Root cause:** `_empty()` used Python `set` for `processed_settlements`.
- **Fix:** **Fixed** — default `[]`; serialize as list on save.

### C3 — Portfolio `state_json` lost updates (no concurrency)
- **Module:** `app/portfolio/store.py`
- **Repro:** Concurrent reserve + fill in separate requests.
- **Root cause:** Read-modify-write without version check.
- **Fix:** **Fixed** — `state_version`, `update_book()`, optimistic `save_book(expected_version)`, `SELECT FOR UPDATE` on Postgres.
- **Test:** `test_book_optimistic_version_conflict`

### C4 — Backtest regime/breadth look-ahead
- **Module:** `signals/generator.py`, `regime/classifier.py`, `regime/benchmark.py`, `regime/market_breadth.py`
- **Repro:** Historical session uses latest benchmark bar.
- **Root cause:** `classify_market()` not scoped to `as_of` in all paths.
- **Fix:** **Fixed (M11)** — evaluation-date anchoring in unified signals; `benchmark_slice(as_of_date=)`; point-in-time breadth.
- **Test:** `tests/test_regime_point_in_time.py`

---

## High (selected)

### H1 — BUY fill replaced holdings instead of merging VWAP
- **Fix:** **Fixed** — `_merge_holding()` + atomic `apply_buy_fill`.
- **Test:** `test_buy_fill_merges_average_cost`

### H2 — SELL did not update portfolio cash/ledger
- **Fix:** **Fixed** — `apply_sell_fill()` updates research book + execution holdings.

### H3 — Nested `load_book`/`save_book` on reserve + fill
- **Fix:** **Fixed** — `reserve_cash`, `release_cash`, fills use `update_book()`.

### H4 — Sell authorization not quantity-bound
- **Fix:** **Fixed** — `authorized_sell_qty`, `reserved_for_sell` on SELL create; `evaluate_sell` checks cap.
- **Test:** `test_sell_authorization_quantity_cap`

### H5 — Drawdown lock ordering / peak only on summary
- **Fix:** **Partial** — lock set before risk event; `check_portfolio_controls` on allocation; `persist=False` on validation reads. Peak still tied to explicit valuation calls.

### H6 — Sensitivity grid did not vary strategy parameters
- **Fix:** **Fixed** — `hold_days` and `min_signal_score` on `BacktestConfig` drive simulator.
- **Test:** `test_sensitivity_changes_hold_days`

### H7–H12 — Dual legacy/v1 books, ownership FSM manual steps, Shariah point-in-time in backtests, etc.
- **Status:** **Deferred** — documented in `financial_integrity.md` and `shariah_execution_policy.md`.

---

## Medium / Low

Documented without code change unless noted: API error shape inconsistency, proposal dual-store, sequence IDs on restart, regime in overview vs v1 book labeling (frontend M8).

---

## Verification commands (executed in M9)

```bash
cd backend && source .venv/bin/activate && pytest -q
cd frontend && npm run test && npm run build
```

See `docs/progress.md` for pass counts after full suite completes.