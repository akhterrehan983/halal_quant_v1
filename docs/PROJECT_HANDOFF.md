# Halal Quant V1 — Authoritative Project Handoff

> **Maintenance header**
> - **Last updated:** 2026-11-27
> - **Current milestone / phase:** M14 — Backtesting Methodology Hardening (Phase 1, Phase 1.1 & F-4 breadth cache committed; **Phase 2 (walk-forward v2) implemented, uncommitted** — plan approved with clarifications in [`docs/m14_phase2_plan.md`](m14_phase2_plan.md))
> - **Latest verified Git commit:** `16163c0` (*"M14 F-4: run-scoped as-of breadth cache"*, `HEAD -> main`, matching `origin/main`), following `3d5714c` (*"M14: F-4 verification, Phase 1.1 baselines, handoff"*) and `498f8bc`
> - **Working tree status at update:** Uncommitted Phase 2 work: new `walk_forward_schemas.py`, `walk_forward_v2.py`, `api/v2/`, `tests/test_walk_forward_m14.py`, `docs/m14_phase2_plan.md`; modified `app/main.py` (router mount) and this handoff
> - **Current next action:** Full suite passed (193 passed, 2 deselected). Run the baseline `--compare` on its own (commands in section 11.3a), then commit. No commit has been made for Phase 2.
>
> **Maintenance rule:** Update this document after every completed milestone, major implementation phase, significant architectural decision, or verified test-status change. Never mark planned work as implemented without repository and test evidence.

---

## 1. Status classification guide

Throughout this handoff, every capability is explicitly classified so new contributors or AI sessions do not mistake prototypes or plans for verified production features:

| Status label | Meaning |
|---|---|
| **Completed and verified** | Implemented in the repository and exercised by passing automated tests or verified baseline/DB scripts. |
| **Implemented but not fully verified** | Implemented in code, but coverage is limited to unit/demo fixtures, missing end-to-end PostgreSQL concurrency runs, or awaiting dedicated integration verification. |
| **Planned / not started** | Documented in roadmap/audit plans only; no production implementation yet. |
| **Known limitation / deferred** | Deliberately scoped out of the current phase, or blocked on external data/licensing/product decisions. |

---

## 2. Project overview

**Halal Quant V1** is a local-first, full-stack quantitative equity research and paper-trading platform built for **Shariah-compliant Indian equities (NSE)** across **swing** and **positional** horizons.

- **Intended user:** An individual researcher / trader building, auditing, and testing rule-based Shariah-compliant equity strategies before placing manual trades through a retail broker (Groww).
- **Current intended workflow:**
  1. **Market data ingestion & quality checks** (synthetic demo universe or imported daily OHLCV CSVs).
  2. **Regime classification & signal generation** (six rule-based strategies combined into a 0–100 consensus research signal with market regime alignment).
  3. **Shariah compliance evaluation** (user-supplied business activity & financial ratios checked against configurable standard templates, generating immutable snapshots).
  4. **Portfolio & risk sizing** (sleeve-based risk sizing and capital allocation proposals on `BookState`, checked against drawdown, exposure, and liquidity limits).
  5. **Paper execution & ownership tracking** (simulated next-session fills, T+1 settlement tracking, manual ownership/possession verification before SELL authorization).
  6. **Manual broker execution (outside the system):** The user manually reviews research outputs and places real orders on **Groww** outside this application.

> **Critical boundary:** Halal Quant V1 is **not** an automated trading bot. There is **no** broker API connection, **no** demat integration, and **no** automatic real-money order placement.

---

## 3. User and product constraints (non-negotiable)

1. **Shariah-only long-only equities:** No short selling, no leverage/margin borrowing, no intraday trading, and no F&O in scope.
2. **Manual Groww execution:** All real broker execution is performed manually by the user outside the platform.
3. **Fail-closed Shariah screening:** Missing financial ratios or missing business-activity classifications must evaluate to `INSUFFICIENT_DATA` / `UNKNOWN` / `NEEDS_REVIEW` and **block new BUY orders**. Missing data must never silently default to `COMPLIANT`.
4. **Demo templates are not religious certification:** Built-in standards (`aaoifi_demo_v1`, `ftse_shariah_demo_v1`) are configurable software templates only, not official Shariah-board or scholarly rulings.
5. **Conservative delivery & ownership safeguards before SELL:**
   - Paper/book positions follow a strict state machine in `app/shariah/ownership.py` and `app/execution/ownership.py`:
     `NOT_OWNED` → `ORDER_PENDING` → `EXECUTED_UNSETTLED` → `SETTLED_PENDING_VERIFICATION` → `OWNERSHIP_VERIFIED` → `POSSESSION_VERIFIED` → `SELL_AUTHORIZED`.
   - T+1 business-day settlement completion (`SETTLED_PENDING_VERIFICATION`) does **not** grant sell permission. Manual verification steps (`POST /api/v1/execution/ownership/{record_id}/verify`) are required to reach `SELL_AUTHORIZED`.
   - `evaluate_sell()` enforces `SELL_AUTHORIZED`, `authorized_sell_qty`, `sellable_quantity`, and `reserved_for_sell` server-side.
   - In backtesting (`simulator.py`), when a protective stop is breached during an ownership-restricted period, the position is **not** sold early; it is held and exited at the first authorised open (`exit_reason="stop_ownership_delayed"`), with breach date, stop price, delayed exit date, fill, and `loss_beyond_stop` reported.
6. **Synthetic demo disclaimer:** Default demo prices are seeded random walks (`app/data/sample_data.py`). Outputs on demo data are software-regression checks, never evidence of market profitability.
7. **Financial & ledger integrity:** Decimal arithmetic (`app/portfolio/money.py`), explicit cash reservation before order acceptance, optimistic concurrency on `BookState`, and strict backtest-to-live isolation (`SimBook` never writes to `BookState`).

---

## 4. Architecture and technology

### Stack summary

| Layer | Technology | Verification notes |
|---|---|---|
| Backend API | FastAPI (`>=0.115`), Pydantic v2 (`>=2.8`), `pydantic-settings` | `backend/pyproject.toml`, `backend/requirements.txt`; Python `>=3.12` required (venv verified on Python `3.13.3` in baseline JSON) |
| Data / analytics | Pandas (`>=2.2,<3.0`, verified `2.3.3`), NumPy (`>=2.0,<3.0`, verified `2.5.5`) | `backend/requirements.txt`, baseline JSON metadata |
| Persistence | PostgreSQL 16 (`docker-compose.yml`), SQLAlchemy 2.0, Alembic, `psycopg[binary]` | Optional at runtime (`DATABASE_URL`); falls back to explicit in-memory demo stores when unset |
| Frontend | React + Vite (`frontend/package.json`), Recharts, Lucide React | Node `>=20.19.0` (`frontend/.nvmrc` = `22`); Vitest + `@testing-library/react` + `jsdom` |
| Tests | `pytest` (`>=8.0,<9.0`), `httpx`, `vitest` | Backend `tests/conftest.py` isolates demo mode unless marked `@pytest.mark.postgres` |

### Verified module & file map

- **Backend entrypoint & config:**
  - `backend/app/main.py` — FastAPI app factory, CORS middleware, exception handler, mounts `legacy_router` and `api_v1_router`.
  - `backend/app/core/config.py` — `Settings` loading `.env` and `../.env` (`database_url`, `starting_cash`, `benchmark_symbols`, `import_conflict_policy`, `cors_origins`).
  - `backend/app/core/database.py`, `exceptions.py`, `logging.py`, `security.py` (auth placeholder).
