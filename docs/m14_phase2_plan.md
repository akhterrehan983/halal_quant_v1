# M14 Phase 2 — Independent Walk-Forward Evaluation Plan

> **Document status:** **Approved with the clarifications in section 0** (2026-11-27). Where section 0 conflicts with later text, section 0 wins.
> **Implementation status:** Implementation of the approved scope is in progress in the working tree (additive files only; see section 12). No existing application logic, v1 endpoint/schemas, baseline JSON artifacts, or strategy defaults are modified.
> **Verified repository baseline:** Branch `main` at commit `16163c0` (*"M14 F-4: run-scoped as-of breadth cache"*, synced with `origin/main`), following `3d5714c` (*"M14: F-4 verification, Phase 1.1 baselines, handoff"*) and `498f8bc` (*"Harden M14 backtesting phase 1"*).
> **Primary audit findings addressed:** `B-17` / `TD-H6` (walk-forward blends train and test spans into one simulation and labels it out-of-sample), plus multiple-testing disclosure hook (`B-23` partial) for candidate selection.

---

## 0. Approved Clarifications (authoritative)

1. **Warm-up is history only.** Bars before a segment's start initialise causal indicators (windows, regime, breadth, benchmark slices) and nothing else. They never produce trades, cash changes, positions, equity points, or metrics for the segment being evaluated. Each segment is one `run_backtest(start_date=segment_start, end_date=segment_end)` call, whose sessions are exactly the calendar sessions inside `[segment_start, segment_end]`; the engine additionally asserts that every trade and equity point lies inside the segment window and fails closed otherwise.
2. **Window restriction.** Training trades/metrics come only from the training window; test trades/metrics only from the test window. Nothing is computed over `[train_start, test_end]`.
3. **Fresh state per segment.** Every segment uses a fresh `SimBook` and a fresh `breadth_cache_scope()` (both created inside `run_backtest`). No cash, holdings, pending orders, ownership-delayed stops, or portfolio state carries between segments or folds. The engine refuses to run inside an already-active breadth scope, because a nested scope would share one memo.
4. **`MAX_SEGMENT_RUNS = 24`, counted exactly.** Every actual `run_backtest()` invocation counts: each training candidate run (the base configuration is always one of the candidates, so a fallback to it needs no extra run) plus one test run per fold. A fold with 12 training candidates plus its test run needs 13 runs. Per fold: `runs = candidates + 1`; total `= sum over folds`. The limit is enforced at the API boundary, before any simulation starts (HTTP 400), and the engine records `run_budget = {max, planned, executed}` and an ordered `run_log`. `MAX_CANDIDATES_PER_FOLD = 12` counts deduplicated candidates including the base.
5. **Training-sample floor.** `min_train_trades = 3` is the initial mechanical-verification floor (not a statistical standard). The response warns when the selected configuration has fewer than 10 training trades. If no candidate qualifies, the engine falls back deterministically to `base_config`, reports `no_candidate_qualified = true` with `selection.status = "fallback_no_candidate_qualified"` and `tuned = false`, and the result is never labelled as tuned.
6. **Embargo in sessions.** The embargo is the number of complete tradable sessions `d` in the same session calendar used for fold generation with `train_end < d < test_start`. Invalid or insufficient folds are rejected deterministically (HTTP 400, naming the fold). Incomplete trailing windows are never shortened silently: auto-generation reports `dropped_trailing_sessions` and a warning, and an explicit fold whose test window is not covered by data (last session more than `COVERAGE_GAP_DAYS = 5` calendar days before `test_end`) is rejected.
7. **Deduplicate and hash the effective configuration.** Candidates are deduplicated by effective configuration (first occurrence wins; base is index 0): `min_signal_score` is normalised to `max(value, 75)` because a unified signal is a BUY only at score >= 75, and `hold_days=None` resolves to the simulator default (10 swing / 60 positional). A warning is emitted for every `min_signal_score <= 75`. The hash covers the **complete** effective configuration: all `BacktestConfig` fields except the segment-specific `name`/`start_date`/`end_date`, plus the effective horizon thresholds, scoring weights, category thresholds, enabled strategies, registered benchmarks and signal-window constants. The selected configuration hash is computed and written to the run log **before** the test segment runs, and the test configuration's hash is asserted equal to it.
8. **Evidence grade stays DEMO on synthetic data.** Passing software tests proves the walk-forward machinery, not strategy validity.

Deviation from the original text: `include_base_candidate` is removed. The base configuration is always candidate 0 (needed for deterministic fallback and exact budget accounting).

---

## 1. Current Implementation Assessment

Every module below was inspected directly at commit `16163c0`.

### 1.1 Walk-forward engine — `backend/app/backtesting/walk_forward.py`

```9:25:backend/app/backtesting/walk_forward.py
def walk_forward(config: BacktestConfig, folds: list[dict]) -> dict:
    """Chronological folds: each {train_end, val_end, test_end} dates as ISO strings."""
    results = []
    for fold in folds:
        c = config.model_copy()
        c.start_date = date.fromisoformat(fold["train_start"])
        c.end_date = date.fromisoformat(fold["test_end"])
        c.name = f"{config.name}_wf_{fold.get('label', '')}"
        run = run_backtest(c)
        results.append(
            {
                "fold": fold,
                "metrics": run.metrics.model_dump(mode="json") if run.metrics else None,
                "status": run.status.value,
            }
        )
    return {"folds": results, "notice": "Out-of-sample segments embedded per fold end_date"}
```

**Confirmed defects (`B-17` / `TD-H6`):**
1. **Blended train + test simulation:** Sets `start_date = fold["train_start"]` and `end_date = fold["test_end"]` and executes **one** continuous `run_backtest(c)`. Cash, open positions, pending orders, drawdown peaks, and trade statistics carry continuously from training into testing.
2. **False out-of-sample claim:** Returns `"notice": "Out-of-sample segments embedded per fold end_date"`, even though `metrics` are computed over the entire `[train_start, test_end]` span (`train_end` and `val_end` are never read).
3. **Docstring vs code mismatch & zero validation:** The docstring lists `{train_end, val_end, test_end}` without `train_start`, while the implementation indexes `fold["train_start"]` and `fold["test_end"]` directly. Missing keys raise raw `KeyError`; inverted or overlapping dates, empty fold lists, and overlapping test spans across folds are not validated.
4. **No training selection or parameter freeze:** No candidate grid is evaluated on training data, and no selected configuration or hash is recorded.
5. **Dropped provenance & warnings:** `run.evidence_grade`, `run.data_provenance`, `run.warnings`, `run.validation`, and `run.trades` are discarded.

### 1.2 API layer — `backend/app/api/v1/backtests.py` & `backend/app/main.py`

- `POST /api/v1/backtests/{backtest_id}/walk-forward` (`backend/app/api/v1/backtests.py` lines `14–16`, `108–113`) accepts `WalkForwardBody(folds: list[dict])`, loads the persisted `BacktestRun` from `app.backtesting.store.get_run(backtest_id)` (`404` if absent), and returns `walk_forward(run.config, body.folds)`.
- Unlike `create_backtest` and `execute_backtest`, `wf()` does **not** catch `ValueError` or `KeyError`, so malformed date strings or `train_start >= test_end` surface as unhandled `500` errors.
- `backend/app/main.py` currently mounts `legacy_router` (`/api/*`) and `api_v1_router` (`/api/v1/*`); no `/api/v2` router exists yet.
- Frontend (`frontend/src/pages/BacktestingLab.jsx`, `frontend/src/lib/api.js`) **does not call** `/walk-forward` today. Preserving v1 while introducing a versioned v2 endpoint therefore breaks zero frontend workflows while honoring Decision 3 of `docs/m14_backtesting_audit.md` (§13).

### 1.3 Simulator & state interfaces — `backend/app/backtesting/simulator.py` & `portfolio.py`

