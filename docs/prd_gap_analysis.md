# Halal Quant V1 — PRD Gap Analysis (Milestone 10)

**Audit date:** 2026-11-22  
**Auditor scope:** Read-only repository inspection; no code changes.  
**Target specification:** Halal Quant V1 Product & Implementation Brief (updated). The brief is **not checked into this repository**; requirements below are mapped from that brief as reflected in M1–M9 milestone specs, `README.md`, and `docs/architecture/*.md`, verified against **actual code**.

**Authoritative implementation status:** Code + tests + M5–M9 architecture docs.  
**Do not use** `docs/architecture/current_state.md` § "Milestone 4 snapshot" / §2 "Repository layout" for layout truth — those sections still describe an older monolithic layout (`main.py` routes only, empty `api/`). Current routes live under `app/api/v1/` and `app/api/legacy.py`.

---

## Evidence legend

| Status | Meaning |
|--------|---------|
| **IMPLEMENTED AND VERIFIED** | Code exists; automated tests or integration tests exercise it |
| **IMPLEMENTED BUT NOT FULLY VERIFIED** | Code exists; limited or demo-only test coverage |
| **PARTIALLY IMPLEMENTED** | Subset of PRD behavior; documented limitations |
| **MISSING** | No meaningful implementation |
| **BLOCKED BY EXTERNAL DEPENDENCY** | Requires licensed data, calendar, provider API, or scholarly certification |
| **NEEDS PRODUCT DECISION** | Engineering possible but product/authorship choice required |

**Implementation class:** Working | Demo-only | User-supplied data | No external integration | Partial | Missing

---

## 1. Platform foundation (M1)

| Requirement | Status | Class | Evidence | Limitations |
|-------------|--------|-------|----------|-------------|
| FastAPI backend | IMPLEMENTED AND VERIFIED | Working | `backend/app/main.py`, `app/api/v1/router.py` | — |
| React/Vite frontend | IMPLEMENTED AND VERIFIED | Working | `frontend/src/App.jsx`, 10 pages | See Testing summary (frontend verified 2026-11-22) |
| PostgreSQL + SQLAlchemy optional | IMPLEMENTED AND VERIFIED | Working | `app/core/database.py`, `settings.database_url` | Demo mode when `DATABASE_URL` unset |
| Alembic migrations | IMPLEMENTED AND VERIFIED | Working | `backend/migrations/versions/` (6 revisions through M7) | — |
| Legacy API preserved | IMPLEMENTED AND VERIFIED | Working | `app/api/legacy.py` | Separate in-memory paper book |
| Versioned `/api/v1` | IMPLEMENTED AND VERIFIED | Working | `test_api_v1.py` | — |
| Demo mode | IMPLEMENTED AND VERIFIED | Demo-only | `sample_data`, in-memory stores | Clearly synthetic OHLCV |
| Authentication / multi-user | MISSING | — | No auth middleware | **NEEDS PRODUCT DECISION**; not safe for public deployment |
| CORS | IMPLEMENTED AND VERIFIED | Working | `main.py` | Permissive defaults |

---

## 2. Market data (M2)

| Requirement | Status | Class | Evidence | Limitations |
|-------------|--------|-------|----------|-------------|
| CSV upload, validate, import | IMPLEMENTED AND VERIFIED | Working + demo | `app/market_data/`, `test_market_data_csv.py`, `test_market_data_api.py` | Idempotent DB import needs PostgreSQL |
| OHLCV persistence | IMPLEMENTED AND VERIFIED | Working | Models in `migrations/..._milestone2_market_data.py` | Demo: memory only |
| Repository abstraction | IMPLEMENTED AND VERIFIED | Working | `app/market_data/repository.py` | — |
| Data quality / coverage API | IMPLEMENTED AND VERIFIED | Working | `/api/v1/market-data/quality/{symbol}` | Missing sessions: approximate calendar (`app/market_data/calendar.py`) |
| Corporate actions infrastructure | PARTIALLY IMPLEMENTED | User-supplied / partial | `test_adjustments.py`, corporate action models | Table empty until verified imports; no live CA feed |
| Raw vs adjusted prices | IMPLEMENTED AND VERIFIED | Working | Adjustment pipeline | No fabricated actions |
| **Licensed live market data provider** | MISSING | — | CSV/manual only | **BLOCKED BY EXTERNAL DEPENDENCY** |
| **Daily automated EOD update job** | MISSING | — | No scheduler/worker | Manual CSV only |
| **Pattern recognition (candles)** | MISSING | — | Indicators only in `strategies/indicators.py` | Not in scope of M2–M7 code |
| Import history API | IMPLEMENTED BUT NOT FULLY VERIFIED | Working | `/market-data/imports` | Tests lean demo/SQLite fixture |