- **APIs:**
  - `backend/app/api/legacy.py` — `/api/health`, `/api/universe`, `/api/history/{symbol}`, `/api/signals/{symbol}`, `/api/scan`, `/api/portfolio`, `/api/data/upload`. Legacy write endpoints `POST /api/portfolio/buy` and `POST /api/portfolio/sell` return **HTTP 403**.
  - `backend/app/api/v1/router.py` — `/api/v1` aggregator covering 12 routers:
    - `health.py` (`/health`)
    - `stocks.py` (`/stocks`, `/stocks/{symbol}`)
    - `market.py` (`/market-data/{symbol}`, `/market/regime`)
    - `market_data.py` (`/market-data/import/csv`, `/validate`, `/imports`, `/{symbol}/candles`, `/{symbol}/latest`, `/quality`, `/{symbol}/corporate-actions`)
    - `strategies.py` (`/strategies`, `/{id}`, `/{id}/evaluate`, `/evaluate`)
    - `regime.py` (`/regime/current`, `/regime/history`)
    - `signals.py` (`/signals`, `/signals/generate`, `/generate/batch`, `/rankings`, `/{id}`, `/{id}/history`)
    - `portfolio.py` (`/portfolio/*`, `/portfolio/valuations*`, `/portfolio/drawdown`, `/portfolio/performance-history`, `/portfolio/reconciliation`, `/portfolio/allocate`, `/portfolio/rebalance/*`; `POST /trades/buy|sell` disabled with **HTTP 403**)
    - `risk.py` (`/risk/config`, `/exposure`, `/limits`, `/events`, `/validate-allocation`)
    - `shariah.py` (`/shariah/standards`, `/profiles`, `/screening/{symbol}*`, `/snapshots/{symbol}`, `/purification`)
    - `execution.py` (`/execution/orders*`, `/holdings*`, `/ownership*`, `/settlements*`, `/sell-authorizations*`)
    - `backtests.py` (`/backtests*`, `/summary`, `/equity-curve`, `/drawdown`, `/trades`, `/metrics`, `/validation`, `/walk-forward`, `/sensitivity`, `/monte-carlo`)
- **Database models & Alembic migrations (`backend/app/models/`, `backend/migrations/versions/`):**
  - Models (`models/__init__.py`): `Stock`, `ShariahScreening`, `OHLCVCandle`, `CorporateAction`, `ResearchSignal`, `SignalLifecycleEvent`, `MarketDataImport`, `PaperPortfolioState`, `PaperPosition`, `PaperTrade`, `PortfolioValuationSnapshot`, `PortfolioBook`, `RiskConfigurationRecord`, `AllocationProposalRecord`, `RebalanceProposalRecord`, `RiskEventRecord`, `ShariahEligibilityStore`, `ShariahSnapshotRow`, `ExecutionStateRow`, `BacktestRunRow`.
  - Alembic chain (7 revisions, 20 app tables + `alembic_version` = 21 total tables verified in `scripts/verify_postgres_setup.py`):
    1. `aec82f8a19c5` — `initial_schema` (M1)
    2. `001e7c2278d4` — `milestone2_market_data` (M2)
    3. `86bcb02a62c5` — `milestone4_signals` (M4)
    4. `0e419f811f08` — `milestone5_portfolio_risk` (M5)
    5. `38a76ff1fe77` — `milestone6_shariah_execution` (M6)
    6. `c4d2e8a91f03` — `milestone7_backtesting` (M7)
    7. `e8f91a2b4c10` — `m13_valuation_snapshots` (M13, **current head**)
- **Market data & storage (`backend/app/market_data/`, `backend/app/data/`):**
  - `data/sample_data.py` — 8 synthetic symbols (`TCS`, `INFY`, `RELIANCE`, `HDFCBANK`, `SUNPHARMA`, `TATAMOTORS`, `BEL`, `COALINDIA`), 520 business-day bars each generated deterministically relative to today.
  - `market_data/benchmarks.py` — Explicit benchmark registry (Phase 1.1): built-in `NIFTY500_PROXY` plus `BENCHMARK_SYMBOLS` setting, read at call time via `app.core.config.settings`.
  - `market_data/repository.py` — Unified Postgres/memory data access. Exposes `list_all_symbols()`, `list_universe_symbols()` (equity-only; excludes registered benchmarks), `history_upto()`, `get_history_window()`, `get_next_bar()`, `bar_fingerprints()`.
  - `market_data/persistence.py` — Bulk candle upserts (`skip`/`update`/`reject`) and `candle_fingerprints()` (single grouped SQL aggregate over `OHLCVCandle` for cache invalidation).
  - `market_data/providers/` (`base.py`, `demo_provider.py`, `csv_provider.py`), `normalization.py`, `validation.py`, `ingestion.py`, `adjustments.py`, `calendar.py`, `quality.py`, `schemas.py`.
- **Feature, strategy & signal engine (`backend/app/features/`, `backend/app/strategies/`, `backend/app/signals/`):**
  - `features/` — `pipeline.py`, `trend.py`, `momentum.py`, `volatility.py`, `volume.py`, `returns.py`, `relative_strength.py` (`aligned_relative_returns`).
  - `strategies/` — `base.py`, `registry.py`, `evaluator.py`, `config.py` (`HorizonConfig` swing/positional), `schemas.py`, `context.py`, `indicators.py`, `engine.py` (`evaluate_all` facade), plus 6 strategy modules: `momentum`, `breakout`, `pullback`, `mean_reversion`, `trend_following`, `high_momentum`.
  - `signals/` — `generator.py` (`generate_unified_signal` anchoring regime/RS to `evaluation_date`), `aggregator.py`, `scoring.py` (weights sum to 100), `ranking.py`, `lifecycle.py`, `persistence.py`, `schemas.py`, `config.py`.
- **Regime classification & breadth (`backend/app/regime/`):**
  - `classifier.py` — `classify_market(..., as_of_date=...)` (`BULLISH`, `BEARISH`, `SIDEWAYS`, `HIGH_VOLATILITY`, `MIXED`).
  - `benchmark.py` — `ensure_benchmark_history()`, `benchmark_slice()`, side-effect-free equal-weight universe proxy cached privately by `repository.bar_fingerprints` (no settings bound in module).
  - `market_breadth.py` — `compute_universe_breadth(as_of_date=...)` computing % of equity symbols above SMA50; excludes registered benchmarks (Phase 1.1). As-of breadth is memoised inside `breadth_cache_scope()` (one backtest run, F-4); uncached everywhere else.
  - `indicators.py`, `config.py`, `schemas.py`.
- **Portfolio, risk & valuation (`backend/app/portfolio/`, `backend/app/risk/`):**
  - `portfolio/store.py` — `BookState` dataclass persisted in `portfolio_books` JSON (`state_version` optimistic lock + `SELECT ... FOR UPDATE` in Postgres) or `_BOOK_MEM` in demo mode. **Sole authority** for live cash, reserves, ledger, and holding qty/avg cost.
  - `portfolio/` — `manager.py`, `allocator.py`, `position_sizing.py`, `cash.py`, `money.py`, `holdings.py`, `exposure.py`, `performance.py`, `rebalancing.py`, `sectors.py`, `enriched.py`, `compat.py` (maps `BookState` to legacy `/api/portfolio` shape). `service.py` (`PaperPortfolio`) is dead/legacy for writes.
  - `portfolio/valuation.py`, `snapshots.py`, `drawdown_audit.py`, `valuation_schemas.py` — M13 append-only `portfolio_valuation_snapshots`, strict close resolution (`<= 5` days valid, else stale/unavailable), drawdown episodes from stored equity only.
  - `risk/` — `manager.py`, `limits.py` (`swing` 40% / `positional` 40% / `reserve` 20%, max drawdown 15%), `validation.py`, `drawdown.py`, `concentration.py`, `correlation.py`, `liquidity.py`, `stop_loss.py`, `schemas.py`.