- `run_backtest(config: BacktestConfig) -> BacktestRun` (`simulator.py:349`) already has strong per-call isolation properties built in Phase 1 / Phase 1.1 / F-4:
  - Wraps each run in `with breadth_cache_scope():` (`market_breadth.py:29`), creating a fresh `ContextVar` dict and discarding it on exit.
  - Instantiates a fresh `SimBook(cash=D(config.initial_capital))`, empty `curve`, `trades`, `pending`, and `stats` (`simulator.py:434–450`). Never touches live `BookState` (`app/portfolio/store.py`) or `execution_state` (`app/execution/store.py`).
  - Calls `_load_feed(sym, config.end_date)` → `repo.history_upto(sym, end=config.end_date)` (`simulator.py:94–96`, `repository.py:115–141`). **Crucial property:** bars strictly after `config.end_date` are **never loaded** into `_SymbolFeed`. Meanwhile, bars before `config.start_date` *are* loaded into `_SymbolFeed.frame` so `feed.window(session, 520)` can warm up indicators, while `sessions` (`simulator.py:364`) restricts simulated trading days to `config.start_date <= d <= config.end_date`.
  - On the final session of a segment, `_queue_entry` calls `feed.next_bar(session)` (`simulator.py:314`), which returns `None` because the feed ends at `config.end_date`, incrementing `stats["unfilled_orders"]` without reading `end_date + 1`.
- **Known simulator behavior relevant to segment boundaries (`B-15`, deferred to Phase 3):** Positions still open on `last_session` remain marked-to-market in `curve[-1].equity` (affecting segment `total_return`, `max_drawdown`, `volatility`, and `sharpe`) and are **not** force-closed into `run.trades`. Because each segment runs in its own `SimBook`, those open positions cannot leak into the next segment, but Phase 2 reporting must disclose end-of-segment open position counts and invested value explicitly.

### 1.4 Strategy & configuration interfaces — `schemas.py`, `strategies/config.py`, `signals/scoring.py`

- `BacktestConfig` (`backend/app/backtesting/schemas.py:45–75`) exposes `horizon`, `strategies`, `symbols`, `shariah_mode`, `cost_scenario`, `slippage_bps`, `max_positions`, `max_adv_participation`, `random_seed`, `min_signal_score`, and `hold_days`.
- `HorizonConfig` (`backend/app/strategies/config.py:7–37`) is a `@dataclass(frozen=True)` holding all indicator/rule thresholds (`breakout_lookback`, `breakout_min_rel_volume`, `pullback_rsi_min/max`, `mean_reversion_rsi_max`, `trend_min_adx`, `atr_stop_mult`, `atr_target_mult`, etc.). `evaluator.build_context` calls `get_horizon_config(horizon)` directly with **no override mechanism** (`B-22`, scheduled for Phase 5).
- `ScoringWeights` and `CategoryThresholds` (`backend/app/signals/config.py`) are hardcoded defaults in `generate_unified_signal` / `score_signal` / `category_from_score`:
  - **Code-level finding on `min_signal_score`:** `category_from_score` (`signals/scoring.py:9–18`) assigns `SignalCategory.BUY` only when `score >= 75` (`STRONG_BUY` when `>= 85`), and `simulator.py:496–499` rejects anything not in `{BUY, STRONG_BUY}` *before* checking `sig.overall_score < config.min_signal_score`. Consequently, **for real unified signals, every `min_signal_score <= 75` (including `0`, `55`, `65`, `75` in `validation_sensitivity.py`) behaves identically to `75`**. Only thresholds in `76..100` (compared against a baseline of `<= 75`) change candidate filtering on real signals.

### 1.5 Existing test coverage

- `backend/tests/` has 19 test modules (146 collected tests: 144 non-Postgres + 2 `@pytest.mark.postgres`), **none** of which call `walk_forward` or `POST /api/v1/backtests/{id}/walk-forward`.

---

## 2. Proposed Architecture and Data Flow

### 2.1 Module layout (additive, zero impact on Phase 1.1 baselines)

| File | Action | Responsibility |
|---|---|---|
| `backend/app/backtesting/walk_forward.py` | **Unchanged** | Keeps legacy v1 `walk_forward(config, folds)` byte-for-byte intact so existing callers cannot break. |
| `backend/app/backtesting/schemas.py` | **Unchanged** | Core `BacktestConfig`, `BacktestMetrics`, `CompletedTrade`, `EquityPoint`, and `BacktestRun` stay untouched, guaranteeing `freeze_m14_baseline.py` serialization and `scenarios_sha256` cannot drift. |
| `backend/app/backtesting/walk_forward_schemas.py` | **New (Phase 2)** | Typed Pydantic v2 request/response models for folds, auto-fold generation, bounded parameter grids, candidate scores, segment outputs, stitched OOS summary, and disclosures. |
| `backend/app/backtesting/walk_forward_v2.py` | **New (Phase 2)** | Pure orchestration engine: session-calendar extraction, fold builder & validator, candidate expander, train-only selector, config hashing, isolated test execution, and stitched OOS aggregation. Calls `simulator.run_backtest` as a black box. |
| `backend/app/api/v2/__init__.py`, `router.py`, `backtests.py` | **New (Phase 2)** | Versioned `/api/v2` router exposing `POST /api/v2/backtests/{backtest_id}/walk-forward` and stateless `POST /api/v2/backtests/walk-forward`. |
| `backend/app/main.py` | **1-line mount (Phase 2)** | `app.include_router(api_v2_router)` alongside `legacy_router` and `api_v1_router`. |
| `backend/tests/test_walk_forward_m14.py` | **New (Phase 2)** | Unit, isolation, price-mutation non-leakage, reproducibility, live-book safety, v1 compatibility, and v2 API tests. |

### 2.2 End-to-end execution flow

```text
WalkForwardV2Request (base_config + explicit folds OR auto_folds + selection_spec)
  │
  ├─ 1. Validate base_config & selection_spec (bounds, candidate count <= MAX_CANDIDATES_PER_FOLD,
  │     cost/provenance/score-floor checks).
  │
  ├─ 2. Resolve trading-session calendar across tradable equities (benchmarks excluded via
  │     universe_for_backtest) capped at overall_end_date — never reading bars > overall_end_date.
  │
  ├─ 3. Resolve & validate folds:
  │     • If auto_folds: slice session calendar into rolling or expanding [train, embargo, test] windows
  │       after reserving >= warmup_sessions prior bars.
  │     • Validate intra-fold order (train_start < train_end < test_start < test_end), session counts,
  │       embargo gap, warm-up bar availability (>= 60), and strict inter-fold test non-overlap
  │       (fold[k-1].test_end < fold[k].test_start).
  │     • Enforce total run budget at the API boundary: sum over folds of (len(candidates) + 1) <= MAX_SEGMENT_RUNS.
  │
  ├─ 4. For each fold k = 0 .. K-1 (strictly sequential, zero state carried across folds):
  │     ├─ 4a. TRAINING PHASE (touches data <= fold[k].train_end ONLY):
  │     │      For each candidate c_j in predeclared candidate list:
  │     │        train_cfg = apply_candidate(base_config, c_j, fold[k].train_start, fold[k].train_end)
  │     │        train_run_j = run_backtest(train_cfg)   # fresh SimBook, fresh breadth_cache_scope
  │     │
  │     ├─ 4b. PARAMETER SELECTION & FREEZE (inputs: {train_run_j} ONLY):
  │     │      winner = select_candidate(train_runs, objective, min_train_trades)
  │     │      test_cfg = apply_candidate(base_config, winner.params, fold[k].test_start, fold[k].test_end)
  │     │      selected_config_hash = canonical_config_sha256(test_cfg, exclude_dates=True)
  │     │
  │     └─ 4c. OUT-OF-SAMPLE TEST PHASE (frozen test_cfg; fresh SimBook; touches <= fold[k].test_end):
  │            test_run = run_backtest(test_cfg)         # runs ONCE; never feeds back into any selection
  │
  └─ 5. Aggregate & return WalkForwardV2Response:
        • Per-fold report: boundaries, gap, warm-up count, candidate table, train_result, selected_params,
          selected_config_hash, selection_status, and isolated test_result.
        • Top-level oos_summary built EXCLUSIVELY from {fold[k].test_result}: stitched OOS equity curve,
          concatenated OOS trades, oos_metrics, fold dispersion, provenance, evidence_grade, and warnings.
```