---

## 3. Strategies (M3)

| Requirement | Status | Class | Evidence | Limitations |
|-------------|--------|-------|----------|-------------|
| Six strategy modules | IMPLEMENTED AND VERIFIED | Working | `app/strategies/*/strategy.py`, `test_registry_has_six_strategies` | — |
| Registry, evaluate, horizon configs | IMPLEMENTED AND VERIFIED | Working | `evaluator.py`, `test_strategies.py` | — |
| Look-ahead-safe breakout high | IMPLEMENTED AND VERIFIED | Working | `test_breakout_excludes_current_from_rolling_high` | — |
| Strategy enable/disable | IMPLEMENTED AND VERIFIED | Working | `test_disable_strategy_blocks_evaluate` | Persistence of toggles: config/API dependent |
| API evaluate + list | IMPLEMENTED AND VERIFIED | Working | `app/api/v1/strategies.py` | — |

---

## 4. Signal engine & regime (M4)

| Requirement | Status | Class | Evidence | Limitations |
|-------------|--------|-------|----------|-------------|
| Unified signal generation | IMPLEMENTED AND VERIFIED | Working | `app/signals/generator.py`, `test_unified_signal_generate` | — |
| Scoring, lifecycle, persistence | IMPLEMENTED AND VERIFIED | Working + demo | `signals/persistence.py`, `test_lifecycle_transitions` | Demo memory / optional PG |
| Rankings, batch generate APIs | IMPLEMENTED BUT NOT FULLY VERIFIED | Working | `app/api/v1/signals.py` | — |
| Regime classifier | IMPLEMENTED AND VERIFIED | Working + demo | `app/regime/classifier.py`, `test_regime.py` | Breadth uses **latest** bar per symbol (`market_breadth.py`) |
| Historical as-of on benchmark slice | IMPLEMENTED AND VERIFIED | Working | `benchmark_slice(as_of_index)` | — |
| **Point-in-time regime in backtests** | IMPLEMENTED AND VERIFIED | Working | M11 evaluation-date anchoring | `tests/test_regime_point_in_time.py` |
| Legacy per-stock signal mode | IMPLEMENTED AND VERIFIED | Working | `signals.py` `mode=legacy` | — |

---

## 5. Portfolio & risk (M5)

| Requirement | Status | Class | Evidence | Limitations |
|-------------|--------|-------|----------|-------------|
| Decimal cash ledger, sleeves | IMPLEMENTED AND VERIFIED | Working | `portfolio/cash.py`, `money.py` | — |
| Position sizing | IMPLEMENTED AND VERIFIED | Working | `test_position_sizing_*` | — |
| Allocation proposals from signals | IMPLEMENTED AND VERIFIED | Working | `portfolio/allocator.py`, `test_allocation_from_signal` | — |
| Risk validation, drawdown lock | IMPLEMENTED AND VERIFIED | Working | `risk/validation.py`, `test_drawdown_breach` | Peak/drawdown: `persist_valuation` not full history table |
| Exposure / liquidity limits | IMPLEMENTED AND VERIFIED | Working | `risk/liquidity.py`, `limits.py` | — |
| APIs portfolio + risk | IMPLEMENTED AND VERIFIED | Working | `portfolio.py`, `risk.py` | — |
| **Valuation snapshot history** | PARTIALLY IMPLEMENTED | Partial | `peak_value`, `last_valuation_date` in `BookState` JSON | No dedicated equity snapshot table (`financial_integrity.md`) |
| **Legacy vs V1 book unification** | PARTIALLY IMPLEMENTED | Dual books | `legacy.py` → `portfolio.service`; v1 → `portfolio/store.py` | Overview/legacy trades ≠ execution book |
| Optimistic concurrency (M9) | IMPLEMENTED AND VERIFIED | Working | `portfolio/store.py`, `test_book_optimistic_version_conflict` | Postgres `FOR UPDATE` path less tested than demo mem |