- **Execution overlay & Shariah (`backend/app/execution/`, `backend/app/shariah/`):**
  - `execution/store.py` — `execution_state` JSON row (`ExecutionHolding` overlay, orders, settlements, ownership events).
  - `execution/order_manager.py` — Validates BUY (Shariah, cash reservation, benchmark exclusion), SELL (`evaluate_sell`).
  - `execution/fill_processor.py`, `reconcile.py`, `matching.py`, `paper_broker.py`, `settlement.py`, `ownership.py`, `sell_authorization.py`, `costs.py`, `schemas.py`.
  - `shariah/` — `standards.py`, `policies.py`, `business_activity.py`, `financial_ratios.py`, `eligibility.py`, `screening.py`, `snapshots.py`, `purification.py`, `ownership.py`, `store.py`, `schemas.py`.
- **Backtesting & isolated `SimBook` (`backend/app/backtesting/`):**
  - `portfolio.py` — `SimBook` and `SimPosition` (completely isolated from `portfolio/store.py`).
  - `simulator.py` — Event-driven daily simulator (Phase 1 hardened).
  - `universe.py` — `partition_universe()` + `universe_for_backtest()` (excludes registered benchmarks).
  - `data.py`, `compliance.py`, `execution.py`, `costs.py`, `metrics.py`, `validation.py`, `walk_forward.py`, `validation_sensitivity.py`, `monte_carlo.py`, `store.py`, `schemas.py`, `config.py`, `engine.py`, `events.py`.
- **Frontend (`frontend/src/`):**
  - `App.jsx`, `context/AppContext.jsx`, `lib/api.js`, `utils/format.js`, `components/layout/` (`MainLayout.jsx`, `Sidebar.jsx`, `Header.jsx`, `PageHeader.jsx`), `components/common/` (`MetricCard.jsx`, `StatusBadge.jsx`, `LoadingState.jsx`, `EmptyState.jsx`, `ErrorState.jsx`), `components/charts/EquityCurve.jsx`.
  - 10 workspaces under `frontend/src/pages/`: `Overview.jsx`, `MarketData.jsx`, `StrategyExplorer.jsx`, `SignalCenter.jsx`, `Portfolio.jsx`, `RiskDashboard.jsx`, `ShariahCompliance.jsx`, `PaperTrading.jsx`, `BacktestingLab.jsx`, `Settings.jsx`.
- **Scripts, tests & docs:**
  - `backend/scripts/` — `seed_demo_to_db.py`, `verify_postgres_setup.py`, `freeze_m14_baseline.py`.
  - `backend/tests/` — 18 committed test modules (`test_*.py`) totaling 133 tests, plus the untracked `test_breadth_cache_m14.py` (13 tests, passing), `conftest.py`, `baselines/` JSON artifacts.
  - `frontend/src/*.test.*` — 3 Vitest files (5 tests total).
  - `docs/` — Milestone logs, architecture docs, M14 audit (`m14_backtesting_audit.md`) and review (`m14_phase1_review.md`), operations runbook (`operations/runbook.md`).

---

## 5. Milestone history (M1–M14)

> **Git-evidence note:** Repository Git history contains three commits: `577b177` (*"Initial commit: Halal Quant V1"*, which bundled M1–M12), `08c1680` (*"M13: valuation snapshots, drawdown audit, APIs and UI"*), and `498f8bc` (*"Harden M14 backtesting phase 1"*). Details for M1–M11 are verified from repository code, migrations, tests, `docs/progress.md`, `docs/implementation/progress.md`, `docs/prd_gap_analysis.md`, `docs/technical_debt.md`, and `docs/architecture/*`.

| Milestone | Main objective | Accomplished & implementation areas | Verification / tests | Remaining limitations |
|---|---|---|---|---|
| **M1 — Foundation** | FastAPI modular shell, optional PostgreSQL, Alembic, legacy API preservation | `main.py`, `core/config.py`, `core/database.py`, `api/legacy.py`, `api/v1/*`, `docker-compose.yml`, Alembic `aec82f8a19c5`, `seed_demo_to_db.py` | Verified in code/migrations; docs recorded initial `test_engine.py` + `test_api_v1.py` (5 tests) | Demo fallback in memory when `DATABASE_URL` unset; no auth; `docs/architecture/current_state.md` §2 still shows mixed-era layout |
| **M2 — Market Data** | CSV ingestion, validation, DB candle store, repository abstraction, features | `app/market_data/*`, `app/features/*`, Alembic `001e7c2278d4`, `/api/v1/market-data/*`, `MarketData.jsx` | `test_market_data_csv.py`, `test_market_data_api.py`, `test_adjustments.py`, `test_features.py` (docs recorded 21 passed at M2) | Approximate holiday calendar (`calendar.py`); no licensed market data feed; `corporate_actions` empty until imported |
| **M3 — Strategies** | Modularize 6 rule-based strategies with `BaseStrategy` and horizon config | `app/strategies/*`, `evaluate_all()` facade preserved, `/api/v1/strategies/*`, `StrategyExplorer.jsx` | `test_strategies.py` (8 tests), `test_engine.py` (1 test) (docs recorded 29 passed at M3) | Enable/disable state is in-memory only; heuristic rules not calibrated |
| **M4 — Regime & Signals** | Benchmark regime classifier, relative strength, unified 0–100 consensus signals & lifecycle | `app/regime/*`, `features/relative_strength.py`, `app/signals/*`, Alembic `86bcb02a62c5`, `/api/v1/regime/*`, `/api/v1/signals/*`, `SignalCenter.jsx` | `test_regime.py` (5 tests), `test_signal_engine.py` (7 tests) (docs recorded 40 passed at M4) | Proxy benchmark is synthetic/survivor average; no India VIX; calendar-day expiration approximation |
| **M5 — Portfolio & Risk** | Decimal sleeves, risk sizing, stops, drawdown lock, allocation proposals | `app/portfolio/*` (excluding M13 valuation files), `app/risk/*`, Alembic `0e419f811f08`, `/api/v1/portfolio/*`, `/api/v1/risk/*`, `Portfolio.jsx`, `RiskDashboard.jsx` | `test_portfolio_risk.py` (8 tests) (docs recorded 48 passed at M5) | Sector map only covers demo stocks (`UNCLASSIFIED` otherwise); rebalancing emits proposals only; `PaperPortfolio` left in `service.py` |
| **M6 — Shariah & Execution** | Configurable screening, immutable snapshots, paper execution, ownership FSM, sell authorization | `app/shariah/*`, `app/execution/*`, Alembic `38a76ff1fe77`, `/api/v1/shariah/*`, `/api/v1/execution/*`, `ShariahCompliance.jsx`, `PaperTrading.jsx` | `test_shariah_execution.py` (6 tests) (docs recorded 54 passed at M6) | Demo screening templates only; manual ownership verification; purification display-only; partial fills minimal |
| **M7 — Backtesting** | Event-driven historical simulator, Shariah modes, walk-forward/sensitivity/Monte Carlo stubs | `app/backtesting/*`, Alembic `c4d2e8a91f03`, `/api/v1/backtests/*`, `BacktestingLab.jsx` | `test_backtesting.py` (5 tests) (docs recorded 59 passed at M7) | Initial prototype had major methodology defects later audited in M14 (`B-01..B-32`); `docs/architecture/backtesting.md` reflects M7/M11 state |
| **M8 — Frontend Expansion** | 10-workspace research UI, theme support, shared formatting/charts, Vitest smoke suite | `frontend/src/` (`MainLayout`, 10 pages, `EquityCurve`, `AppContext`, `api.js`, `format.js`) | `format.test.js`, `navigation.test.jsx` (4 passed at M8; 59 backend passed) | No URL router (refresh returns to Overview); sparse page-level RTL integration tests (tracked as M18) |
| **M9 — Integration & Reliability** | Optimistic `BookState` locking, atomic cash/fill ledger, VWAP merge, sell auth qty cap, backtest exit fix | `portfolio/store.py`, `execution/fill_processor.py`, `sell_authorization.py`, `docs/architecture/system_audit.md`, `financial_integrity.md`, `operations/runbook.md` | `test_integration_m9.py` (6 tests); full backend 65 passed reported at M10 audit | Left dual legacy/v1 books until M12 and C4 regime look-ahead until M11 |
| **M10 — PRD Gap & Tech Debt Audit** | Audit-only milestone mapping implementation vs product brief | `docs/prd_gap_analysis.md`, `docs/technical_debt.md`, `docs/implementation_roadmap.md` | Read-only audit verified against 65 backend + 4 frontend tests (2026-11-22) | External PRD brief is not checked into repo |
| **M11 — Point-in-Time Regime** | Eliminate benchmark & breadth look-ahead in unified signals and backtests | `regime/benchmark.py` (`benchmark_slice(as_of_date=)`), `regime/market_breadth.py` (`as_of_date=`), `signals/generator.py` (`evaluation_date`), `relative_strength.py` | `test_regime_point_in_time.py` (9 tests; 74 backend passed at M11) | `evaluator.build_context` still called `aligned_relative_returns` without explicit `as_of_date` (mitigated by inner join, tracked as `B-26`) |
| **M12 — Single Portfolio Book** | Enforce `BookState` as sole holdings/cash authority; block legacy/v1 trade writes; sync overlay | `api/legacy.py` & `api/v1/portfolio.py` (403 on write), `portfolio/compat.py`, `enriched.py`, `execution/reconcile.py`, `fill_processor.py`, `docs/architecture/portfolio_consistency.md` | `test_integration_m12.py` (11 tests incl. `@pytest.mark.postgres`), `holdings-reconcile.test.js` (frontend 5 passed; backend 84 passed + 1 skipped in demo, 11/11 in PG) | Cross-store writes (`portfolio_books` vs `execution_state`) remain two JSON rows mitigated by idempotent markers + `reconcile_all()` |
| **M13 — Valuation Snapshots** | Append-only portfolio valuation snapshots and snapshot-driven drawdown audit | Commit `08c1680`: `models/portfolio_valuation.py`, Alembic `e8f91a2b4c10`, `portfolio/valuation.py`, `snapshots.py`, `drawdown_audit.py`, `Overview.jsx`, `Portfolio.jsx` | `test_valuation_m13.py` (8 tests incl. `@pytest.mark.postgres`); 94 backend passed incl. PG (2026-11-25) | No automatic post-fill snapshot hook; no bundled scheduler/cron |
| **M14 — Backtest Hardening (Phases 1 & 1.1)** | Fix critical leakage/execution integrity bugs first; freeze baseline & isolate universe/benchmark | Commit `498f8bc`: `simulator.py`, `universe.py`, `benchmarks.py`, `repository.py`, `persistence.py`, `regime/benchmark.py`, `market_breadth.py`, `order_manager.py`, `freeze_m14_baseline.py`, `BacktestingLab.jsx`, `docs/m14_*` | `test_backtest_phase1_m14.py` (27), `test_backtest_phase1_1_m14.py` (12), `test_regime_point_in_time.py` (9) = **48 passed**; full suite **133 passed**; post-1.1 baseline & first-4 ablation frozen | Phases 2–6 not started; **F-4** breadth cache in working tree, verification pending; `B-09`/`B-10`/`B-29`/`B-32` blocked on M15–M17 |

