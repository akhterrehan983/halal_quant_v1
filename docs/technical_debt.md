# Halal Quant V1 — Technical Debt Register (Milestone 10)

**Last updated:** 2026-11-22 (M11: TD-C1, TD-C2 resolved)  
**Source:** Code inspection, `docs/architecture/system_audit.md` (M9), M10 PRD gap analysis.  
**Severity:** Critical | High | Medium | Low

---

## Critical

### TD-C1 — Unified signal regime uses full benchmark history in historical backtests

| Field | Detail |
|-------|--------|
| **Status** | **RESOLVED (M11)** |
| **Fix** | `evaluation_date()` + `benchmark_slice(as_of_date=)` in `signals/generator.py` and `regime/benchmark.py`. |
| **Tests** | `tests/test_regime_point_in_time.py` |

### TD-C2 — Market breadth always uses latest cross-section

| Field | Detail |
|-------|--------|
| **Status** | **RESOLVED (M11)** |
| **Fix** | `compute_universe_breadth(as_of_date=...)` in `regime/market_breadth.py`. |
| **Tests** | `tests/test_regime_point_in_time.py` |

---

## High

### TD-H1 — Dual portfolio systems (legacy vs research/execution book)

| Field | Detail |
|-------|--------|
| **Status** | **Substantially resolved (M12)** — legacy writes blocked; reads from book; UI aligned. |
| **Remaining** | Dead `PaperPortfolio` module; separate execution JSON for orders/ownership metadata. |
| **Tests** | `tests/test_integration_m12.py` |

### TD-H2 — Valuation snapshot history absent

| Field | Detail |
|-------|--------|
| **Status** | **Resolved (M13)** — `portfolio_valuation_snapshots`, drawdown audit from immutable rows, v1 APIs + Portfolio UI. |
| **Remaining** | No automatic post-fill snapshot hook; no external scheduler bundled. |
| **Tests** | `tests/test_valuation_m13.py` |

### TD-H3 — Backtest sensitivity does not vary M3 strategy parameters

| Field | Detail |
|-------|--------|
| **Severity** | High (product expectation vs M7 spec) |
| **Module** | `app/backtesting/validation_sensitivity.py` |
| **Issue** | Grid only changes `hold_days` and `min_signal_score`, not breakout lookback, RSI thresholds, etc. |
| **Evidence** | M9 fixed “stub” partially; `system_audit.md` H6. |
| **Fix direction** | Parameter overlay on `StrategyConfig` with versioned backtest config snapshot. |

### TD-H4 — Survivorship / point-in-time universe

| Field | Detail |
|-------|--------|
| **Severity** | High (backtest validity) |
| **Module** | `app/backtesting/universe.py` |
| **Issue** | `survivorship_warning: True` for demo; no listing/delisting dates. |
| **Evidence** | `backtesting.md` Known limitations. |
| **Fix direction** | Universe provider interface + data ingestion when available. |

### TD-H5 — Execution vs research holdings dual store

| Field | Detail |
|-------|--------|
| **Status** | **Substantially resolved (M12)** — book owns qty; `sync_overlay_from_book` + reconciliation API. |
| **Remaining** | Overlay still a second persistence blob (ownership fields only by policy). |
| **Tests** | `tests/test_integration_m12.py` |

### TD-H6 — Walk-forward folds do not isolate parameter tuning

| Field | Detail |
|-------|--------|
| **Severity** | High (methodology) |
| **Module** | `app/backtesting/walk_forward.py` |
| **Issue** | Each fold reruns simulator on full date span in config; not separate train/val/test metric storage per M7 methodology. |
| **Fix direction** | Per-fold configs, frozen parameters, OOS metrics only from test windows. |

---

## Medium

### TD-M1 — `datetime.utcnow()` deprecation (196 test warnings)

| Field | Detail |
|-------|--------|
| **Severity** | Medium |
| **Modules** | `backtesting/store.py`, `shariah/snapshots.py`, `signals/persistence.py`, `execution/order_manager.py`, `signals/lifecycle.py`, SQLAlchemy defaults |
| **Fix** | Replace with `datetime.now(timezone.utc)`. |