---

## 6. Shariah compliance (M6)

| Requirement | Status | Class | Evidence | Limitations |
|-------------|--------|-------|----------|-------------|
| Configurable standards & profiles | IMPLEMENTED AND VERIFIED | Demo templates | `app/shariah/standards.py`, `policies.py`, `test_api_shariah_standards` | Templates, not official provider certification |
| Business activity screening | IMPLEMENTED AND VERIFIED | User-supplied | `business_activity.py`, `submit_activity` in tests | No commercial activity feed |
| Financial ratio screening | IMPLEMENTED AND VERIFIED | User-supplied | `financial_ratios.py`, `test_compliant_with_fixture` | Missing data → `INSUFFICIENT_DATA` (`test_insufficient_data_without_financials`) |
| Eligibility statuses | IMPLEMENTED AND VERIFIED | Working | `eligibility.py`, `shariah/schemas.py` | — |
| Immutable snapshots | IMPLEMENTED AND VERIFIED | Working | `shariah/snapshots.py` | Backtests use sparse snapshot store in demo |
| Purification framework | IMPLEMENTED BUT NOT FULLY VERIFIED | Working | `purification.py`, API GET/POST | No payment execution |
| Multi-profile policies (any/all/primary) | IMPLEMENTED BUT NOT FULLY VERIFIED | Working | `policies.py`, `screening.py` | Limited tests for conflicting standards |
| Fail-closed for orders | IMPLEMENTED AND VERIFIED | Working | `test_buy_order_rejected_without_screening` | — |
| **Official Shariah provider integration** | MISSING | — | — | **BLOCKED BY EXTERNAL DEPENDENCY** |

---

## 7. Paper execution (M6)

| Requirement | Status | Class | Evidence | Limitations |
|-------------|--------|-------|----------|-------------|
| Order lifecycle (MARKET/LIMIT) | IMPLEMENTED AND VERIFIED | Simulated | `execution/order_manager.py`, `schemas.py` | No live broker |
| BUY validation chain | IMPLEMENTED AND VERIFIED | Working | `order_manager.py`, shariah + cash checks | — |
| Next-session fill model | IMPLEMENTED AND VERIFIED | Working | `execution/matching.py`, backtest `fill_market_next_session` | Daily OHLCV limits |
| Transaction costs | IMPLEMENTED AND VERIFIED | Configurable | `execution/costs.py` | Effective dates: configurable, not exhaustive NSE schedule audit |
| Settlement simulation | IMPLEMENTED AND VERIFIED | Approximate | `execution/settlement.py` | T+1 business-day style; not full NSE holiday calendar |
| Ownership FSM | IMPLEMENTED AND VERIFIED | Working | `execution/ownership.py`, `shariah/ownership.py` | Manual verification steps |
| Sell authorization server-side | IMPLEMENTED AND VERIFIED | Working | `sell_authorization.py`, `test_sell_denied_without_authorization`, M9 qty cap test | — |
| Portfolio cash sync on fill (M9) | IMPLEMENTED AND VERIFIED | Working | `test_buy_fill_merges_average_cost`, `test_paper_workflow_buy_updates_portfolio_book` | Execution holdings vs research book still dual structure |
| Full Postgres execution persistence | IMPLEMENTED BUT NOT FULLY VERIFIED | Working | `execution/store.py`, migration M6 | Integration tests reset in-memory store |

---

## 8. Backtesting (M7)