---

## 6. M14 detailed status

### Original audit conclusion (`docs/m14_backtesting_audit.md`)

Before M14 work began, the static and empirical audit concluded that the backtest engine was a **research sandbox, not a research-grade engine**. Fourteen acceptance criteria (Section 11 of `docs/m14_backtesting_audit.md`) must hold before any run may be treated as research-grade; until then, runs remain labelled `demo` or `imported_unverified`.

### Audit findings & Phase 1 / 1.1 disposition

| ID | Finding | Status | Notes |
|---|---|---|---|
| **B-01** | Price loader kept only latest 520 bars regardless of backtest date | **Fixed (Phase 1)** | `repository.history_upto`, `get_history_window`, `get_next_bar`, `_SymbolFeed` bisected by session date |
| **B-02** | Stop-loss and target levels computed but never enforced | **Fixed (Phase 1)** | Daily-bar stop/target checks with **stop-first** assumption and **ownership-delayed stop** handling |
| **B-03** | Position sizing used next session's open (look-ahead) | **Fixed (Phase 1)** | Sized at signal close (`close * (1 + slippage)`); re-validated at actual fill where quantity can only shrink |
| **B-08** | Missing bars silently marked at entry price | **Fixed (Phase 1)** | Marked at last known close; stale marks counted (`stale_marks`, `max_stale_days`) and warned (`> 5` sessions flagged) |
| **B-09** | Survivorship filter silently dropped listings/delistings | **Surfacing fixed (Phase 1)**; full membership **Deferred (M15)** | Coverage status (`full`/`partial`/`none`), excluded symbols, and start/end gaps recorded in `warnings` and `validation["coverage"]` |
| **B-12** | Entry scan capped to 4 list-order-dependent symbols (`syms[:4]`) | **Pulled forward & fixed (Phase 1)**; **Verified by ablation (Phase 1.1)** | Full eligible universe scanned; runtime budget remains open (`F-4` / Phase 5 `B-24`) |
| **B-14** | Benchmark proxy entered tradable universe & lacked documentation | **Exclusion pulled forward (Phase 1)** & **registry-driven (Phase 1.1)**; proxy docs **Deferred (Phase 4)**; historical constituents **Deferred (M15)** | Benchmarks excluded from scans, breadth, and equity BUY orders; still an equal-weight current-universe survivor average |
| **B-28** | No data provenance or evidence grade on results | **Fixed (Phase 1)** | `EvidenceGrade` (`demo` / `imported_unverified`) & `DataProvenance` stored, returned by API, shown in `BacktestingLab.jsx` |
| **B-30** | No check that data covered requested end date | **Fixed (Phase 1)** | `start_gap_days` / `end_gap_days` checked and warned when `> 5` days |
| **F-1..F-3, F-5** | Review findings: run-order proxy mutation, benchmark in breadth, hardcoded 1-symbol exclusion, stale audit doc | **Fixed (Phase 1.1)** | See Phase 1.1 summary below |
| **F-4** | Per-signal breadth recomputation runtime scaling | **Redundant recomputation: cache implemented and verified (2026-11-27). Real-universe runtime budget: still open (Phase 5 `B-24`)** | Profiled: breadth was 66% of a real-signal backtest; run-scoped as-of cache in `market_breadth.py` (see "F-4 breadth profiling and cache" below and review §9) |
| **B-17** | Walk-forward blends train/test spans and labels OOS | **Phase 2 v2 engine implemented (uncommitted); v1 endpoint unchanged and still blended — see [`docs/m14_phase2_plan.md`](m14_phase2_plan.md) section 12** | Plan defines `/api/v2` independent train/test walk-forward with frozen per-fold selection and test-only `oos_summary` |
| **B-04, B-05, B-06, B-07, B-15, B-21, B-25, B-27** | Missing buy costs in trade P&L, `ZERO` cost default, asymmetric exit fills, unused ADV cap, unliquidated end positions, fill-time limit/expiry checks, unsourced/missing SEBI cost rates, `SimBook` parity test | **Deferred (Phase 3 — not started)** | `ZERO` remains default until rates are confirmed and Phase 3 is implemented |
| **B-11, B-13, B-16, B-18, B-19, B-20, B-31** | Degenerate Monte Carlo, missing benchmark-relative metrics, Sortino/Calmar/sample flags, short-window CAGR, Sharpe convention, calendar vs session hold days, dead schema fields | **Deferred (Phase 4 — not started)** | — |
| **B-22, B-23, B-24, B-26** | Strategy parameter sensitivity overlay, multiple-testing dispersion, full history/indicator caching, explicit `as_of_date` in `build_context` | **Deferred (Phase 5 / hygiene — not started)** | `B-26` inner-join mitigates leakage today |
| **B-10, B-29, B-32** | Shariah financial publication dates, corporate-action-adjusted backtest prices, authoritative NSE settlement calendar | **Deferred / blocked (M15–M17)** | Cannot be solved cleanly without historical corporate/fundamental/calendar datasets |