---

## 3. Fold Definition and Generation Design

### 3.1 Why each fold has `train` + optional `gap` + `test` (no ignored `val_end`)

In walk-forward evaluation, each chronological split $k$ acts as its own train/validation pair when rolling forward, or uses `train` to pick from a small predeclared grid and `test` as the strictly untouched out-of-sample evaluation window. The legacy `walk_forward.py` accepted a `val_end` key in its docstring and silently ignored it. Phase 2 defines **three** explicit chronological zones per fold — **training** `[train_start, train_end]`, **optional embargo/gap** `(train_end, test_start)`, and **out-of-sample test** `[test_start, test_end]` — every one of which has enforced semantics. (Callers wanting a final untouched holdout vault after walk-forward simply set `overall_end_date` prior to their vault period.)

### 3.2 Explicit fold specification & validation rules

Each `WalkForwardFoldInput` contains:
- `label: str | None` (defaults to `"fold_1"`, `"fold_2"`, …)
- `train_start: date`, `train_end: date`
- `test_start: date`, `test_end: date`

**Mandatory validation invariants (violation raises `ValueError` → HTTP `400`):**
1. **Strict intra-fold chronology:** `train_start < train_end < test_start <= test_end`, and because `BacktestConfig.validate_dates()` requires `start_date < end_date`, we enforce strict `test_start < test_end` as well:
   `train_start < train_end < test_start < test_end`.
2. **No train/test overlap:** `train_end < test_start` guarantees at least 1 calendar day (and at least the next distinct trading session) separates the last training bar from the first test session.
3. **Optional minimum gap / embargo enforcement:** Request field `min_embargo_sessions: int = 0` (`>= 0`). Let $S$ be the sorted union of trading dates across the tradable universe up to `overall_end_date`. The count of sessions $d \in S$ satisfying `train_end < d < test_start` must be `>= min_embargo_sessions`. (Setting `min_embargo_sessions = 5`, for instance, separates the end of training from `test_start` by one full trading week, preventing overlap with `BDay(3)` settlement windows.)
4. **Minimum segment sessions:** Both `train` (`[train_start, train_end]`) and `test` (`[test_start, test_end]`) must contain **at least 2 trading sessions** in $S$ so return/volatility series and next-session fills (`signal` on session $t$, `fill` on session $t+1$) are well-defined.
5. **Warm-up history requirement:** At least one tradable symbol must have **`>= MIN_SIGNAL_BARS` (`60`)** bars on or before `fold[0].train_start` (checked via `count_upto(train_start)` on histories capped at `overall_end_date`). If the maximum pre-`train_start` bar count across tradable symbols is in `[60, 251]`, the fold is valid (matching `simulator.py:493`) **and** records a structured warning: `"Partial indicator warm-up (< 252 bars before train_start): sma200, high_52w, and rel_252d use fallback/partial history on early train sessions."`
6. **Strict inter-fold ordering & disjoint OOS test windows:** Across folds $k = 0 \dots K-2$:
   - `folds[k].train_start <= folds[k + 1].train_start`
   - `folds[k].train_end < folds[k + 1].train_end`
   - **`folds[k].test_end < folds[k + 1].test_start`** (mandatory: OOS test windows must be pairwise disjoint and strictly chronological so no market session is ever counted twice in `oos_summary`).

### 3.3 Automatic multi-fold generator (`auto_folds`)

Callers may supply **either** `folds: list[WalkForwardFoldInput]` **or** `auto_folds: WalkForwardAutoFoldSpec` (mutually exclusive; providing both or neither fails validation):

- `mode: Literal["rolling", "expanding"] = "rolling"`
- `overall_start: date | None = None` (optional lower bound on usable history, including warm-up)
- `overall_end: date | None = None` (defaults to `base_config.end_date`)
- `warmup_sessions: int = 60` (`>= 60`; recommended `252` on multi-year histories)
- `train_sessions: int = 120` (`>= 20`)
- `embargo_sessions: int = 0` (`>= 0`)
- `test_sessions: int = 40` (`>= 5`)
- `step_sessions: int | None = None` (defaults to `test_sessions`; must satisfy `step_sessions >= test_sessions` so generated test windows are automatically non-overlapping!)

**Session-index slicing algorithm:**
Let $S = [s_0, s_1, \dots, s_{N-1}]$ be the sorted trading dates across tradable equities with `overall_start <= s_i <= overall_end` (or `s_i <= overall_end` if `overall_start is None`).
- Reserve warm-up indices `0 .. warmup_sessions - 1`. First fold starts at `first_train_idx = warmup_sessions`.
- For fold $k = 0, 1, \dots$ while `anchor_end + embargo_sessions + test_sessions <= N`:
  - If `mode == "rolling"`: `tr_start_idx = warmup_sessions + k * step_sessions`, `tr_end_idx = tr_start_idx + train_sessions - 1`.
  - If `mode == "expanding"`: `tr_start_idx = warmup_sessions`, `tr_end_idx = warmup_sessions + train_sessions - 1 + k * step_sessions`.
  - `te_start_idx = tr_end_idx + 1 + embargo_sessions`.
  - `te_end_idx = te_start_idx + test_sessions - 1`.
  - Stop when `te_end_idx >= N`.
- **Insufficient history & trailing remainder rules:**
  - If $N < \text{warmup\_sessions} + \text{train\_sessions} + \text{embargo\_sessions} + \text{test\_sessions}$, zero folds can be formed → raise `ValueError` with exact counts (`available_sessions`, `required_minimum_sessions`, breakdown of `warmup + train + embargo + test`).
  - Trailing sessions after the last complete `te_end_idx` (`dropped_trailing_sessions = N - 1 - last_te_end_idx`) are **not** turned into a truncated stub fold; they are reported in `fold_generation.dropped_trailing_sessions` so every OOS fold has uniform horizon length.

---

## 4. Training and Parameter Selection Design

### 4.1 Audit of parameters in the current codebase

Before designing selection, every candidate knob was traced through `simulator.py`, `signals/`, and `strategies/`:

| Parameter / config location | Affects `run_backtest` today? | Phase 2 status & exact reason |
|---|---|---|
| `BacktestConfig.hold_days` (`int \| None`) | **Yes** (`simulator.py:216, 246, 433`) | **Eligible in Phase 2.** Controls `time_exit_authorized` once `session >= sell_authorized_date` (`entry + BDay(3)`). Values `>= 4` change swing/positional holding duration. |
| `BacktestConfig.min_signal_score` (`int`, `75..95`) | **Yes, only for `>= 75`** (`simulator.py:496–499`, `scoring.py:9–18`) | **Eligible in Phase 2 (with score-floor guard).** On real unified signals, `SignalCategory.BUY` already requires `score >= 75` (`STRONG_BUY >= 85`). Grid values `< 75` are redundant on real unified signals unless comparing `75` (all `BUY`+`STRONG_BUY`) vs `80` / `85` (`STRONG_BUY` only) / `90`. Values `< 75` will emit a validation warning (or be rejected if duplicate effective thresholds collapse). |
| `BacktestConfig.max_positions` (`int`, `1..10`) | **Yes** (`simulator.py:266, 483`) | **Optional / opt-in in Phase 2.** Alters portfolio concentration and cash deployment rather than per-signal entry/exit rules; disabled by default in the grid unless explicitly supplied. |
| `HorizonConfig.*` (`strategies/config.py`: `breakout_lookback`, `pullback_rsi_*`, `trend_min_adx`, `atr_stop_mult`, `atr_target_mult`, etc.) | **No** (frozen dataclass, no pass-through from `BacktestConfig`) | **Excluded in Phase 2 — prerequisite is Phase 5 (`B-22`).** Pretending to optimize indicator lookbacks or ATR multiples without `B-22` would be fraudulent. Phase 2 structures `WalkForwardCandidate` so an optional `strategy_overrides` map can be added in Phase 5 without changing v2 routes. |
| `ScoringWeights` / `CategoryThresholds` (`signals/config.py`) | **No** (module constants) | **Excluded in Phase 2** (not plumbed through `BacktestConfig`). |
| `BacktestConfig.strategies` (`list[str]`) | **No** (`simulator.py` ignores it; calls `generate_unified_signal` over global `_ENABLED`) | **Excluded in Phase 2** (`B-31`). Must not mutate global `strategies.registry._ENABLED`. |
| `BacktestConfig.max_adv_participation`, `random_seed` | **No** (unread in `simulator.py`) | **Excluded in Phase 2** (`B-07` is Phase 3; `B-31` is Phase 4). |
| `cost_scenario`, `slippage_bps`, `shariah_mode` | Environmental / mandate assumptions, not tunable alpha knobs | **Forbidden in candidate grid** (held fixed from `base_config` across all train and test runs). |

### 4.2 Selection modes & bounded candidate grid

`WalkForwardSelectionSpec` supports two explicit modes:

1. **`mode = "fixed"` (default when no grid is passed):**
   - Evaluates **1** candidate (the frozen `base_config`) on `train` (for in-sample diagnostics and comparison) and **1** run on `test` (for OOS evaluation).
   - Useful for pure out-of-sample stability checks across rolling windows with **zero** parameter-fitting degrees of freedom (`candidates_per_fold = 1`).
2. **`mode = "grid_search"`:**
   - Predeclared, bounded Cartesian grid over non-empty lists supplied in `grid`:
     - `hold_days: list[int] | None` — each in `[4, 120]`, unique, sorted.
     - `min_signal_score: list[int] | None` — each in `[0, 100]` (recommended `[75, 80, 85]`), unique, sorted; emits a warning if more than one value is `<= 75` because unified `BUY` gating treats all `<= 75` identically.
     - `max_positions: list[int] | None` — optional, each in `[1, 10]`, unique, sorted.
   - **Hard bounds (see section 0, items 4 and 7):**
     - `1 <= deduplicated_candidates (including base) <= MAX_CANDIDATES_PER_FOLD` (`12`).
     - `sum over folds of (candidates + 1) <= MAX_SEGMENT_RUNS` (`24` synchronous `run_backtest` calls). Exceeding either cap fails closed (`400`) before any simulation starts. The raw Cartesian grid is also capped at 64 combinations at the schema level (`422`).

### 4.3 Training-only objective, minimum-trade guard, fallback, and tie-breaking

For fold $k$, selection inspects **only** `{train_run_j.metrics}` ($j = 0 \dots M-1$):

- **Allowed `objective` values:**
  - `"sharpe"` (default): `metrics.sharpe` (`Decimal`; ineligible if `sharpe is None`).
  - `"total_return"`: `metrics.total_return` (`Decimal`).
  - `"return_over_max_drawdown"`: `total_return / max_drawdown` when `max_drawdown > 0`; if `max_drawdown == 0` and `total_return > 0`, treated as `+Infinity` ranked by `total_return`; if `total_return <= 0` and `max_drawdown == 0`, score `0`.
- **Minimum training sample guard (`min_train_trades: int = 3`, configurable `>= 0`):**
  - Any candidate with `train_run.metrics.total_trades < min_train_trades` (or `objective_value is None`) is marked `eligible = False` so a 1-trade outlier cannot hijack `sharpe`.
- **Deterministic fallback when zero candidates qualify (section 0, item 5):**
  - On short windows, sparse signals, or `STRICT` Shariah mode without snapshots (0 trades), *all* candidates may have `total_trades < min_train_trades`.
  - Fallback rule: select the base configuration, which is always candidate index `0`. Set `selection.status = "fallback_no_candidate_qualified"`, `no_candidate_qualified = true`, `tuned = false`, and record a fold warning. **Test data are never consulted.** Other statuses: `fixed_config` (mode `fixed`), `single_candidate_no_selection` (grid collapsed to the base after deduplication), `selected_on_train` (at least two candidates and a qualifying winner; `tuned = true`).
  - Independent of status, a warning is emitted when the selected configuration has fewer than 10 training trades.
- **Deterministic tie-breaking among eligible candidates:**
  Ranked by exact `Decimal` tuple:
  `(objective_value DESC, total_return DESC, -max_drawdown DESC, -candidate_index DESC)` (lowest `candidate_index` wins exact ties).
- **Canonical configuration hash (`selected_config_hash`):**
  Before calling `run_backtest` on the test window, serialize the complete effective configuration (section 0, item 7), excluding only the segment-specific `name`, `start_date`, and `end_date` (`json.dumps(..., sort_keys=True)`), and compute `hashlib.sha256(...).hexdigest()`. Record `base_config_hash`, a `config_hash` per candidate, and the per-fold `selected_config_hash` in the run log before the test run starts.

---

## 5. Segment Isolation and Stitched Out-of-Sample Rules

### 5.1 Segment isolation invariants

Every `train` candidate run and every `test` run calls `run_backtest(segment_cfg)` independently:
1. **Fresh `SimBook` (`initial_capital = base_config.initial_capital`):** Cash starts at `initial_capital`; `positions = {}`, `realized_pnl = 0`, `costs_paid = 0`.
2. **Zero order/exit carryover:** `pending = []` at segment start; any queued order at `train_end` or `SimPosition` still open at `train_end` (including `stop_pending = True` ownership-delayed stops) dies with the `train` `BacktestRun` object and cannot appear in `test`.
3. **Fresh `breadth_cache_scope()`:** Exits at the end of every `run_backtest` call (`market_breadth.py:42`), leaving `_SCOPED_CACHE.get() is None`.
4. **No cross-fold feedback:** Fold $k$'s training selection sees **only** fold $k$'s training runs — never fold $k-1$'s test metrics or trades.
5. **Warm-up vs execution boundary:** During fold $k$'s test run (`[test_start, test_end]`), `_load_feed(sym, fold[k].test_end)` loads historical bars `<= test_end`. Bars with `date < test_start` (including bars that happened to fall inside `train` or the `embargo` gap) are accessed **solely** as causal price history inside `feed.window(session, 520)`, `benchmark_slice(-1, as_of_date=session)`, and `compute_universe_breadth(as_of_date=session)` for sessions `session >= test_start`. No fill, exit, mark, equity point, or entry signal is generated on any date `< test_start` or `> test_end`.

### 5.2 Stitched out-of-sample (`oos_summary`) aggregation