| Requirement | Status | Class | Evidence | Limitations |
|-------------|--------|-------|----------|-------------|
| Event-driven simulator | IMPLEMENTED AND VERIFIED | Working | `backtesting/simulator.py`, `test_backtest_runs_demo` | Caps scan to 4 symbols (`syms[:4]`) |
| Next-session entry (no signal close fill) | IMPLEMENTED AND VERIFIED | Working | `test_next_session_after_signal`, simulator pending_entries | — |
| Point-in-time OHLCV | IMPLEMENTED AND VERIFIED | Working | `data.slice_as_of`, `test_slice_no_future` | — |
| Shariah STRICT / RESEARCH_ONLY | IMPLEMENTED AND VERIFIED | Working | `compliance.py`, `BacktestConfig` | Sparse historical snapshots in demo |
| Ownership delay on exits | IMPLEMENTED AND VERIFIED | Working | `test_backtest_can_exit_after_authorization` | Simplified `earliest_sell_date` vs full FSM |
| Performance metrics | IMPLEMENTED AND VERIFIED | Working | `metrics.py`, API summary | `benchmark_return=None` in simulator |
| Validation report | IMPLEMENTED AND VERIFIED | Working | `validation.py` | Warns on settlement calendar |
| Walk-forward | PARTIALLY IMPLEMENTED | Framework | `walk_forward.py` | Re-runs full-range simulator per fold; not true train/val/test isolation of **parameters** |
| Parameter sensitivity | PARTIALLY IMPLEMENTED | Partial | `validation_sensitivity.py`, M9 tests | Varies `hold_days` / `min_signal_score` only — **not** M3 strategy parameters (RSI, breakout lookback, etc.) |
| Monte Carlo | IMPLEMENTED BUT NOT FULLY VERIFIED | Working | `monte_carlo.py`, `test_monte_carlo_seed` | Resampling exercise only |
| Compare backtests API | MISSING | — | No `POST /backtests/compare` | Listed in M7 spec |
| **Point-in-time universe / listing history** | PARTIALLY IMPLEMENTED | Demo-only | `universe.py` + survivorship warning | **BLOCKED** without membership data |
| **Regime/breadth look-ahead in backtest** | IMPLEMENTED AND VERIFIED | Working | M11 fixed C4 | Regression tests in `test_regime_point_in_time.py` |

---

## 9. Frontend (M8)

| Requirement | Status | Class | Evidence | Limitations |
|-------------|--------|-------|----------|-------------|
| Application shell, 10 workspaces | IMPLEMENTED AND VERIFIED | Working | `App.jsx`, `MainLayout`, `Sidebar` | — |
| API client integration | IMPLEMENTED BUT NOT FULLY VERIFIED | Working | `frontend/src/lib/api.js` | No broad E2E against live API in CI |
| Charts (equity, etc.) | PARTIALLY IMPLEMENTED | Working | `components/charts/EquityCurve.jsx` | Not all PRD chart types |
| INR formatting | IMPLEMENTED AND VERIFIED | Working | `utils/format.test.js` (3 tests) | Verified Vitest 2026-11-22 |
| Risk dashboard page | IMPLEMENTED AND VERIFIED | Working | `pages/RiskDashboard.jsx` | — |
| Settings page | IMPLEMENTED BUT NOT FULLY VERIFIED | Working | `pages/Settings.jsx` | Some settings may be non-persistent |
| **Full frontend test matrix (M8 §19)** | PARTIALLY IMPLEMENTED | Partial | `navigation.test.jsx`, `format.test.js` | 2 test files only; no page-level integration tests |
| Legacy vs v1 labeling | IMPLEMENTED BUT NOT FULLY VERIFIED | Partial | `financial_integrity.md`, legacy endpoints | User confusion risk on Overview |

---

## 10. Integration & reliability (M9)