### Key Phase 1 mechanics implemented (`simulator.py`)

- **Strict daily session order:** (1) Pending fills at next-session open (with fill-time revalidation; quantity can only decrease) → (2) Exits → (3) Close marks (stale-aware, equity point recorded after exits) → (4) Signals across full tradable universe (top candidate queued).
- **Stop-first same-bar assumption (Decision 2):** Gap checks run at session open first (`open <= stop` → `"stop"`, else `open >= target` → `"target"`). If neither triggers at open, intrabar checks evaluate `low <= stop` **before** `high >= target` (conservative assumption).
- **Ownership-delayed stop behavior (Decision 1 / Phase 1 review):**
  - While `session < pos.sell_authorized_date`, a stop breach sets `pos.stop_pending = True` and records `pos.stop_breach_date` (first breach session) and increments `ownership_blocked_exits` without selling.
  - On the first authorised session (`session >= sell_authorized_date`), `_check_exit` closes the position at session `open` (or mark if bar missing) with `exit_reason = "stop_ownership_delayed"`.
  - `CompletedTrade` reports `stop_price`, `stop_breach_date`, `delayed_exit_date`, `exit_price` (`actual_fill`), and `loss_beyond_stop = max(0, stop_price - actual_fill) * quantity` (before costs; clamped at 0 if price recovered).
  - Run-level summary lives in `run.validation["ownership_delayed_stops"]` (`count`, `total_loss_beyond_stop`, `events`) plus a warning in `run.warnings`.
- **Provenance & evidence grades:** `_provenance()` labels synthetic or unknown-source runs `EvidenceGrade.DEMO` and imported-only runs `EvidenceGrade.IMPORTED_UNVERIFIED` (never a research-grade label in Phase 1). Both `BacktestRun` JSON persistence and `BacktestingLab.jsx` surface them.

### Key Phase 1.1 benchmark & proxy corrections

- **Explicit benchmark registry (`app/market_data/benchmarks.py`):** Built-in `NIFTY500_PROXY` plus comma-separated symbols from `BENCHMARK_SYMBOLS` (`app/core/config.py`). Settings are read at call time (`_config.settings`) so test monkeypatching works reliably.
- **Universe partitioning & BUY rejection:**
  - `repository.list_universe_symbols()` returns equities only (registered benchmarks stripped). `list_all_symbols()` retains the raw list solely for reporting `benchmark_excluded` in `backtesting/universe.py`.
  - `execution/order_manager.py` rejects `BUY` orders for registered benchmarks (`"Registered benchmark / index proxy is not a tradable equity"`).
- **Side-effect-free proxy & content-sensitive cache (`regime/benchmark.py`, `repository.py`, `persistence.py`):**
  - `_build_equal_weight_proxy` iterates `sorted(symbols)` and never writes to `sample_data.SYMBOLS` or `sample_data.HISTORIES`.
  - `_inputs_fingerprint` keys `_PROXY_CACHE` by `repository.bar_fingerprints(ordered)`: in memory mode, `(len, min_date, max_date, blake2b digest of dates+OHLCV)`; in DB mode, `persistence.candle_fingerprints()` (grouped aggregate query returning count, min/max dates, OHLCV sums, `sum(close * id)` to catch swapped closes, and `max(updated_at)`). `regime/benchmark.py` binds no `settings` object.
- **Breadth exclusion (`regime/market_breadth.py`):** Both `as_of_date` and latest paths skip registered benchmarks while preserving M11 point-in-time slicing.

### Full-universe scan & B-12 ablation evidence (synthetic demo data)

Both freezes were executed on clean commit `498f8bc` (`backend_app_has_uncommitted_changes: false`) by `backend/scripts/freeze_m14_baseline.py` (anchor last bar `2026-11-20`, backtest window `2026-08-03` to `2026-10-30`, `max_positions=3`, `horizon="swing"`, `initial_capital=100000`, `slippage_bps=10`):

| Run & artifact | Scenario | Trades | Total return | Max drawdown | Sharpe | Profit factor | Costs | Shariah rejections | Ownership blocked exits | Elapsed (single run) |
|---|---|---|---|---|---|---|---|---|---|---|
| **Full 8-symbol universe** (`tests/baselines/m14_post_phase1_1.json`) | A (`RESEARCH_ONLY`, `ZERO`) | 22 | **1.29%** (`0.0129`) | **1.55%** (`0.015465...`) | **1.20** (`1.1996`) | 1.47 | `0.0000` | 0 | 4 | 76.7 s |
| **Full 8-symbol universe** (same) | B (`RESEARCH_ONLY`, `REALISTIC`) | 22 | **1.04%** (`0.0104`) | **1.595%** (`0.015946...`) | **0.974** (`0.9737`) | 1.40 | `216.7800` | 0 | 4 | 86.0 s |
| **Full 8-symbol universe** (same) | C (`STRICT`, `ZERO`) | 0 | `0.0000` | `0` | — | — | `0.0000` | **132** | 0 | 159.9 s |
| **First-4-symbol ablation** (`tests/baselines/m14_ablation_first4.json`) | A (`RESEARCH_ONLY`, `ZERO`) | 9 | **0.56%** (`0.0056`) | **0.95%** (`0.009532...`) | **0.720** (`0.7198`) | 1.49 | `0.0000` | 0 | 2 | 58.3 s |
| **First-4-symbol ablation** (same) | B (`RESEARCH_ONLY`, `REALISTIC`) | 9 | **0.46%** (`0.0046`) | **0.975%** (`0.009749...`) | **0.590** (`0.5896`) | 1.42 | `86.6100` | 0 | 2 | 54.3 s |
| **First-4-symbol ablation** (same) | C (`STRICT`, `ZERO`) | 0 | `0.0000` | `0` | — | — | `0.0000` | **47** | 0 | 74.7 s |

**Interpretation & caveats:**
- **B-12 verified by ablation for scan behavior only:** Same commit (`498f8bc`), same window; `--symbols TCS,INFY,RELIANCE,HDFCBANK` restricts `scanned_symbols` to the first 4 equities while breadth and the proxy still read all 8 stored demo symbols. Widening the scan increased trades (9 → 22), returns, and Sharpe on this sample, while also increasing drawdown, volatility (`0.0313` → `0.0429` in A), transaction costs (`86.61` → `216.78` in B), ownership-blocked exits (2 → 4), and STRICT Shariah rejections (47 → 132), and lowering profit factor slightly (`1.49` → `1.47` in A; `1.42` → `1.40` in B).
- **Path dependence:** Because entries share one cash balance and `max_positions = 3`, trade paths are portfolio-dependent; no individual added symbol is credited with a specific P&L effect.
- **Not real-market evidence:** Data are synthetic demo series (`8 symbols × 520 bars`, ~2 years). `STRICT` mode produced 0 trades because point-in-time compliant snapshots do not exist in the demo dataset. `REALISTIC` is a configured scenario (`brokerage_pct = 0`, `sebi_per_crore` defined but unapplied in `execution/costs.py`) and is **not** proof of actual brokerage or statutory tax charges.
- **F-4 at freeze time:** These single-run timings (`54–160 s`) were measured before the breadth cache, when breadth was recomputed per candidate. STRICT (C) was slowest despite 0 trades because it never holds positions, so every symbol is a candidate every session. Scaling on a real universe is unmeasured.