### TD-M2 — Settlement calendar approximate

| Field | Detail |
|-------|--------|
| **Severity** | Medium |
| **Modules** | `market_data/calendar.py`, `execution/settlement.py`, `backtesting/validation.py` |
| **Issue** | Business-day offset; sample 2024 subset; not authoritative NSE holidays. |

### TD-M3 — API error shape inconsistency

| Field | Detail |
|-------|--------|
| **Severity** | Medium |
| **Evidence** | `system_audit.md` Medium section |
| **Impact** | Frontend error handling complexity. |

### TD-M4 — Proposal dual-store (memory vs PG)

| Field | Detail |
|-------|--------|
| **Severity** | Medium |
| **Module** | `portfolio/store.py` |
| **Issue** | Proposal IDs and sequences differ between demo mem and DB mode. |

### TD-M5 — Backtest symbol cap (`syms[:4]`)

| Field | Detail |
|-------|--------|
| **Severity** | Medium |
| **Module** | `simulator.py` |
| **Issue** | Performance guard hides full-universe behavior. |

### TD-M6 — Benchmark comparison in backtests

| Field | Detail |
|-------|--------|
| **Severity** | Medium |
| **Module** | `simulator.py` `benchmark_return=None` |
| **Issue** | Metrics lack aligned benchmark alpha/beta in default run. |

### TD-M7 — Missing `POST /backtests/compare`

| Field | Detail |
|-------|--------|
| **Severity** | Medium |
| **Evidence** | M7 API list vs `app/api/v1/backtests.py` |

### TD-M8 — README structure outdated

| Field | Detail |
|-------|--------|
| **Severity** | Medium |
| **Issue** | README still shows `api/` empty and routes in `main.py` only. |

### TD-M9 — `current_state.md` mixed-era content

| Field | Detail |
|-------|--------|
| **Severity** | Medium |
| **Issue** | Header updated M9 but §2 still M1 tree; misleads auditors. |

---

## Low

### TD-L1 — Starlette TestClient / httpx deprecation warning

| Field | Detail |
|-------|--------|
| **Severity** | Low |
| **Fix** | Adopt `httpx2` or pin when ecosystem stabilizes. |

### TD-L2 — Frontend test surface minimal

| Field | Detail |
|-------|--------|
| **Severity** | Low |
| **Evidence** | Only `navigation.test.jsx`, `format.test.js` |
| **Impact** | Regressions in pages undetected. |

### TD-L3 — No API authentication

| Field | Detail |
|-------|--------|
| **Severity** | Low (for local research) / High (if deployed) |
| **Note** | Documented limitation; not debt if product stays local-only. |

### TD-L4 — Sequence ID reset on demo restart

| Field | Detail |
|-------|--------|
| **Severity** | Low |
| **Module** | In-memory stores |

### TD-L5 — Corporate actions empty in typical demo DB

| Field | Detail |
|-------|--------|
| **Severity** | Low until real data loaded |

---

## Documentation debt

| ID | Item | Action |
|----|------|--------|
| DD-1 | External PRD not in repo | Add `docs/product_brief.md` or link when canonical |
| DD-2 | `implementation/progress.md` vs `progress.md` | Consolidate or cross-link |
| DD-3 | Post-M10 `current_state.md` refresh | Separate audit from M10 gap doc |

---

## Deferred M9 issues (tracked)

| ID | From system_audit | Status |
|----|-------------------|--------|
| C4 | Benchmark regime look-ahead | **Fixed (M11)** |
| H5 | Drawdown peak only on valuation calls | Partial (TD-H2) |
| H7–H12 | Dual books, PG execution E2E, etc. | Open (TD-H1, TD-H5) |

---

## Maintenance order (suggested)

1. ~~TD-C1 + TD-C2 (research trust)~~ **Done (M11)**  
2. TD-H1 + TD-H5 (ledger unity)  
3. TD-H2 (valuation history)  
4. TD-H3 + TD-H6 (backtest methodology)  
5. TD-M1 (warning noise / future Py breakage)  
6. TD-L2 (frontend regression net)