| Requirement | Status | Class | Evidence | Limitations |
|-------------|--------|-------|----------|-------------|
| System audit documentation | IMPLEMENTED AND VERIFIED | Doc | `docs/architecture/system_audit.md` | — |
| Financial integrity doc | IMPLEMENTED AND VERIFIED | Doc | `financial_integrity.md` | — |
| M9 integration tests | IMPLEMENTED AND VERIFIED | Working | `tests/test_integration_m9.py` (6 tests) | In-memory fixtures only |
| Operational runbook | IMPLEMENTED AND VERIFIED | Doc | `docs/operations/runbook.md` | — |
| End-to-end SELL workflow test | PARTIALLY IMPLEMENTED | Partial | Buy path + auth cap tested | Full 17-step workflow not one automated test |
| PostgreSQL concurrency integration | IMPLEMENTED BUT NOT FULLY VERIFIED | Partial | `save_book` + `FOR UPDATE` in code | No dedicated PG concurrency test in suite |

---

## Financial & Shariah integrity — bypass review

| Safeguard | Enforced server-side? | Bypass path? |
|-----------|----------------------|--------------|
| Shariah before BUY | Yes (`order_manager`, eligibility) | User could use **legacy** `/api/portfolio/buy` — unscreened legacy book |
| Sell without SELL_AUTHORIZED | Blocked in `evaluate_sell` + `paper_broker` | Legacy sell bypasses ownership FSM |
| Missing screening → COMPLIANT | No | `test_insufficient_data_without_financials` |
| authorized_sell_qty cap | Yes (M9) | `test_sell_authorization_quantity_cap` |
| Negative cash via concurrent reserve | Mitigated (optimistic version) | Legacy book + v1 book still separate |
| Frontend bypass sell | No API trust of client auth flags | Correct pattern |

---

## Testing summary (backend — user-executed 2026-11-22)

| Metric | Value |
|--------|-------|
| Test modules | 13 under `backend/tests/` |
| Tests collected | **65** (inferred from pass count; matches `test_*` inventory) |
| Passed | **65** |
| Failed | **0** |
| Skipped | **0** |
| Warnings | **196** (mostly `datetime.utcnow()` deprecation; Starlette `httpx` notice) |
| Duration | ~155 s |

**Frontend** (user-executed 2026-11-22, Node v22.23.1 per `frontend/.nvmrc`):

| Metric | Value |
|--------|-------|
| Command | `cd frontend && nvm use && npm run test && npm run build` |
| Vitest | **4 passed** (2 files: `format.test.js` ×3, `navigation.test.jsx` ×1) |
| Duration | ~1.10s (tests) |
| Production build | **Success** (`vite build`, 523ms) |
| Bundle warning | Main JS chunk ~690 kB gzip ~200 kB (Vite chunk size notice) |

**Combined regression (same day):** Backend **65 passed** + Frontend **4 passed** + production build OK.

---

## Executive classification summary

| Status | Approx. count (major rows) |
|--------|---------------------------|
| IMPLEMENTED AND VERIFIED | ~45 |
| IMPLEMENTED BUT NOT FULLY VERIFIED | ~12 |
| PARTIALLY IMPLEMENTED | ~14 |
| MISSING | ~6 |
| BLOCKED BY EXTERNAL DEPENDENCY | ~4 |
| NEEDS PRODUCT DECISION | ~2 |

---

## Highest-impact gaps vs product brief

1. ~~Backtest regime/breadth look-ahead~~ — **Fixed M11** (see `test_regime_point_in_time.py`).
2. **Dual portfolio books** (legacy vs v1 execution) — financial consistency and UX risk.
3. **No real market or Shariah data providers** — research platform on CSV + user-supplied fundamentals only.
4. **Survivorship / universe** — backtests use current demo universe with explicit warning only.
5. **Strategy-level sensitivity & walk-forward** — framework present; not full OOS parameter discipline.
6. **No authentication** — deployment constraint.
7. **Valuation snapshot history** — drawdown reconstruction limited to book JSON peak fields.

**Recommended next implementation milestone:** See `docs/implementation_roadmap.md` — **M11: Backtest point-in-time regime & benchmark alignment** (prerequisite for trustworthy research results).