### F-4 breadth profiling and cache (verified 2026-11-27, not yet committed)

Full detail: `docs/m14_phase1_review.md` §9.

- **Call path:** `simulator` step 4 → `generate_unified_signal` (once per candidate per session) → `classify_market` → `compute_universe_breadth(as_of_date)` → `add_indicators` on ≤520 bars of every equity. Same answer for every candidate on a session.
- **Method:** in-memory demo mode, fixed anchored freeze data (8 equities × 520 bars), throwaway script (not in repo; no longer on disk), single runs.
- **Results:** one breadth call **245.7 ms** (mean of 20). cProfile of scenario A settings over 2026-10-01..2026-10-30: 22 sessions, 70 signal evaluations, 70 breadth calls for only **11 distinct dates**; breadth **34.27 s of 51.78 s (66%)**. Per-date memo prototype without profiler: **29.13 s → 13.61 s (−53.3%)**, trades/metrics/equity identical.
- **Design:** `breadth_cache_scope()` context manager (`ContextVar`) in `market_breadth.py`; `run_backtest` wraps the run in it, so the memo lives for exactly one run (no cross-run state, no run-order dependence). Outside a scope (live/API paths) and for `as_of_date=None`, nothing is cached. Separate from `_PROXY_CACHE`.
- **Key / invalidation:** `(as_of_date, sorted equities with registered benchmarks removed, sorted (symbol, bar_fingerprint) pairs)`. Fingerprints are the Phase 1.1 `repository.bar_fingerprints` (memory: frame digest; DB: one `candle_fingerprints` aggregate query, no candle load). Any as-of change, equity add/remove, `BENCHMARK_SYMBOLS` change or equity bar edit recomputes; edits after the as-of date also recompute (conservative). Benchmark bars are outside the key. Hits return a copy.
- **Formula unchanged:** the original body moved verbatim to `_compute_universe_breadth`.
- **Tests:** `backend/tests/test_breadth_cache_m14.py` (13 tests): **13 passed**. Focused breadth/M14/PIT: **61 passed**. Full suite: **144 passed, 2 errors**. The 2 errors are the PostgreSQL-marked tests `test_postgres_reconcile_smoke` and `test_postgres_snapshot_persisted`, which could not connect to `localhost:5432` (server not running). Neither touches breadth or the simulator; they are **not verified** in this run.
- **Baseline identity:** `freeze_m14_baseline --compare tests/baselines/m14_post_phase1_1.json /tmp/m14_post_f4.json` → `scenarios_sha256 equal: True`; no differences in A, B or C (metrics, trades and equity `sha256`).
- **Single-run timing (not a same-process comparison):** A 34.1 s, B 33.7 s, C 64.2 s, against 76.7 s, 86.0 s and 159.9 s in the committed baseline. Conditions differ between those runs; the speedup is not established.

### Baseline artifacts in `backend/tests/baselines/`

| File | Commit & cleanliness | Purpose & status |
|---|---|---|
| `m14_pre_phase1.json` | Committed in `498f8bc` (taken on clean `08c1680`) | Pre-Phase 1 reference baseline (capped 4-symbol scan, pre-Phase 1 simulator). |
| `m14_post_phase1.json` | Committed in `498f8bc` (taken on dirty `08c1680`) | **Superseded** intermediate Phase 1 capture prior to Phase 1.1 corrections. |
| `m14_post_phase1_1.json` | **Untracked** (taken on clean `498f8bc`) | Authoritative clean post-Phase 1.1 full 8-symbol baseline. |
| `m14_ablation_first4.json` | **Untracked** (taken on clean `498f8bc`) | First-four-symbol (`TCS,INFY,RELIANCE,HDFCBANK`) ablation matching `498f8bc`. |

### Latest verified test counts

- **Focused M14 Phase 1.1 + Phase 1 + PIT regime run:** **48 passed** in `25.47s` (`tests/test_backtest_phase1_1_m14.py` 12 + `tests/test_backtest_phase1_m14.py` 27 + `tests/test_regime_point_in_time.py` 9).
- **Full backend suite (post-Phase 1.1):** **133 passed** (across all 18 `test_*.py` modules under `backend/tests/`).
- **Frontend (`frontend/`):** `5` Vitest tests (`format.test.js` ×3, `navigation.test.jsx` ×1, `holdings-reconcile.test.js` ×1) and `npm run build` passed prior to Phase 1.1; no `frontend/` files changed after commit `498f8bc`, though frontend checks were not re-run in the post-1.1 cycle.

---

## 7. Current exact project state

Verified from `git status` and `git log` on `2026-11-26`:
- **Branch & HEAD:** `main` at `498f8bc0dd9abbfc855e3e0e057fd6eda415144f` (*"Harden M14 backtesting phase 1"*), synced with `origin/main`.
- **Committed & pushed:** All M14 Phase 1 and Phase 1.1 application code, test suites (`test_backtest_phase1_m14.py`, `test_backtest_phase1_1_m14.py`), `freeze_m14_baseline.py`, `BacktestingLab.jsx` provenance banner, `docs/m14_backtesting_audit.md`, and the initial `docs/m14_phase1_review.md`.
- **Uncommitted / untracked in working tree (nothing staged):**
  - `M docs/m14_phase1_review.md` — Section 8 (post-Phase 1.1 baseline & B-12 ablation evidence) and Section 9 (F-4 profiling and cache).
  - `?? backend/tests/baselines/m14_post_phase1_1.json` — clean Phase 1.1 full-universe baseline artifact (from clean `498f8bc`).
  - `?? backend/tests/baselines/m14_ablation_first4.json` — clean Phase 1.1 first-four-symbol ablation artifact (from clean `498f8bc`).
  - `?? docs/PROJECT_HANDOFF.md` — this handoff document.
  - `M backend/app/regime/market_breadth.py` — F-4 run-scoped breadth cache.
  - `M backend/app/backtesting/simulator.py` — `run_backtest` wraps `_run_backtest` in `breadth_cache_scope()`; run body unchanged.
  - `?? backend/tests/test_breadth_cache_m14.py` — 13 F-4 tests.
  - Note: a zero-byte file `main` at the repo root was introduced in commit `08c1680` (minor hygiene artifact; do not touch without checking).
- **Phase 2 status:** **Implemented in the working tree, not committed.** Additive v2 engine and `/api/v2` endpoints (design and as-built notes: [`docs/m14_phase2_plan.md`](m14_phase2_plan.md) sections 0 and 12). Verification so far: `tests/test_walk_forward_m14.py` 49 passed; focused backtest/regime group (`test_walk_forward_m14`, `test_backtest_phase1_m14`, `test_backtest_phase1_1_m14`, `test_breadth_cache_m14`, `test_backtesting`, `test_regime`, `test_regime_point_in_time`) 159 passed with `-m "not postgres"`. Full suite `pytest -q -m "not postgres"` after Phase 2: **193 passed, 2 deselected** (144 existing + 49 new; run by the user, 2026-11-27, 220.9 s). Baseline `--compare` not yet run after Phase 2. PostgreSQL-marked tests (2) not run. Evidence grade stays DEMO. `app/backtesting/walk_forward.py` (v1, blended window, `B-17`) is unchanged.
- **Next engineering task:** Review and commit Phase 2 after the full-suite and baseline `--compare` checks; then Phase 3 (execution realism and costs).

---

## 8. Remaining M14 work (prioritized checklist)