Across $K$ disjoint, chronological test runs $R^{(0)}_{\text{test}}, \dots, R^{(K-1)}_{\text{test}}$:
- **`oos_trades`:** Exact chronological concatenation `R[0].trades + ... + R[K-1].trades`. Every trade satisfies `fold[k].test_start <= entry_date <= exit_date <= fold[k].test_end` for some $k$. **Zero** training trades are included.
- **`oos_equity_curve` (multiplicative test-only chaining, zero train sessions):**
  - Let $C_0 = \text{base\_config.initial\_capital}$, anchor $A_0 = C_0$, and running peak $P = C_0$.
  - For fold $k = 0 \dots K-1$ with test curve $p_0, \dots, p_{m_k - 1}$:
    - Scale factor $f_k = A_k / C_0$.
    - For each point $p_t$: `eq = money(p_t.equity * f_k)`, `cash = money(p_t.cash * f_k)`, `inv = eq - cash`, `P = max(P, eq)`, `dd = (P - eq) / P if P > 0 else D(0)`. Append `EquityPoint(date=p_t.date, equity=eq, cash=cash, invested=inv, drawdown=dd)`.
    - Set next anchor $A_{k+1} = \text{eq}_{\text{last}}$ (end-of-fold stitched equity).
  - Properties: within every test fold, daily percentage returns `(eq[t] - eq[t-1]) / eq[t-1]` equal the standalone fold's daily returns up to `0.01` currency rounding; at the boundary between fold $k-1$'s last session (`A_k`) and fold $k$'s first session (`p_0.equity == C_0` because entries fill at `T+1` open, so session 0 of any fresh run has 0 fills and `equity == C_0` → `eq == A_k`), the inter-fold boundary return is **exact `0.0%`**, injecting no phantom jump and zero training sessions!
- **`oos_metrics`:** Computed by calling `compute_metrics(oos_equity_curve, oos_trades, C_0, benchmark_return=None, stats=summed_test_stats)`.
- **Explicit stitching caveats reported in `oos_summary.warnings`:**
  1. **End-of-fold open positions (`B-15`, until Phase 3):** If any test fold ends with `invested > 0`, its unrealized gain/loss at `test_end` is reflected in `oos_equity_curve` and `oos_metrics.total_return`, while unclosed positions are absent from `oos_trades` (`win_rate` / `profit_factor`). `oos_summary` records `unclosed_end_positions_folds` and `unclosed_end_invested_total` explicitly.
  2. **Disjoint-fold CAGR span (`B-18`, until Phase 4):** When `embargo_sessions > 0` or `step_sessions > test_sessions` leaves calendar gaps between test folds, `compute_metrics`'s `(curve[-1].date - curve[0].date).days` spans inactive gap days while `total_test_sessions` counts only active OOS sessions; `oos_summary` reports both `total_test_sessions` and a short-window/gapped-span note alongside `oos_metrics`.

---

## 6. Leak Prevention Analysis

### 6.1 Eight-channel leakage audit

| Channel | Code path | Existing point-in-time protection | Remaining gap / edge case | Phase 2 mitigation & labeling |
|---|---|---|---|---|
| **1. OHLCV prices** | `simulator._load_feed` → `repository.history_upto(sym, end=config.end_date)` | `history_upto` filters `date <= config.end_date` in both DB (`fetch_candles(..., end=end)`) and memory (`out["date"].dt.date <= end`). `_queue_entry` sees `None` after `end_date`. | None within a segment once `end_date` is set to `train_end` or `test_end`. | Each `train` run sets `end_date = fold.train_end`; `test` sets `end_date = fold.test_end`. Proven by price-mutation test (§6.2). |
| **2. Technical indicators** | `simulator` (`feed.window(session, 520)`) → `evaluator.build_context` → `indicators.add_indicators` | Causal rolling/EWM transforms (`ema20/50`, `sma50/200`, `rsi14`, `adx14`, `atr14`, `high_52w`) on bars `<= session`. | `evaluator.build_context` (`evaluator.py:34`) calls `aligned_relative_returns(df.iloc[:idx+1], as_of_index=-1)` without explicit `as_of_date` (`B-26`). Safe today because inner `pd.merge(..., on="date")` caps dates at `df.iloc[idx].date`. | Keep `B-26` noted; covered end-to-end by §6.2 test-window mutation test on real signals. |
| **3. Market regime** | `signals.generator` → `regime.classifier.classify_market(as_of_date=eval_date)` | `benchmark_slice(-1, as_of_date=eval_date)` slices `<= eval_date` *before* `benchmark_features(df)` and `hist_vol_20.quantile(...)` (`classifier.py:20, 34, 46`). | None for `<= 5000` bars (see Channel 5). | Verified by `test_regime_point_in_time.py` and §6.2 walk-forward mutation test. |
| **4. Market breadth & F-4 cache** | `classifier` → `market_breadth.compute_universe_breadth(as_of_date=as_of)` | Uses `get_history_window(sym, end=as_of_date, lookback_bars=520)` + `_slice_on_or_before`, benchmarks excluded (`F-2`). `breadth_cache_scope` is run-scoped (`F-4`) and keyed by `(as_of_date, equities, bar_fingerprints)`. | Appending/editing test bars changes `bar_fingerprints`, causing a conservative recompute that returns the **identical** as-of breadth for `as_of_date <= train_end`. | Fresh `breadth_cache_scope()` per segment run; zero cross-run cache state. |
| **5. Benchmark proxy & `_PROXY_CACHE`** | `regime.benchmark.ensure_benchmark_history` → `benchmark_slice` | `pct_change()` and `cumprod()` are causal on `date <= as_of_date`; `_PROXY_CACHE` keys on `bar_fingerprints` (`Phase 1.1`). | **(a) Survivor constituents (`B-14`):** proxy averages returns over current `list_universe_symbols()`. **(b) `limit=5000` tail:** `get_history_dataframe(sym, limit=5000)` (`benchmark.py:65`) would shift the `cumprod` base if a symbol exceeded 5,000 bars (~20 years) and new bars were appended. | Disclose survivor-proxy limitation (`B-14`, blocked on M15) in walk-forward warnings; document `5000`-bar horizon note. |
| **6. Shariah screening** | `backtesting.compliance.check_entry` → `snapshot_as_of` | Checks `s.screening_date <= session` on immutable snapshots (`shariah_snapshots`). | **`B-10` (two parts):** (a) `screening_date` is screen run date, not financial filing `published_at` (blocked on M17). (b) Fallback `sh_store.get_latest_eligibility(symbol)` (`compliance.py:19–20`) reads the single latest mutable record: if a later screening (`verified_at > train_end`) overwrites it without an earlier snapshot, `verified_at <= session` becomes `False` retroactively. Held positions are also not re-screened after entry. | Emit mandatory `B-10` warning on `STRICT` walk-forward runs (`"STRICT Shariah checks screening_date/verified_at <= session, not financial statement publication dates (B-10 / M17)"`); test `STRICT` snapshot behavior across fold boundaries. |
| **7. Universe membership** | `backtesting.universe.universe_for_backtest` | Partitions out registered benchmarks (`F-3`); flags per-segment missing/partial symbol coverage (`B-09`/`B-30`). | **`B-09` survivorship bias:** Default universe is current `list_all_symbols()` across all historical folds (blocked on M15 point-in-time `UniverseProvider`). | Propagate `survivorship_warning` to top-level `WalkForwardV2Response.warnings` and `disclosures`. |
| **8. Portfolio & execution state** | `SimBook` (`backtesting/portfolio.py`) vs live `BookState` (`portfolio/store.py`) & `execution_state` | `SimBook` is purely in-memory and discarded per `run_backtest`. | None if each segment invokes `run_backtest` separately. | Assert in tests that `BookState` and `execution_state` before and after walk-forward are identical, and no `SimPosition` / `pending` / `stop_pending` crosses a fold or train→test boundary. |

### 6.2 Proof test design: test-window price mutation cannot affect training or selected parameters

`tests/test_walk_forward_m14.py::test_mutating_test_window_prices_cannot_change_train_metrics_or_selected_params` will prove strict causal separation on **both** a fast multi-candidate grid and the real unified signal pipeline:

