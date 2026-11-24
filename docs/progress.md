# Halal Quant V1 — Progress Log

## Milestone 12 — Single portfolio book (complete)

### Implemented

- Legacy and v1 trade POST endpoints always 403
- `reconcile.py`, `fill_processor.py`, enriched holdings API
- Overview / Paper Trading use research book quantities
- `tests/test_integration_m12.py`, `holdings-reconcile.test.js`
- `docs/architecture/portfolio_consistency.md`

### Verification

- Backend: **84 passed**, **1 skipped** (demo mode without `DATABASE_URL`), 221 warnings (~232s) — verified 2026-11-22
- Post-run fixes: execution store `_normalize_state` (M12 `holdings` KeyError); regime `high_volatility_flag` native `bool` (live `/api/v1/regime/current` 500)
- **PostgreSQL (local):** Alembic at `c4d2e8a91f03` (20 tables); `scripts/verify_postgres_setup` PASS; M12 **11 passed** with `test_postgres_reconcile_smoke` (2026-11-22)
- Frontend (prior run): **5** Vitest tests, build OK

---

## Milestone 11 — Point-in-time regime & signal context (complete)

### Implemented

- `benchmark_slice(..., as_of_date=)` caps benchmark series before index resolution
- `compute_universe_breadth(as_of_date=)` point-in-time cross-section
- `classify_market(as_of_date=)` + breadth aligned to benchmark bar date
- `evaluation_date()` / unified signal anchors regime and relative strength to stock evaluation bar
- `aligned_relative_returns(..., as_of_date=)` caps benchmark and stock for merge

### Tests

- New `tests/test_regime_point_in_time.py` (M11 regression suite)
- Backend: **74 passed**, 0 failed, 199 warnings (~179s) — verified 2026-11-22
- Frontend: **4 passed**, build OK (2026-11-22)

### Docs

- TD-C1, TD-C2 resolved in `docs/technical_debt.md`
- `system_audit.md` C4 marked fixed
- `signal_engine.md`, `backtesting.md` look-ahead sections updated

---

## Milestone 9 — Integration & reliability (complete)

### Implemented

- Portfolio optimistic concurrency (`state_version`, `update_book`)
- Atomic cash reserve/fill; BUY VWAP merge; SELL portfolio book updates
- Sell authorization quantity caps + reservations
- Backtest exit logic fix; real sensitivity on `hold_days` / `min_signal_score`
- Integration tests `tests/test_integration_m9.py`
- Docs: `system_audit.md`, `financial_integrity.md`, `shariah_execution_policy.md`, `operations/runbook.md`

### Tests

See latest `pytest -q` / `npm run test` run in README (M9 adds **6** integration tests).

---

## Milestone 8 — Frontend expansion (complete)

### Implemented

- Application shell: grouped sidebar, header (health, data mode, theme, refresh)
- Page modules under `frontend/src/pages/` (10 workspaces incl. **Risk Dashboard** + **Settings**)
- Shared components (`components/common`, `layout`, `charts/EquityCurve`)
- `AppContext`, INR formatting utils, dark/light theme
- Vitest: `npm run test` (format + navigation)
- `docs/architecture/frontend.md`

### Verification

- Frontend: **4** Vitest tests passed, `npm run build` succeeded
- Backend regression: **59 passed**

---

## Milestone 7 — Backtesting (complete)

### Implemented

- Event-driven `app/backtesting/simulator.py`
- Point-in-time signals, Shariah modes, next-session fills
- Metrics, validation report, walk-forward, Monte Carlo
- `/api/v1/backtests/*` + **Backtesting lab** UI
- `docs/architecture/backtesting.md`

### Tests

**59 passed** (~2.5 min full suite).

---

## Milestone 6 — Shariah & Paper Execution (complete)

### Implemented

- `app/shariah/` configurable standards, screening, snapshots, purification
- `app/execution/` paper orders, matching, settlement, ownership, sell authorization
- `/api/v1/shariah/*`, `/api/v1/execution/*`
- Frontend **Shariah compliance** + **Paper trading**
- `docs/architecture/shariah_execution.md`
- Alembic `38a76ff1fe77_milestone6_shariah_execution`

### Tests

**54 passed**.

---

## Milestone 5 — Portfolio & Risk (complete)

### Implemented

- Swing / positional / reserve sleeves with Decimal cash ledger
- Risk-based position sizing, stops, liquidity & exposure validation
- Allocation proposals from M4 ACTIVE BUY signals
- Drawdown lock, risk events, rebalancing proposals (no auto-trade)
- `/api/v1/portfolio/*`, `/api/v1/risk/*`
- Frontend **Portfolio & risk** workspace
- `docs/architecture/portfolio_risk.md`
- Alembic `0e419f811f08_milestone5_portfolio_risk`

### Tests

**48 passed** (includes portfolio/risk unit + API smoke).

---

## Milestone 4 — Market Regime & Signal Engine (complete)

### Implemented

- `app/regime/` classifier with historical as-of support
- `app/features/relative_strength.py` benchmark-relative returns
- `app/signals/` generator, aggregator, scoring, lifecycle, persistence, ranking
- Models + Alembic `86bcb02a62c5_milestone4_signals`
- `/api/v1/regime/*`, `/api/v1/signals/*` (unified + legacy mode)
- Frontend **Signal center** view
- `docs/architecture/signal_engine.md`

### Tests

**40 passed** (regime, signal engine, M1–M3 regression).

---

## Milestone 3 — Strategy Modularization (complete)

### Implemented

- Six strategy modules + `BaseStrategy`, registry, evaluator, Pydantic `StrategyResultModel`
- `evaluate_all()` facade preserved for legacy API
- `/api/v1/strategies/*` evaluate + toggle endpoints
- Frontend **Strategy explorer** view
- `docs/architecture/strategies.md`

### Tests

**29 passed** (includes strategy registry, API evaluate, backward compat).

---

## Milestone 2 — Market Data Infrastructure (complete)

### Implemented

- CSV normalization, validation, ingestion with import summaries
- PostgreSQL persistence (idempotent skip/update/reject)
- Models: `market_data_imports`, `corporate_actions`, candle `created_at`/`updated_at`
- Alembic: `001e7c2278d4_milestone2_market_data`
- Repository layer (DB source of truth when configured; no silent DB fallback on errors)
- Feature modules + `add_indicators` backward-compatible facade
- Corporate action adjustment interface (no fabricated actions)
- `/api/v1/market-data/*` endpoints (import, validate, candles, quality, corporate-actions)
- Legacy `/api/*` wired through repository + shared ingestion
- Frontend **Market data** workspace (upload, validate, quality, recent candles)

### Tests

`21 passed` — engine, API v1, CSV, features, adjustments, market data API.

### Known limitations

- Licensed NSE holiday calendar not integrated (missing sessions approximate).
- Corporate actions table empty until verified imports.
- Import history API requires PostgreSQL.
- Adjusted price API requires DB + corporate action records.

---

## Milestone 1 — Foundation

Documented in `docs/implementation/progress.md`.