1. [x] **Record baseline and ablation results in the review document** — Recorded in `docs/m14_phase1_review.md` Section 8 (awaiting commit).
2. [x] **Preserve and review baseline JSON artifacts** — Reviewed 2026-11-26: both files come from clean `498f8bc` (`backend_app_has_uncommitted_changes: false`) and match the review §8 and the table above (metrics, ownership-delayed events, coverage, elapsed). `m14_post_phase1.json` remains superseded. Still untracked.
3. [ ] **Review and commit documentation and baseline artifacts** — Commit `docs/m14_phase1_review.md`, `docs/PROJECT_HANDOFF.md`, and the two new baseline JSONs without touching `.env`.
4. [x] **Profile breadth runtime and implement a safe cache if justified (F-4)** — Profiled (breadth 66% of runtime; 53% saving from a per-date memo); run-scoped cache implemented. See "F-4 breadth profiling and cache".
5. [x] **Verify cached-vs-uncached breadth identity** — `test_breadth_cache_m14.py` 13 passed (2026-11-27); `--compare` against `m14_post_phase1_1.json` gives `scenarios_sha256 equal: True`, no differences in A, B or C.
6. [ ] **Run targeted tests and full backend suite** — Confirm focused M14/regime tests and full `pytest -q` suite pass cleanly.
7. [ ] **Review Phase 1 / Phase 1.1 acceptance criteria** — Confirm clean Git status, stable runtime baseline, and sign-off before opening Phase 2.
8. [~] **Phase 2 (Walk-forward hardening — `B-17`)** — *Implemented additively as `/api/v2`, uncommitted; see [`docs/m14_phase2_plan.md`](m14_phase2_plan.md) section 12. Original scope text kept below for reference:*
   - **Strict Phase 2 scope:** Implement a v2 walk-forward endpoint and engine (`walk_forward.py`, `schemas.py`, `api/v1/backtests.py`) that executes **independent** train, validation, and test simulations over disjoint date windows with frozen parameters per fold. Report segment metrics separately and compute `oos_metrics` strictly from test-window trades—never blend train and test spans into an OOS headline.
   - **Subsequent M14 phases (all planned / not started):**
     - **Phase 3:** Execution realism & costs (`B-04`, `B-05` `REALISTIC` default only after rate confirmation, `B-06` symmetric exits, `B-07` ADV cap, `B-15` end-of-backtest liquidation policy, `B-21` fill-time limit/expiry checks, `B-25` SEBI charges with cited rates, `B-27` `SimBook`/live sizing parity).
     - **Phase 4:** Metrics & benchmark comparison (`B-13`, `B-16` Sortino/Calmar/sample flags, `B-18` short-window CAGR rule, `B-19` Sharpe convention, `B-20` session hold days, `B-11` non-degenerate bootstrap Monte Carlo, `B-14` proxy documentation, `B-31` dead-field cleanup).
     - **Phase 5:** Sensitivity & robustness (`B-22` parameter overlay without mutating `HorizonConfig` registry defaults, `B-23` dispersion/multiple-testing warning, regime split & strategy attribution, `B-24` history/indicator caching).
     - **Phase 6:** Frontend reporting & documentation refresh (`BacktestingLab.jsx` segments/warnings/cost labels, refresh `docs/architecture/backtesting.md`, `technical_debt.md`, `prd_gap_analysis.md`, `implementation_roadmap.md`, `README.md`).

---

## 9. Future roadmap (M15–M19 — planned / not started)

> **Status:** M15–M19 are **planned / not started** (`docs/implementation_roadmap.md`, `docs/m14_backtesting_audit.md` §9). Partial data-model scaffolds from M2/M6 (`corporate_actions`, `shariah_screenings`, `shariah_snapshots`) exist in code, but the historical datasets and workflows are not built.

| Milestone | Scope | Status | Why it matters (methodology & integrity) |
|---|---|---|---|
| **M15 — Historical Market Data & Point-in-Time Universe** | Real historical NSE OHLCV ingestion, point-in-time universe membership (`UniverseProvider`), listing & delisting dates, historical index constituents | **Planned / blocked on sourced datasets** | Eliminates **survivorship bias** (`B-09`) and replaces the current equal-weight survivor benchmark proxy (`B-14`) with historical index constituents. |
| **M16 — Corporate Actions & Market Calendar** | Complete corporate-action ingestion (splits, bonuses, dividends), adjusted price series for signals/marks with raw prices kept for execution (`B-29`), authoritative NSE trading/holiday calendar (`B-32`, `TD-M2`) | **Planned / partial M2 scaffold only** | Prevents artificial price drops at splits/bonuses from distorting indicators/stops and replaces `BDay` business-day approximations in settlement & session hold logic. |
| **M17 — Point-in-Time Fundamentals & Shariah Operations** | Financial inputs carrying `financial_period_end` and `published_at` timestamps (`B-10`), periodic re-screening of held positions, bulk snapshot import & `NEEDS_REVIEW` workflow (commercial Shariah feed blocked on external provider) | **Planned / blocked on publication-dated data** | Prevents **look-ahead bias in `STRICT` Shariah mode** (currently `screening_date` reflects evaluation run date, not financial filing release date) and avoids false Shariah eligibility claims. |
| **M18 — Frontend Quality Gate** | Expand Vitest + RTL tests (`>= 15` tests covering signal filters, disabled SELL buttons, backtest provenance/segment warnings) and CI gate | **Planned / not started** | Protects M8 workspaces (`BacktestingLab.jsx`, `PaperTrading.jsx`, `Portfolio.jsx`) from regressions; currently only 5 Vitest tests exist (`TD-L2`). |
| **M19 — Security & Deployment Readiness** | Authentication/authorization model (**needs product decision**), stricter production CORS, deployment hardening | **Planned / needs product decision** | Required before any non-local or multi-user deployment (`TD-L3`). |

---

## 10. Critical engineering rules and known risks

### Non-negotiable engineering invariants

1. **`BookState` is the sole live portfolio authority:** Live cash, reserves, ledger entries, and holding quantities/avg cost live only in `portfolio_books` (`app/portfolio/store.py`). Execution holdings (`execution_state`) mirror quantities from `BookState` via `app/execution/reconcile.py`.
2. **Keep `SimBook` isolated:** Backtesting (`app/backtesting/portfolio.py`) must never mutate `BookState`, `execution_state`, or call broker/execution persistence.
3. **Legacy & direct write paths stay disabled:** `POST /api/portfolio/buy|sell` and `POST /api/v1/trades/buy|sell` must remain HTTP `403`. Only `POST /api/v1/execution/orders` (with Shariah, risk, and ownership checks) can mutate paper positions.
4. **No automated broker execution:** Never integrate automated live order routing.
5. **Strict point-in-time discipline:** Never use future bars, next-session prices (except fill simulation after signal generation), future benchmarks, future breadth, or un-dated/post-session Shariah records.
6. **Fail closed on missing prices or Shariah inputs:** Never fabricate missing marks (`entry_price` silent fallback banned in M13/M14) and never pass unverified Shariah symbols (`INSUFFICIENT_DATA` / `UNKNOWN` blocks BUY).
7. **Preserve audit trails & provenance:** Keep append-only `portfolio_valuation_snapshots`, immutable `shariah_snapshots`, `signal_lifecycle_events`, and `EvidenceGrade` / `DataProvenance` tags on all backtest runs.
8. **PostgreSQL safety:**
   - **Never run `docker compose down -v`** — the `halal_quant_pgdata` Docker volume holds persistent local DB state.
   - **Never run destructive DB resets or Alembic downgrades** without explicit approval.
   - **Never stage, commit, or print `.env` or database credentials** (`.env` is gitignored).
   - **Note on `pytest -m postgres`:** `tests/conftest.py` deletes rows where `name == "default"` / `book_name == "default"` (`reset_persisted_default_rows()`) before `@pytest.mark.postgres` tests. Do not run `-m postgres` against a database containing irreplaceable `"default"` book data without a backup.