1. Construct a deterministic market (`3` equities × `220` business days) and a fold with `train = [bar_date(65), bar_date(135)]`, `embargo = 5 sessions`, `test = [bar_date(141), bar_date(205)]`, and a 4-candidate grid (`hold_days=[5, 12] × min_signal_score=[75, 85]`) where candidates produce distinct trade counts and Sharpe ratios on `train`.
2. Execute `run_walk_forward_v2` on the baseline market → capture for Fold 1:
   - every candidate's `train_metrics`, `train_trades`, and `train_equity_sha256`,
   - `selected_params`, `selected_config_hash`, and `selection_status`,
   - `test_result.metrics` and `test_result.trades`.
3. **Corrupt all post-train bars (`date > fold.train_end`, covering both the embargo gap and the test window)** across all equities — e.g., multiply `open/high/low/close` by `5.0` on half the symbols and `0.2` on the rest (dramatically altering `test_result` returns, regime, breadth, and benchmark proxy values on `date > train_end`).
4. Re-execute `run_walk_forward_v2` with the exact same request on the corrupted market.
5. **Assertions:**
   - Every candidate's `train_metrics`, `train_trades`, and `train_equity_sha256` are **100% identical** between run 1 and run 2.
   - `selected_params`, `selected_config_hash`, and `selection_status` are **100% identical** between run 1 and run 2.
   - `test_result` **does** differ between run 1 and run 2 (proving the mutation was active and actually exercised the test window).

---

## 7. Reporting Contract

Every Phase 2 walk-forward response strictly separates in-sample (`train`) diagnostics from out-of-sample (`test`) results:

1. **Top-level metadata & integrity hashes:**
   - `schema_version`: `"2.0"`
   - `status`: `"COMPLETED"` (or HTTP error on validation failure)
   - `base_config`: serialized `BacktestConfig` (with `cost_scenario`, `shariah_mode`, `horizon`, `initial_capital` visible)
   - `base_config_hash`: SHA-256 of canonical `base_config` (dates excluded)
   - `selection_spec`: mode (`"fixed"` | `"grid_search"`), objective, `min_train_trades`, `candidates_per_fold`
   - `fold_generation`: mode (`"explicit"` | `"rolling"` | `"expanding"`), `total_folds`, `min_embargo_sessions`, `dropped_trailing_sessions`
   - `evidence_grade`: conservative rollup across all segment runs (`"demo"` if any segment is `"demo"`, else `"imported_unverified"` — **never** `"research_grade"`)
   - `data_provenance`: aggregated `DataProvenance` across scanned symbols
   - `disclosures`: structured flags (`survivorship_biased: true`, `shariah_filing_dates_unverified: bool`, `cost_scenario: str`, `end_of_segment_positions_unliquidated: bool`, `multiple_testing_candidates_per_fold: int`)
   - `warnings`: deduplicated list including mandatory survivorship (`B-09`), proxy (`B-14`), Shariah `STRICT` filing-date (`B-10`), cost-free `ZERO` (`B-05` disclosure when `cost_scenario == ZERO`), and multiple-testing (`B-23`) notices
   - `notice`: `"Independent train/test walk-forward (v2): parameters selected on train windows only; oos_summary reflects stitched disjoint test windows only. Not a forecast."`
2. **Per-fold object (`folds[k]`):**
   - `fold_index`, `label`
   - `boundaries`: `{train_start, train_end, test_start, test_end, gap_calendar_days, embargo_sessions_actual, train_sessions, test_sessions, min_warmup_bars_before_train}`
   - `candidates`: list of `{candidate_index, params, config_hash, eligible, objective_value, train_metrics}` (plus `train_dispersion`: min/median/max of `total_return` and `sharpe` across candidates when `candidates_per_fold > 1`)
   - `selection`: `{selected_candidate_index, selected_params, selected_config_hash, objective, objective_value, selection_status}` (`"selected_on_train"` | `"fixed_config"` | `"fallback_insufficient_train_trades"`)
   - `train_result`: `{metrics, trades, equity_points, equity_sha256, open_positions_at_end, open_invested_at_end, warnings}` for the **selected** candidate on `[train_start, train_end]`
   - `test_result`: `{metrics, trades, equity_points, equity_sha256, open_positions_at_end, open_invested_at_end, warnings}` for the **frozen** selected config on `[test_start, test_end]` (optionally `include_equity_curves: bool = False` query/body flag to include full `equity_curve` arrays when requested while keeping default payloads compact)
3. **Top-level `oos_summary` (the ONLY block permitted to use the label "out-of-sample"):**
   - `fold_count`: $K$
   - `total_test_sessions`: sum of `test_sessions` across folds
   - `positive_test_folds`: count of folds with `test_result.metrics.total_return > 0`
   - `zero_trade_test_folds`: count of folds with `test_result.metrics.total_trades == 0`
   - `fold_test_returns`: list of per-fold `total_return` strings (plus `mean` and `std` when $K \ge 2$)
   - `unclosed_end_positions_folds` & `unclosed_end_invested_total` (`B-15` transparency)
   - `oos_metrics`: `BacktestMetrics` computed **strictly** from `oos_equity_curve` and `oos_trades`
   - `oos_trades`: chronological list of test-window `CompletedTrade`s only
   - `oos_equity_curve`: stitched test-only `EquityPoint` list (and `oos_equity_sha256`)

**Hard prohibition:** Nowhere in `WalkForwardV2Response` is a simulation run from `train_start` to `test_end`, and no metric combines `train` and `test` equity curves or trades.

---

## 8. Versioned API and Compatibility Proposal

### 8.1 Endpoints

| Endpoint | Method | Status in Phase 2 | Purpose |
|---|---|---|---|
| `/api/v1/backtests/{backtest_id}/walk-forward` | `POST` | **Preserved unchanged** | Legacy M7 behavior (`walk_forward.py::walk_forward`) kept untouched so existing scripts/clients do not break silently. |
| `/api/v2/backtests/{backtest_id}/walk-forward` | `POST` | **New (Phase 2)** | Loads stored `BacktestRun` (`backtest_id`), uses its `run.config` as `base_config`, and runs `run_walk_forward_v2`. |
| `/api/v2/backtests/walk-forward` | `POST` | **New (Phase 2)** | Stateless evaluation accepting `base_config: BacktestConfig` inline alongside folds and selection settings (avoids creating throwaway single-window rows in `backtest_runs`). |

### 8.2 Request shapes

```json
{
  "folds": [
    {
      "label": "f1",
      "train_start": "2026-04-01",
      "train_end": "2026-07-31",
      "test_start": "2026-08-10",
      "test_end": "2026-09-18"
    }
  ],
  "auto_folds": null,
  "min_embargo_sessions": 0,
  "selection": {
    "mode": "grid_search",
    "objective": "sharpe",
    "min_train_trades": 3,
    "grid": {
      "hold_days": [7, 10, 15],
      "min_signal_score": [75, 85],
      "max_positions": null
    }
  },
  "include_segment_curves": false
}
```

*(For `POST /api/v2/backtests/walk-forward`, the same body additionally requires `"base_config": { ...BacktestConfig... }`.)*

### 8.3 Error & validation behavior

| Failure condition | HTTP status | Response detail |
|---|---|---|
| `backtest_id` does not exist (`/{backtest_id}/walk-forward`) | `404 Not Found` | `{"detail": "Backtest not found"}` |
| Malformed JSON, invalid types, out-of-range grid integers (`hold_days < 4`, `min_signal_score` outside `0..100`, `max_positions < 1`), or both/neither of `folds` and `auto_folds` set | `422 Unprocessable Entity` | Standard Pydantic field-validation error detail |
| Domain validation failure: inverted dates (`train_start >= train_end`, `train_end >= test_start`, `test_start >= test_end`), overlapping test folds (`fold[k].test_end >= fold[k+1].test_start`), `embargo_sessions < min_embargo_sessions`, `< 2` sessions in a segment, `< 60` warm-up bars, 0 generated folds, `candidates > 12`, or total segment runs `> 24` | `400 Bad Request` | Clear, deterministic message naming the offending fold/parameter and exact counts |

---

