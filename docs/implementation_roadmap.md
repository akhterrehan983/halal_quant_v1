# Halal Quant V1 — Implementation Roadmap (Post-M10)

**Created:** 2026-11-22  
**Basis:** M10 PRD gap analysis, technical debt register, M9 audit deferrals.  
**Principle:** Fix correctness and data integrity before new features. No live broker.

Milestones **M1–M9** are complete as engineering prototypes. **M10** is audit-only. Below is the **recommended M11+** sequence.

---

## M11 — Point-in-time regime, benchmark, and signal context (RECOMMENDED NEXT)

### Objective

Eliminate look-ahead in unified signals used by **live API**, **backtests**, and **signal persistence** when an evaluation date is known.

### Scope

- Add `as_of_date: date` (or session) to `classify_market`, `compute_universe_breadth`, and `generate_unified_signal`.
- Align `benchmark_slice` to the same calendar date as stock `as_of_index`.
- Update backtest simulator to pass session date into signal generation.
- Extend validation report to fail or warn if regime `as_of_date > session`.
- **Out of scope:** Licensed NSE breadth index data.

### Dependencies

- M4 regime, M7 backtest simulator (existing).

### Deliverables

- Code changes in `regime/`, `signals/generator.py`, `backtesting/simulator.py`.
- Tests: `test_regime_benchmark_aligned_to_stock_session`, `test_backtest_regime_no_future`, extend `test_regime.py`.
- Update `docs/architecture/backtesting.md`, `signal_engine.md`.

### Acceptance criteria

- For any `session` in backtest, `RegimeClassification.as_of_date <= session`.
- Existing 65 backend tests pass; ≥3 new look-ahead tests pass.
- C4 in `system_audit.md` marked **Fixed**.

### Required tests

- Unit: benchmark slice by date.
- Integration: backtest with forced early session asserts older regime than end-of-sample regime.

---

## M12 — Single portfolio book & legacy migration

### Objective

One authoritative cash/holdings ledger for research UI, paper execution, and allocation.

### Scope

- Read path: Overview, Portfolio pages use `/api/v1/portfolio/*` + execution holdings.
- Legacy `/api/...` buy/sell: deprecate or proxy to v1 with explicit 410/redirect.
- Document migration for users on legacy paper book.

### Dependencies

- M5 portfolio store, M6 execution (M9 sync helpers).

### Deliverables

- API deprecation plan, optional `?book=v1` only.
- Frontend labels removed for dual books.
- Integration test: legacy endpoint cannot bypass Shariah when disabled.

### Acceptance criteria

- No documented path to buy without screening when `STRICT` policy enabled.
- Portfolio summary reconciles cash + holdings + reserved within one book.

### Required tests

- E2E paper workflow uses single book (`test_integration_m9` extended).
- Frontend smoke: Portfolio matches execution holdings for symbol/qty.

---

## M13 — Valuation snapshots & drawdown audit trail

### Objective

Persist daily (or on-demand) portfolio valuations for risk history and M5 drawdown reconstruction.

### Scope

- Alembic: `portfolio_valuation_snapshots`.
- Write on `persist_valuation=True` and after fills/settlement.
- Risk dashboard: historical drawdown series from snapshots.

### Dependencies

- M12 (single book), PostgreSQL optional but schema required.

### Acceptance criteria

- Peak/drawdown reproducible from snapshots after restart (PG mode).
- `check_portfolio_controls` does not need ad-hoc peak recompute.

### Required tests

- PG fixture: fill → snapshot row; drawdown matches manual calculation.

---

## M14 — Backtest methodology hardening

### Objective

Meet M7 research standards: strategy parameter sensitivity, walk-forward OOS, benchmark-attached metrics.

### Scope

- Sensitivity: overlay strategy params from registry configs.
- Walk-forward: separate metrics for train/val/test windows; no headline blending.
- `benchmark_return` aligned to backtest date range.
- Optional: `POST /backtests/compare`.

### Dependencies

- **M11** (trustworthy signals in backtest).

### Acceptance criteria

- Sensitivity test proves different breakout lookback changes trade count.
- Walk-forward API returns per-fold OOS metrics only in test window fields.

### Required tests

- Extend `test_sensitivity_*`, new walk-forward leakage test.

---

## M15 — Universe & survivorship data layer

### Objective

Pluggable historical membership; strict mode when data missing.

### Scope

- `UniverseProvider` implementation stub + CSV import for listing/delisting.
- Backtest uses point-in-time membership when records exist.

### Dependencies

- **BLOCKED** partial: requires product-sourced membership files.

### Acceptance criteria

- Backtest without membership data keeps warning; with data, symbol set changes by year.

---

## M16 — Market data operations (non-licensed minimum)

### Objective

Operational CSV pipeline clarity; optional scheduled import hook (cron doc only, no Celery unless requested).

### Scope

- Import job idempotency tests across restart.
- Missing-session report uses documented calendar limitations.
- Provider interface doc for future NSE/vendor adapter.

### Dependencies

- M2 market data.

---

## M17 — Shariah data & operations

### Objective

Production-ready **user-managed** screening workflow (still not official certification).

### Scope

- Bulk snapshot import API; review queue for `NEEDS_REVIEW`.
- Stricter multi-profile conflict UX (frontend + API).

### Dependencies

- M6 Shariah module.

### Blocked

- Commercial Shariah screening provider APIs (**BLOCKED BY EXTERNAL DEPENDENCY**).

---

## M18 — Frontend quality gate

### Objective

Regression safety for M8 workspaces.

### Scope

- Vitest + RTL tests for critical flows (signal filter, paper sell disabled, backtest warnings).
- CI script documentation.

### Dependencies

- Node ≥20.19 (`frontend/.nvmrc`).

### Acceptance criteria

- ≥15 frontend tests; `npm run build` clean on supported Node.

---

## M19 — Security & deployment readiness (optional product)

### Objective

Authentication, rate limits, safe defaults for non-local deploy.

### Scope

- **NEEDS PRODUCT DECISION** on auth model.
- Env-based CORS lockdown.

---

## Dependency graph (simplified)

```text
M11 (regime PIT) ──► M14 (backtest methodology)
        │
M12 (single book) ──► M13 (valuation snapshots)
        │
M15 (universe data) ──► M14
M16 (market ops) ──► M15 (optional)
M17 (Shariah ops)     parallel track
M18 (frontend tests)  after M12 (stable APIs)
M19 (auth)            product decision
```

---

## What not to do next

- Live broker or demat integration  
- Auto-trading from signals without explicit user order  
- Claiming halal certification from demo templates  
- Large frontend rewrite (M8 shell is adequate)  

---

## Suggested approval checkpoint

After **M11** + **M12**, re-run full M10-style gap pass on:

- Look-ahead  
- Financial single-book reconciliation  
- Shariah/order enforcement paths  