### Known active risks & technical debt

- **Cross-store persistence split:** `portfolio_books` and `execution_state` are separate DB JSON rows rather than one cross-table DB transaction; recovery relies on idempotent order event markers and `GET /api/v1/portfolio/reconciliation?repair=true`.
- **Runtime scaling (`F-4` / `B-24`):** Breadth is now computed once per session per run (verified for identity), but still over every equity, so it grows with universe size. `build_context` still runs twice per signal and `ensure_benchmark_history` fingerprints every equity about four times per signal. Nothing is measured on a real universe.
- **Unupdated legacy documentation (`TD-M8`, `TD-M9`):** `README.md`, `docs/architecture/current_state.md` (§2), `docs/architecture/backtesting.md`, and `docs/operations/runbook.md` (which still cites `c4d2e8a91f03` instead of `e8f91a2b4c10`) contain pre-M13/pre-M14 descriptions. Treat code + tests + `docs/m14_phase1_review.md` + this handoff as authoritative.
- **Deprecation warning noise (`TD-M1`):** `pytest` emits ~1,900+ warnings largely from `datetime.utcnow()` in SQLAlchemy defaults and stores (harmless today, scheduled for cleanup later).
- **Stray zero-byte `main` file at repo root:** Present since commit `08c1680`; leave untouched unless intentionally removing in a cleanup commit.

---

## 11. Local development and validation commands

> **Standing workflow rule in this repo:** Keep `.env` untracked and use placeholders when sharing configs. Do not run `freeze_m14_baseline.py` concurrently with `pytest` (CPU contention distorts scenario timings).

### 1. Optional PostgreSQL & Alembic migrations

```bash
cd /home/rehan/Downloads/halal_quant_v1
cp .env.example .env
# Edit .env to set DATABASE_URL=postgresql+psycopg://<DB_USER>:<DB_PASSWORD>@localhost:5432/<DB_NAME>
docker compose up -d postgres

cd backend && source .venv/bin/activate
alembic current
alembic upgrade head                 # target head: e8f91a2b4c10 (M13)
python -m scripts.seed_demo_to_db    # optional: loads demo OHLCV into ohlcv_candles
python -m scripts.verify_postgres_setup
```

Backup / restore (run before any risky DB work):

```bash
pg_dump -h localhost -U <DB_USER> <DB_NAME> > backup_$(date +%F).sql
```

### 2. Backend server

```bash
cd /home/rehan/Downloads/halal_quant_v1/backend
source .venv/bin/activate
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

- Health: `GET http://localhost:8000/api/health` and `GET http://localhost:8000/api/v1/health` (check `database_enabled`).

### 3. Backend tests (`pytest`)

`tests/conftest.py` forces isolated in-memory demo mode by default even when `../.env` sets `DATABASE_URL`.

```bash
cd /home/rehan/Downloads/halal_quant_v1/backend

# Focused M14 Phase 1.1 + Phase 1 + PIT regime suite (latest verified: 48 passed)
.venv/bin/python -m pytest \
  tests/test_backtest_phase1_1_m14.py \
  tests/test_backtest_phase1_m14.py \
  tests/test_regime_point_in_time.py -q

# Full backend test suite (latest verified: 133 passed)
.venv/bin/python -m pytest -q

# Optional live PostgreSQL integration tests (touches "default" book/execution/valuation rows!)
.venv/bin/python -m pytest -q -m postgres
```

### 3a. F-4 breadth cache verification (run one at a time; never alongside a freeze)

```bash
cd /home/rehan/Downloads/halal_quant_v1/backend

# 1. New cache tests (expected: 13 passed)
.venv/bin/python -m pytest tests/test_breadth_cache_m14.py -q

# 2. Focused breadth / M14 / point-in-time tests (expected: 61 passed = 13 + 48)
.venv/bin/python -m pytest tests/test_breadth_cache_m14.py tests/test_backtest_phase1_1_m14.py \
  tests/test_backtest_phase1_m14.py tests/test_regime_point_in_time.py -q

# 3. Full backend suite without PostgreSQL (verified 2026-11-27: expect 144 passed, 2 deselected)
.venv/bin/python -m pytest -q -m "not postgres"
# With PostgreSQL running, the full suite collects 146 (expect 146 passed). CAUTION: the postgres-marked tests
# run conftest's reset_persisted_default_rows(), which DELETES the "default" book, execution and valuation rows.
# Do not run this against a database holding data you need; take a pg_dump first.
# .venv/bin/python -m pytest -q

# 4. Baseline unchanged: fresh freeze to /tmp (never overwrite the committed files), then compare.
#    Expect "scenarios_sha256 equal: True" (the hash excludes elapsed time).
.venv/bin/python -m scripts.freeze_m14_baseline --out /tmp/m14_post_f4.json
.venv/bin/python -m scripts.freeze_m14_baseline --compare tests/baselines/m14_post_phase1_1.json /tmp/m14_post_f4.json

# 5. Optional: same-process timing, cached vs scope disabled. The script is no longer on disk; recreate it
#    outside the repo from the method in review section 9.2 before running any timing.
```

### 4. M14 baseline freeze & ablation

```bash
cd /home/rehan/Downloads/halal_quant_v1/backend

# Full-universe baseline (forces DATABASE_URL="" in-process)
.venv/bin/python -m scripts.freeze_m14_baseline \
  --out tests/baselines/m14_post_phase1_1.json

# First-four-symbol ablation
.venv/bin/python -m scripts.freeze_m14_baseline \
  --symbols TCS,INFY,RELIANCE,HDFCBANK \
  --out tests/baselines/m14_ablation_first4.json

# Compare two frozen baselines (metrics + equity.sha256)
.venv/bin/python -m scripts.freeze_m14_baseline \
  --compare tests/baselines/m14_ablation_first4.json tests/baselines/m14_post_phase1_1.json
```

### 5. Frontend dev, tests & build

```bash
cd /home/rehan/Downloads/halal_quant_v1/frontend
nvm use          # Node 22 per .nvmrc (requires >=20.19.0)
npm run dev      # http://localhost:5173
npm run test     # Vitest (5 tests across 3 files)
npm run build    # Production bundle check
```

### 6. Safe Git workflow

```bash
cd /home/rehan/Downloads/halal_quant_v1
git status
git diff --check
# Stage specific files explicitly (never stage .env or scratch files):
# Commit 1 — F-4 breadth cache (only after section 3a passes)
git add backend/app/regime/market_breadth.py backend/app/backtesting/simulator.py backend/tests/test_breadth_cache_m14.py
git diff --cached --name-only   # confirm no .env / credentials before committing
# Commit 2 — docs (with the verified test results filled in) and Phase 1.1 baselines
git add docs/m14_phase1_review.md docs/PROJECT_HANDOFF.md backend/tests/baselines/m14_post_phase1_1.json backend/tests/baselines/m14_ablation_first4.json
git diff --cached --name-only
```

---

## 12. New chat startup instructions (for ChatGPT continuity)

When starting a brand-new ChatGPT conversation with no access to prior chat history:

1. **Upload** `docs/PROJECT_HANDOFF.md` (and `docs/m14_phase1_review.md` if reviewing M14 specifics).
2. **Instruct ChatGPT** to treat `docs/PROJECT_HANDOFF.md` as the authoritative project context and obey all product, Shariah, ledger-isolation, and PostgreSQL safety rules listed in Sections 3 and 10.
3. **Paste current ground truth:** latest `git status`, `git log -n 3 --oneline`, and the latest `pytest` / `vitest` output from Cursor.
4. **Request the exact next step** from **Section 7 (Current exact project state)** and **Section 8 (Remaining M14 work)**—for example: *"Verify the F-4 breadth cache with the section 11.3a commands and commit it, without changing Phase 1.1 logic or starting Phase 2."*