## 9. Testing Plan and Acceptance Criteria

### 9.1 Planned test suite — `backend/tests/test_walk_forward_m14.py`

Most structural/leakage tests will use a deterministic seeded 3-symbol × 220-bar fixture and controllable regime/score stubs so the suite completes in a few seconds, paired with compact end-to-end real-signal tests:

1. **Fold validation unit tests:**
   - Rejects `train_start >= train_end`, `train_end >= test_start`, and `test_start >= test_end`.
   - Rejects overlapping or non-chronological test windows across folds (`fold[0].test_end >= fold[1].test_start`), while permitting overlapping `train` windows (both rolling and expanding).
   - Enforces `min_embargo_sessions > 0` when `test_start` is too close to `train_end`.
   - Rejects insufficient warm-up (`< 60` bars before `fold[0].train_start`) and `< 2` trading sessions in `train` or `test`.
   - Rejects empty folds, both `folds` and `auto_folds` supplied, `candidates > MAX_CANDIDATES_PER_FOLD`, and segment budget `> MAX_SEGMENT_RUNS`.
2. **Auto-fold generator unit tests:**
   - `mode="rolling"` produces fixed `train_sessions` and disjoint `test_sessions` separated by `embargo_sessions`, dropping trailing partial sessions and reporting `dropped_trailing_sessions`.
   - `mode="expanding"` anchors `train_start` at `session[warmup_sessions]` while advancing `train_end` and `test_start` without overlap.
   - Raises clear `ValueError` when total sessions cannot form 1 full fold.
   - Emits partial-warm-up warning when `60 <= warmup_bars < 252`.
3. **Training-only selection, tie-breaking & fallback tests:**
   - Selects the candidate maximizing `objective` (`sharpe`, `total_return`, `return_over_max_drawdown`) on `train` even when another candidate would have performed better on `test` (anti-snooping test!).
   - Enforces `min_train_trades`: disqualifies a high-Sharpe 1-trade candidate in favor of a qualifying candidate.
   - Zero-trade / `STRICT` Shariah fallback: when every candidate has `< min_train_trades`, deterministically selects `base_config` (`candidate_index = 0`), sets `selection_status = "fallback_insufficient_train_trades"`, and emits warning.
   - Exact tie-breaking determinism and canonical `selected_config_hash` stability across key orderings.
   - Emits warning when `min_signal_score` grid contains multiple values `<= 75` on `unified` strategy.
4. **Segment isolation tests (no state carryover):**
   - A position opened in `train` that is still held on `train_end` (including one with `stop_pending = True` ownership-delayed stop, and a signal on `train_end - 1` or `train_end`) **never** appears in `test` positions, `test` exits, `test.trades`, or `oos_trades`.
   - `test` starts with exact `cash == initial_capital` and `open_count == 0` on every fold, regardless of `train` profits, losses, or open positions.
   - Fold 2's training selection is unaffected if Fold 1's test outcome is altered.
5. **Leakage proof tests (§6.2):**
   - Mutating all OHLCV bars strictly after `fold.train_end` (both embargo and test dates) leaves every candidate's `train` metrics/trades/equity `sha256`, `selected_params`, and `selected_config_hash` bit-identical, including on a real unified-signal run (exercising indicators, `classify_market`, `compute_universe_breadth` + F-4 cache, and `ensure_benchmark_history` + `_PROXY_CACHE`).
6. **Stitched OOS reporting tests:**
   - `oos_trades` equals exact concatenation of per-fold `test_result.trades` and contains **zero** trades with `entry_date < fold[k].test_start` or `exit_date > fold[k].test_end`.
   - `oos_equity_curve` contains test-window dates only (no train or embargo dates), chains fold returns multiplicatively from `initial_capital`, and matches standalone single-fold `test_result.metrics` when $K = 1$.
   - Provenance, `EvidenceGrade.DEMO`, survivorship (`B-09`), proxy (`B-14`), `STRICT` filing-date (`B-10`), `ZERO` cost (`B-05`), and end-of-fold open-position (`B-15`) disclosures are present.
7. **Reproducibility & live-portfolio isolation tests:**
   - Two consecutive `run_walk_forward_v2` calls (and reversed fold-independent single-fold calls) produce identical JSON payloads and `oos_equity_sha256`.
   - Live `BookState` (`portfolio/store.py`) and `execution_state` (`execution/store.py`) remain untouched before and after walk-forward execution; legacy trade write endpoints remain `403`.
8. **API & backward-compatibility tests (`TestClient`):**
   - `POST /api/v1/backtests/{id}/walk-forward` still returns its exact legacy response shape (`{"folds": [...], "notice": "Out-of-sample segments embedded per fold end_date"}`).
   - `POST /api/v2/backtests/{id}/walk-forward` and `POST /api/v2/backtests/walk-forward` return `200` on valid requests, `404` on unknown `backtest_id`, `422` on schema violations, and `400` on overlapping folds / insufficient history / budget overflow.

### 9.2 Exact Phase 2 acceptance criteria

Phase 2 will be complete **only** when all of the following are verified:
1. All new tests in `backend/tests/test_walk_forward_m14.py` pass.
2. Focused M14 + regime point-in-time tests (`test_walk_forward_m14.py`, `test_breadth_cache_m14.py`, `test_backtest_phase1_1_m14.py`, `test_backtest_phase1_m14.py`, `test_regime_point_in_time.py`) pass with 0 failures.
3. Full non-Postgres backend suite (`pytest -q -m "not postgres"`) passes with 0 failures (and `@pytest.mark.postgres` status is explicitly reported).
4. `backend/tests/baselines/m14_post_phase1_1.json` and `backend/tests/baselines/m14_ablation_first4.json` have **zero diff**, and running `freeze_m14_baseline.py --out /tmp/m14_post_phase2.json` followed by `--compare tests/baselines/m14_post_phase1_1.json /tmp/m14_post_phase2.json` prints `scenarios_sha256 equal: True` with no differences in Scenarios A, B, or C.
5. `git diff --check` is clean and no `.env` or credentials are staged.
6. `docs/PROJECT_HANDOFF.md` (and `docs/m14_backtesting_audit.md` status line for Phase 2 / `B-17`, if requested at completion) reflects verified test counts and commit state.

---

## 10. Risks, Dependencies, and Phased Implementation Sequence

### 10.1 Key risks & dependencies

| Risk / dependency | Impact | Mitigation in Phase 2 |
|---|---|---|
| **Synchronous HTTP runtime (`B-24`)** | Even with the F-4 breadth cache, one 65-session 8-symbol demo run takes ~34 s; an unbounded grid (e.g. 5 folds × 20 candidates = 105 runs) would block a worker for ~1 hour. | Enforce `MAX_CANDIDATES_PER_FOLD = 12` and `MAX_SEGMENT_RUNS = 24` in v2 validation; keep Phase 5 (`B-24` per-run history/indicator precomputation) as the prerequisite for larger grids. |
| **Unliquidated end-of-segment positions (`B-15`)** | Positions open on `train_end` or `test_end` affect segment equity curves without generating a `CompletedTrade`. | Never carry positions into the next segment; report `open_positions_at_end` and `open_invested_at_end` per segment and in `oos_summary` until Phase 3 implements `B-15` end-of-window liquidation. |
| **Pre-Phase-3 cost accounting (`B-04`, `B-05`)** | Default `cost_scenario` remains `ZERO`, and `CompletedTrade.costs` / `net_pnl` still omit buy-side fees until Phase 3 (`B-04`) — though `SimBook` equity *does* deduct buy fees (`simulator.py:287`). | Keep `ZERO` default untouched per Phase 2 constraints; prefer equity-curve objectives (`sharpe`, `total_return`, `return_over_max_drawdown`) over trade-sum `profit_factor` for candidate selection; surface `cost_scenario` prominently in `disclosures` and `warnings`. |
| **No sub-strategy indicator tuning yet (`B-22`)** | `HorizonConfig` thresholds cannot be varied until Phase 5 adds non-mutating parameter overlays. | Restrict Phase 2 grid to real `BacktestConfig` knobs (`hold_days`, `min_signal_score >= 75`, optional `max_positions`) and document `B-22` as the prerequisite for indicator-level tuning. |
| **Data-layer survivorship & Shariah filing dates (`B-09`, `B-10`, `B-14`)** | Walk-forward splitting cannot cure survivorship in `list_all_symbols()` or missing `published_at` dates in Shariah financials. | Cap `evidence_grade` below research-grade (`DEMO` / `IMPORTED_UNVERIFIED`) and attach explicit `B-09`/`B-10`/`B-14` warnings to every v2 response until M15–M17 land. |

### 10.2 Phased implementation sequence (after user approval)

1. **Step 2.1 — Schemas (`backend/app/backtesting/walk_forward_schemas.py`):** Define `WalkForwardFoldInput`, `WalkForwardAutoFoldSpec`, `WalkForwardGridSpec`, `WalkForwardSelectionSpec`, `WalkForwardV2Request`, `WalkForwardStatelessV2Request`, and `WalkForwardV2Response` with field-level bounds and validators.
2. **Step 2.2 — Core engine (`backend/app/backtesting/walk_forward_v2.py`):** Implement session-calendar discovery, auto-fold slicing (`rolling` & `expanding`), fold/warm-up/embargo/non-overlap validation, candidate grid expansion + `base_config` anchor, train-only deterministic selector + `selected_config_hash`, isolated `test` execution, and multiplicative test-only `oos_summary` stitching.
3. **Step 2.3 — Versioned API (`backend/app/api/v2/backtests.py`, `router.py`, `app/main.py`):** Wire `POST /api/v2/backtests/{backtest_id}/walk-forward` and `POST /api/v2/backtests/walk-forward` with `400`/`404`/`422` handling, leaving `/api/v1/backtests/{backtest_id}/walk-forward` untouched.
4. **Step 2.4 — Regression & leakage test suite (`backend/tests/test_walk_forward_m14.py`):** Implement all 8 test groups from §9.1.
5. **Step 2.5 — Verification & handoff update:** User runs targeted tests, full non-Postgres suite, and `freeze_m14_baseline.py --compare`; update `docs/PROJECT_HANDOFF.md` with verified results before committing.

---

## 11. Software Validation on Demo Data vs Genuine Strategy Validation on Real Historical Data

This distinction is mandatory when interpreting any Phase 2 walk-forward output:

| Dimension | What Phase 2 validates on current demo data (`EvidenceGrade.DEMO`) | What is required for genuine strategy validation on real NSE data |
|---|---|---|
| **Price series** | `8` synthetic symbols × `520` seeded random-walk business days (`app/data/sample_data.py`). Proves fold splitting, warm-up indexing, and non-leakage **software correctness** only. | Multi-year historical NSE OHLCV (`M15`) with corporate-action-adjusted signal series and raw execution prices (`B-29`, `M16`) plus authoritative NSE holiday calendar (`B-32`, `M16`). |
| **Statistical power** | After `60–252` warm-up bars, `520` bars yield only `2–4` short test folds (`30–60` sessions each) with single-digit trade counts per fold — statistically meaningless for judging alpha. | Hundreds of point-in-time equities across multiple market regimes (bull, bear, sideways, high-vol) spanning several years and sufficient OOS trade counts (`B-16`, Phase 4). |
| **Universe & benchmark** | Static 8-stock list (`survivorship_warning=True`) and equal-weight 8-stock proxy (`B-09`, `B-14`). | Point-in-time NSE constituent membership including delistings (`M15`) and historical index benchmark constituents (`M15`, Phase 4 `B-13`). |
| **Shariah compliance** | `RESEARCH_ONLY` skips Shariah screening; `STRICT` produces `0` trades on demo data without manually seeded snapshots, and checks `screening_date` rather than filing `published_at` (`B-10`). | Point-in-time financial statements carrying `financial_period_end` and `published_at <= session` (`M17`) plus periodic holding re-screening. |
| **Execution & costs** | `CostScenario.ZERO` default, incomplete `REALISTIC` fee schedule, missing buy-side cost in `CompletedTrade.net_pnl`, asymmetric close exits, and unliquidated end-of-fold holdings (`B-04..B-07`, `B-15`, `B-25`). | Verified Indian delivery cost schedule, symmetric exit fills, ADV liquidity caps, and end-of-segment liquidation policy (**M14 Phase 3**). |
| **Tunable space** | Simulator-level `hold_days`, `min_signal_score >= 75`, and optional `max_positions`. | Non-mutating `HorizonConfig` strategy parameter overlay (`B-22`) and multiple-testing dispersion reporting (**M14 Phase 5**). |

**Bottom line:** Passing Phase 2 on demo data proves that the walk-forward engine **enforces strict train/test separation, selects parameters without peeking at future bars, resets portfolio state per segment, and computes out-of-sample metrics exclusively from test windows**. It does **not** validate that any strategy in Halal Quant V1 has positive expected return in live markets.

---

## 12. Implementation Notes (as built, 2026-11-27)

**Files (all additive).** `backend/app/backtesting/walk_forward_schemas.py` (request/response models and the budget constants), `backend/app/backtesting/walk_forward_v2.py` (calendar, fold generation and validation, candidates, hashing, selection, execution, OOS stitching), `backend/app/api/v2/router.py` + `backend/app/api/v2/backtests.py`, a two-line mount in `backend/app/main.py`, and `backend/tests/test_walk_forward_m14.py` (49 tests). `backend/app/api/v2/` has no `__init__.py`, matching `api/v1` (namespace package). `walk_forward.py`, `schemas.py`, `simulator.py`, `api/v1/*`, baselines, and strategy defaults are untouched.

**Endpoints.** `POST /api/v2/backtests/{backtest_id}/walk-forward` (base config loaded from the stored run; 404 if unknown) and `POST /api/v2/backtests/walk-forward` (stateless, `base_config` inline). 422 = request shape, 400 = invalid folds / embargo / warm-up / coverage / candidate limit / run budget / non-completed segment. Results are returned and not persisted.

**Behaviour as built.**
- `plan_walk_forward` does all validation before any `run_backtest` call (including the run budget). `execute_plan` runs each fold: every deduplicated candidate on the training window, `evaluate_candidates` (training metrics only; its signature admits no test input), freeze and log the selected hash, then one test run on the test window.
- Run log events per fold: `train_run` (per candidate), `selection_frozen` (selected hash), `test_run`. An `on_event` hook lets tests prove ordering. The test configuration hash is asserted equal to the frozen hash.
- Segment guards: window assertion on every equity point and trade (fail closed), non-COMPLETED run fails closed, the engine refuses to start inside an active breadth scope, and refuses any run beyond `planned_runs`.
- Warm-up: at least 60 sessions before `train_start` are required (warning below 252). Warm-up bars are history for indicators only; no simulation occurs before the segment start.
- OOS: stitched from test segments only (`stitch_oos`); it is a rescaled chain of independently simulated folds, not one continuous simulation, and the response says so.

**Deviations / additions relative to sections 1-11.** `include_base_candidate` removed (base is always candidate 0). Auto folds validate against `WalkForwardAutoFoldSpec.warmup_sessions >= 60`. Schema caps: raw grid <= 64 combinations (422), at most 12 folds. Explicit fold labels must be unique. `hold_days` is applied through the simulator's existing calendar-day hold test; no change was made to that semantics (B-20 stays in Phase 4).

**Not done (out of scope):** Phase 5 parameter plumbing (HorizonConfig overlay), B-23 dispersion statistics, persistence of v2 results, frontend, M15-M17 point-in-time data.
