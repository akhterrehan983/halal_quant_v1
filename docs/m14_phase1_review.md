# M14 Phase 1 — Review Notes

Status: Phase 1 and the Phase 1.1 correction (section 7) are implemented. The clean full-universe baseline and the first-four-symbol ablation are recorded in section 8. F-4 breadth profiling and a run-scoped breadth cache are recorded in section 9 (implemented in the working tree and verified on 2026-11-27, section 9.6; not yet committed). Phase 2 has **not** been started.
Data caveat: every number below comes from **synthetic demo data**. It is software-regression output, not performance evidence. Nothing here is a research-grade claim.

Sources: `backend/tests/baselines/m14_pre_phase1.json` (clean tree at commit `08c1680`), `backend/tests/baselines/m14_post_phase1.json` (superseded; dirty tree at `08c1680`), `backend/tests/baselines/m14_post_phase1_1.json` (clean tree at `498f8bc`, full 8-symbol universe) and `backend/tests/baselines/m14_ablation_first4.json` (same commit, first four symbols). All four were produced by `backend/scripts/freeze_m14_baseline.py`.

Test status: full backend suite **133 passed** after Phase 1.1. Earlier suite timings (121 passed in 541.6s; 117 passed in 258.7s) stay in section 7.4. Those timings do not resolve F-4. Frontend tests (5) and build passed in an earlier round.

---

## 1. Scope disclosure: work pulled forward from later phases

The audit (`docs/m14_backtesting_audit.md`) scheduled these items later than Phase 1:

| Item | Audit schedule | What Phase 1 now does |
|---|---|---|
| B-12 four-symbol scan cap | Phase 3 | Cap removed; the full eligible universe is scanned every session |
| B-14 benchmark in the tradable universe | Phase 4 (exclude benchmark from tradable universe) | Registered benchmarks (initially `NIFTY500_PROXY`) are excluded from scanning. Phase 1 used a hardcoded one-symbol set; Phase 1.1 replaced it with an explicit registry (section 7) |

Why they were done together: decision 5 (approved) removes the cap. Once every universe symbol is scanned, the benchmark proxy would become tradable unless excluded, so the exclusion was pulled forward with it.

What was **not** done from B-14: the benchmark is still an equal-weight survivor proxy, benchmark-relative metrics are absent (B-13, Phase 4), and survivorship bias is still only disclosed, not solved (M15).

This changes the baseline materially (see section 3), so it should be read as a Phase 1 effect even though it was not on the original Phase 1 list.

## 2. Ownership safeguard and stop-breach reporting

Behaviour (unchanged from the Phase 1 implementation): when a stop is breached while the sale is not yet authorised, nothing is sold. The breach is recorded, and the position exits at the **first authorised open**.

Reporting added in this review round (no change to when or at what price anything exits):

| Required item | Where it is reported |
|---|---|
| Stop-breach date | `CompletedTrade.stop_breach_date`; first session whose low traded at or through the stop while unauthorised |
| Stop price | `CompletedTrade.stop_price` (set on every trade) |
| Delayed exit date | `CompletedTrade.delayed_exit_date` (only when the sale was held back by ownership authorisation) |
| Actual fill | `CompletedTrade.exit_price` (the first authorised open); repeated as `actual_fill` in the run report |
| Loss beyond stop | `CompletedTrade.loss_beyond_stop` = `max(0, stop_price - fill) * quantity`, before costs |

Run level: `run.validation["ownership_delayed_stops"]` holds `count`, `total_loss_beyond_stop`, and one event per delayed stop. A warning is added to `run.warnings` whenever `count > 0`.

Definition notes:
- `loss_beyond_stop` is never negative. If the price recovers above the stop by the authorised open, it is `0`; a recovery is not reported as a gain.
- Ordinary `stop` exits (not ownership-delayed) also carry `stop_price`, `stop_breach_date` (= exit date) and `loss_beyond_stop` (gap slippage past the stop). They are not counted in `ownership_delayed_stops` and have no `delayed_exit_date`.
- Target and time exits carry only `stop_price`.
- Legacy stored runs load with these fields as `None`.

Existing baseline events: the post baseline contains two ownership-delayed exits (RELIANCE entered 2026-10-15, exit 2026-10-20 at 133.5484; COALINDIA entered 2026-10-27, exit 2026-10-30 at 262.3408). The superseded `m14_post_phase1.json` predates the reporting fields. The clean baseline `m14_post_phase1_1.json` stores `stop_price`, `stop_breach_date`, `delayed_exit_date` and `loss_beyond_stop` on each trade.

## 3. Baseline diff explanation (A: zero cost, B: realistic cost, C: STRICT)

Headline changes: A trades 8 to 22, A total return 0.44% to 1.29%; B total return 0.34% to 1.04% and costs 78.29 to 216.78; C trades 0 to 0 and Shariah rejections 47 to 132. The higher returns are **not** evidence of improvement. They come from changed mechanics on synthetic data.

Rule applied below: **Verified** means shown by the baseline files, the code, or both. **Hypothesis** means plausible but not isolated; no causality is claimed without an ablation.

### B-12 full-universe scan (and benchmark exclusion)
- Verified: pre-Phase 1 code scanned `syms[:4]`. The demo universe order is TCS, INFY, RELIANCE, HDFCBANK, SUNPHARMA, TATAMOTORS, BEL, COALINDIA. Pre trades are only HDFCBANK (4) and RELIANCE (4), both within the first four.
- Verified: 14 of the 22 post trades are in TATAMOTORS (5), COALINDIA (8) and SUNPHARMA (1), symbols the capped scan could not reach. TCS, INFY and BEL have no trades in either run.
- Verified: the earliest divergence is COALINDIA entered 2026-08-04, one day before the first common trade.
- The 8-to-22 change above compares old code (four-symbol cap) with new code (full scan). It mixes B-12 with the other Phase 1 mechanics. The universe-size comparison on one commit is in section 8: 9 trades on the first four symbols, 22 on all eight. That is the B-12 ablation. Later trades stay path dependent (max 3 positions, shared cash).
- Hypothesis: C's Shariah rejections rose (47 to 132) because more symbols' BUY signals are now evaluated. STRICT still produces 0 trades, and `check_entry` was not changed.

### B-02 stop and target enforcement
- Verified: pre exits are 8 of 8 `time_exit_authorized`. Post exits are 13 time, 5 target, 2 stop, 2 ownership-delayed stop. So 9 of 22 exits come from logic that did not exist before.
- Verified (cleanest case): HDFCBANK entered 2026-08-19 with identical quantity and entry price (48 at 203.70) in both runs. Pre exits 2026-08-31 at 200.3957 (time exit); post exits 2026-08-27 at 194.5949 (stop). Same entry, different exit, reason `stop`. The stop produced a worse result here than waiting; this shows a stop is a risk rule, not an improvement claim.
- Verified: `ownership_blocked_exits` 0 to 4 (counts sessions where an exit or a stop was held back by authorisation).
- Hypothesis: other changed HDFCBANK and RELIANCE trades are partly B-02 and partly path effects.

### B-03 signal-time sizing, fill-time validation
- Verified: `fill_rejections` is 0 in all three post scenarios, so the fill-time rejection and quantity-reduction path was **not exercised** by the baseline. It is covered only by unit tests.
- Observed, not isolated: RELIANCE 2026-09-02 changed quantity 82 to 83 and RELIANCE 2026-09-25 changed 74 to 76 with identical entry prices. Candidates are the sizing basis (assumed signal close instead of next open) and path-dependent equity from different earlier trades. Both are plausible; neither is verified.

### B-01 as-of data and 520-bar windows
- Verified: demo histories have exactly 520 bars (`make_history(periods=520)`) and the baseline window starts about 80 bars before the last bar. The old "latest 520 bars" tail therefore truncated **nothing** in this baseline. B-01 truncation cannot explain any baseline difference.
- Hypothesis (unverified): signal and breadth inputs are now cut at the session instead of using the full frame with `as_of_index`. This matches the old results only if every indicator is causal. An equivalence check on the same bars would verify it.

### B-08 stale marks
- Verified: `stale_marks = 0` and `max_stale_days = 0` in all three scenarios. Every held position had a bar every session, so B-08 had **no effect** on the baseline. It is covered only by unit tests.

### B-09 coverage filter and excluded symbols
- Verified: all 8 symbols have coverage status `full` (first bar 2026-08-03, last bar 2026-10-30), `excluded = []`, start and end gaps are 0. The old coverage filter would not have dropped anything, so B-09 had **no effect** on the baseline. Phase 1 only surfaces exclusions; it does not fix the listings/delistings issue (M15).

### B-28 provenance
- Verified: post runs carry `evidence_grade = demo` and `data_provenance.kind = synthetic`; the pre files have no such keys.
- Verified by code reading: provenance is computed from the loaded feeds after loading and is not read by trading logic, so it cannot change trades.

### Other observed effects (not mapped to the requested IDs)
- Verified: the equity point is now recorded after exits, and the session order is fills, exits, marks, signals. Equity curve points stay at 65, but the values differ. Not separable from the trade differences.
- Verified: costs. B's transaction costs rose because there are 22 trades instead of 8. The cost model was not changed.
- Verified: A and B (post) agree on 20 of 22 trades, and every entry and exit date, price and reason; the two differences are quantities off by one share (68 vs 67, 37 vs 36), consistent with costs lowering equity used for sizing.
- Verified: runtime per scenario rose from about 51, 51, 56 seconds to 64, 62, 112 seconds (8 symbols instead of 4).

### Ablation status

The four-versus-eight run in the plan below has been executed. Both files were frozen from commit `498f8bc` with a clean backend tree. The measured results and the B-12 verdict are in section 8. The full-universe file is named `m14_post_phase1_1.json` (the plan's `m14_post_phase1_clean.json` name was not used).

The pre-Phase 1 versus first-four comparison (old code against new code on the same four symbols) was not recorded. Differences on that pair would still combine B-01, B-02, B-03 and the session-order change. Separating B-02 from B-03 and B-01 would require temporary simulator toggles. That has not been done and is not proposed here.

Original plan, kept for the command shape:

```
cd backend
.venv/bin/python -m scripts.freeze_m14_baseline --out tests/baselines/m14_post_phase1_clean.json
.venv/bin/python -m scripts.freeze_m14_baseline --symbols TCS,INFY,RELIANCE,HDFCBANK --out tests/baselines/m14_ablation_first4.json
.venv/bin/python -m scripts.freeze_m14_baseline --compare tests/baselines/m14_pre_phase1.json tests/baselines/m14_ablation_first4.json
.venv/bin/python -m scripts.freeze_m14_baseline --compare tests/baselines/m14_ablation_first4.json tests/baselines/m14_post_phase1_clean.json
```

## 4. Universe and benchmark: confirmation and findings

Confirmed (baseline data and code):
1. The scanned set is the same 8 tradable symbols in all three scenarios; `NIFTY500_PROXY` is not in `scanned_symbols` and never traded.
2. In this baseline the proxy would not have been scanned before either (capped at the first four), so excluding it changes no baseline trade by itself.
3. Explicit `symbols` from the API are upper-cased, de-duplicated, and have the benchmark removed; unit tests cover the full-universe scan and the benchmark exclusion.
4. Shariah and ownership checks are unchanged and still run for every scanned candidate.

Findings. **F-1, F-2, F-3 and F-5 were resolved in the Phase 1.1 correction (section 7); F-4 remains open.** The text below is the finding as originally recorded:
- **F-1, process-state dependence.** `regime/benchmark.py` appends `NIFTY500_PROXY` to the module-level `sample_data.SYMBOLS` on first use. Scenario A (first run in the process) reports `benchmark_excluded: []`; B and C report `['NIFTY500_PROXY']`. Scanning is unaffected (excluded either way), and A and B trade identically apart from the two one-share differences. This predates Phase 1, but it is an unintended dependence on run order.
- **F-2, breadth includes the benchmark.** `compute_universe_breadth(as_of_date)` samples `list_universe_symbols()`, which includes the proxy once it exists, so the breadth sample is 8 or 9 symbols depending on run order. Verified against the committed code (`HEAD`): the old loader also iterated `list_universe_symbols()`, so Phase 1 neither introduced nor removed this. Fixing it changes signals, so it should be a deliberate later decision (suggested alongside B-14 in Phase 4 or in M15).
- **F-3, benchmark set is hardcoded.** `BENCHMARK_SYMBOLS` holds one symbol. In database mode any other index-like series would be scanned as tradable. There is no instrument-type field to rely on.
- **F-4, runtime scaling (hypothesis).** Breadth recomputation per signal is likely to scale with universe size squared. It has not been measured on a real universe. Demo runs take about 1 to 2 minutes with 8 symbols.
- **F-5, stale audit text.** The audit states the universe order is sorted (true only in database mode; demo order is the `SYMBOLS` list) and schedules B-12 and the B-14 exclusion in later phases. It should get a status note after the commit; it has not been edited.

## 5. Required fixes before Phase 2

- The review found no blocking defect. Its findings F-1, F-2, F-3 and F-5 were then fixed in Phase 1.1 (section 7).
- Still open: F-4, the runtime budget for a real universe (section 7.4). The redundant per-candidate breadth recomputation was profiled and removed by a run-scoped cache (section 9); the real-universe runtime budget is still unmeasured. The clean baseline and the first-four ablation are recorded in section 8. `m14_post_phase1.json` stays superseded.

## 6. Unchanged by the first review round (before Phase 1.1)

- Cost default: still `ZERO` in `BacktestConfig`. The REALISTIC default is deferred to Phase 3, after cost accounting and rates are verified.
- No walk-forward, metrics, Monte Carlo, API route, database schema, or frontend change.
- Only code touched in this round: `backtesting/schemas.py` (4 optional trade fields), `backtesting/portfolio.py` (1 field), `backtesting/simulator.py` (stop-breach reporting), `scripts/freeze_m14_baseline.py` (optional `--symbols`), and `tests/test_backtest_phase1_m14.py` (4 tests).

---

## 7. Phase 1.1 correction (F-1, F-2, F-3)

Narrow scope. Strategy rules, cost defaults (still `ZERO`), ownership safeguards and the Shariah checks were **not** changed. Phase 2 has not started.

### 7.1 What changed

| Finding | Root cause | Fix |
|---|---|---|
| F-1 run-order dependence | `regime/benchmark.py` wrote the proxy into `sample_data.HISTORIES` and appended `NIFTY500_PROXY` to `sample_data.SYMBOLS` the first time any run needed it. The universe list therefore differed between the first run in a process and later runs, and the proxy was built from whichever universe existed at that moment | The proxy build has **no side effects**. It never touches the stored symbol list or history store. It is built from the benchmark-free equity universe in sorted symbol order (a pure function of the stored histories) and cached privately by a content fingerprint of its inputs (the symbols and their stored bars, in both database and memory mode; see 7.1a), so changed data forces a rebuild and list order cannot matter. Callers get a copy |
| F-2 benchmark counted in breadth | Breadth sampled `list_universe_symbols()`, which included the proxy once it existed | Breadth (as-of and latest paths) never samples registered benchmarks. The as-of window logic is unchanged, so breadth remains point-in-time and causal |
| F-3 hardcoded benchmark set | `BENCHMARK_SYMBOLS` held one symbol | Explicit registry in `app/market_data/benchmarks.py`: built-in `NIFTY500_PROXY` plus extra symbols from the `BENCHMARK_SYMBOLS` setting (comma-separated). Result depends only on configuration |

How the registry is enforced:
- `repository.list_universe_symbols()` now returns the **equity universe only** (registered benchmarks removed). `list_all_symbols()` is the raw list, used only to report what was excluded. Every equity consumer inherits the exclusion: backtest scan, breadth, signal scans, valuation prices, stock and quality listings.
- `backtesting/universe.partition_universe()` splits any requested universe (explicit or implicit) into tradable equities and excluded benchmarks (case-insensitive, de-duplicated). The coverage report gains `benchmarks_registered`; `benchmark_excluded` lists registered benchmarks that were present in the request or the stored data.
- `execution/order_manager.validate_buy` adds a rejection ("Registered benchmark / index proxy is not a tradable equity") so a benchmark cannot be bought as an equity. It only adds a rejection; the Shariah and ownership checks are untouched.
- `RegimeConfig.benchmark_symbol` and `BacktestConfig.benchmark` now take their default from the registry constant instead of repeating the string.

Behaviour changes to be aware of (intended, but visible):
- A stored benchmark series is still readable by name (`get_history_dataframe("NIFTY500_PROXY")`), but it no longer appears in the equity universe listings. In demo mode the built proxy is no longer stored at all, so it is not readable through the repository by name; the regime code obtains it through `ensure_benchmark_history()`. No in-repo caller read it by name.
- `benchmark_excluded` is now `[]` in **every** scenario of the demo baseline (the proxy is never stored), instead of `[]` for the first run and `['NIFTY500_PROXY']` for later ones. `benchmarks_registered` (always `['NIFTY500_PROXY']` unless more are configured) is the stable record of what is protected.
- In database mode with no stored benchmark, each signal evaluation now makes one extra symbol-list query (the proxy cache check needs the universe). Not measured.

### 7.1a Follow-up fix: proxy cache fingerprint and settings binding

A review of the first Phase 1.1 implementation found a defect in its own proxy cache:

- **Stale proxy.** The cache key was `(symbol, bar count, last bar date)` in memory mode and the symbol set only in database mode. A corrected or restated bar with an unchanged symbol list (same count, same last date) returned the old proxy. The earlier "never stale" test passed only because it also changed the symbol list.
- **Import-time settings binding.** `regime/benchmark.py` imported `settings` directly and chose its branch from `settings.database_enabled`. The test fixture swaps settings in a fixed list of modules that did not include it, and `.env` sets a database URL, so a test could silently take the database branch.

Fix:
- `repository.bar_fingerprints(symbols)` returns a content fingerprint per symbol, in whichever storage mode the repository is using. Memory mode: bar count, first and last date, and a blake2b digest of the dates and OHLCV values. Database mode: one grouped aggregate query (`persistence.candle_fingerprints`) returning row count, first and last date, sums of open/high/low/close/volume, the sum of close x row id (so offsetting edits and closes swapped between dates are detected, which plain sums cannot do), and the latest `updated_at`. No candles are loaded.
- `regime/benchmark.py` no longer reads settings. The storage-mode decision lives only in `repository`, which the test fixture already controls. The cache key is the sorted `(symbol, fingerprint)` pairs.
- `market_data/benchmarks.py` reads `app.core.config.settings` at call time (no import-time binding), so the fixture's swap applies to it.

Known limit of the database fingerprint: a raw SQL edit that bypasses `updated_at` and only moves a middle bar's date, leaving every value and count unchanged, would not be detected. Edits made through the ORM or Core `update` bump `updated_at`.

### 7.2 Regression tests (`tests/test_backtest_phase1_1_m14.py`)

- Three scenarios (A zero cost, B realistic cost, C STRICT) run in two different orders, each from a freshly installed market. For every scenario the test asserts identical coverage and tradable symbols, breadth inputs (which symbols and dates breadth read), the benchmark slice and breadth seen by each signal evaluation, trades, metrics and the equity curve, and that the stored symbol list is never modified by running. The stub signal scores from the benchmark slice and breadth, so any order dependence in either would change scores, trades or metrics.
- The proxy build has no side effects and returns a copy.
- Symbol-order independence: reversed list order gives an identical proxy with a warm cache (a cache hit) and with a cold cache (a real rebuild from a reversed input list), and the fingerprint ignores list order and symbol case.
- **Changed bars, identical symbols (memory mode):** one middle close is edited while the symbol list, bar count, last date and last close stay the same. The test asserts those preconditions, then asserts the proxy rebuilds and differs, and that restoring the bar restores the original proxy exactly. An unchanged-data call is a cache hit.
- **Changed bars, identical symbols (database mode):** the same scenario against an in-memory SQLite database wired in as the repository's database, with the build count checked.
- Database fingerprint (`candle_fingerprints`): stable across order and case, omits unknown symbols, and changes for a middle-close edit, a volume-only edit, and two closes swapped between dates, each with `updated_at` held fixed so only the content signals the change. Other symbols' fingerprints do not move.
- Settings binding: swapping `app.core.config.settings` takes effect in the registry, and `regime.benchmark` owns no `settings` attribute.
- A new symbol added to the universe changes the proxy.
- Breadth excludes a stored benchmark series (as-of and latest paths) and ignores appended future bars.
- Registry defaults and configuration (case, whitespace, empty entries).
- A configured benchmark that would win any scan is never offered to the signal generator, never sampled by breadth, never traded, and is reported as excluded, including when named in an explicit symbol list.
- A BUY order for a registered benchmark is rejected.

### 7.3 Baseline impact (measured in section 8)

- `m14_post_phase1.json` was produced before Phase 1.1, on a dirty tree at `08c1680`. It is **superseded**. The Phase 1.1 reference is `m14_post_phase1_1.json`.
- The scenario metric blocks that were compared by hand match as strings between those two files: total trades, total return, Sharpe, max drawdown, profit factor, volatility, transaction costs, ownership-blocked exits and Shariah rejections, for A, B and C. Trade-by-trade and equity-curve identity was not re-checked for this note. Elapsed time differs (section 7.4), which is a runtime measurement, not a result change.
- The four-versus-eight ablation is in section 8. A pre-Phase 1 versus first-four comparison would still mix B-01, B-02, B-03, the session-order change and the F-2 breadth change. That comparison was not recorded.

### 7.4 Remaining runtime concern (F-4, still open)

- Verified (timings only): the full backend suite took 541.6 s for 121 tests (18:41 run) and 258.7 s for 117 tests (17:32 run). The 308.7 s run of 20 tests overlapped with a baseline freeze, so its timing is contaminated. The phase-1 test file alone took 2.4 s, because its signal generator is stubbed.
- Not established: the cause of the 541.6 s vs 258.7 s difference. The code changed between them was reporting only, so environment load is more likely. Needs a clean `--durations` measurement.
- Verified (from code): each real signal evaluation calls `classify_market`, which recomputes breadth over every equity symbol. A backtest session therefore does up to (scanned symbols × equity symbols) indicator recomputations, with no caching. Real backtests run this path. Stubbed tests do not.
- Verified (from the freeze output): one 8-symbol demo scenario took 62 to 112 s in the pre-Phase-1.1 run. The clean Phase 1.1 freeze (`m14_post_phase1_1.json`) recorded 76.7 s, 86.0 s and 159.9 s for scenarios A, B and C. The first-four ablation on the same commit recorded 58.3 s, 54.3 s and 74.7 s. Each figure is a single run. The spread across runs is large, so these timings do not establish a scaling law and do not resolve F-4. Nothing here was measured on a real universe. A runtime budget and general history/indicator caching belong to Phase 5 (B-24). The separately approved breadth cache is recorded in section 9.
- Phase 1.1 adds a per-signal cost when no stored benchmark exists: symbol-list filtering plus the input fingerprint. After the 7.1a fix the fingerprint covers bar content, so in memory mode it hashes every equity frame on each call, and in database mode it runs one grouped aggregate query (plus the symbol-list query) on each call. This is more work than the first Phase 1.1 version did. It is not measured. The approved breadth-caching follow-up is intended to share the same fingerprint query and reduce repeated work; it is not part of this change.

### 7.5 Files changed in Phase 1.1

`app/market_data/benchmarks.py` (new; call-time settings binding), `app/market_data/persistence.py` (`candle_fingerprints`), `app/core/config.py`, `app/market_data/repository.py` (`bar_fingerprints`), `app/regime/benchmark.py`, `app/regime/market_breadth.py`, `app/regime/config.py`, `app/backtesting/universe.py`, `app/backtesting/simulator.py`, `app/backtesting/schemas.py`, `app/execution/order_manager.py`, `tests/test_backtest_phase1_1_m14.py` (new), `docs/m14_phase1_review.md`, `docs/m14_backtesting_audit.md`.

---

## 8. Measured baseline and B-12 ablation

Recorded from the baseline files after Phase 1.1. Both files were produced by `scripts/freeze_m14_baseline.py` from git commit `498f8bc0dd9abbfc855e3e0e057fd6eda415144f`, with `backend_app_has_uncommitted_changes: false`. Window `2026-08-03` to `2026-10-30`, anchor last bar `2026-11-20`. Percentages below are the stored metric strings rounded for reading. The JSON strings are the source of truth.

| Run | File | Scenario | Trades | Total return | Max drawdown | Sharpe | Profit factor | Shariah rejections |
|---|---|---|---|---|---|---|---|---|
| Full 8-symbol universe | `tests/baselines/m14_post_phase1_1.json` | A zero cost | 22 | 1.29% | 1.55% | 1.20 | 1.47 | 0 |
| Full 8-symbol universe | same | B realistic cost | 22 | 1.04% | 1.595% | 0.974 | 1.40 | 0 |
| Full 8-symbol universe | same | C STRICT | 0 | 0 | 0 | — | — | 132 |
| First four symbols | `tests/baselines/m14_ablation_first4.json` | A zero cost | 9 | 0.56% | 0.95% | 0.720 | 1.49 | 0 |
| First four symbols | same | B realistic cost | 9 | 0.46% | 0.975% | 0.590 | 1.42 | 0 |
| First four symbols | same | C STRICT | 0 | 0 | 0 | — | — | 47 |

The first-four file sets `explicit_symbols` to TCS, INFY, RELIANCE, HDFCBANK. The full-universe file leaves symbols unset and scans the demo list (those four plus SUNPHARMA, TATAMOTORS, BEL, COALINDIA).

Stored strings behind the rounded cells: full-universe A drawdown `0.01546545012707008279310607259`, Sharpe `1.199565212541984`; B drawdown `0.01594593594355958713728912272`, Sharpe `0.9737007739154933`. First-four A drawdown `0.009531894019035602249345879807`, Sharpe `0.7198316254890831`; B drawdown `0.009749357912311451709888310326`, Sharpe `0.5895790536087171`. Returns and profit factors match the table with no further rounding (`0.0129`, `0.0104`, `0.0056`, `0.0046`, and profit factors `1.47`, `1.40`, `1.49`, `1.42`).

### B-12 universe-scan ablation

**B-12 is verified by ablation for scan behavior.** The two runs use the same code commit and the same window. Coverage in the files records the scan: `scanned_symbols` is TCS, INFY, RELIANCE, HDFCBANK in the ablation, and those four plus SUNPHARMA, TATAMOTORS, BEL and COALINDIA in the full-universe file. That is a valid comparison of scan size.

Both freezes install the full 8-symbol demo history. The `--symbols` flag limits only the backtest scan. Breadth and the equal-weight benchmark proxy still read every stored equity symbol in both runs, because those functions use the stored universe and do not take the backtest's symbol list. The ablation isolates who can be traded. It leaves the breadth sample and the proxy constituents on the full demo set in both runs.

On this synthetic sample the full scan changed the observed book as follows:

- Trades rose from 9 to 22 in both the zero-cost and realistic-cost scenarios.
- Total return and Sharpe rose (zero cost 0.56% / 0.720 to 1.29% / 1.20; realistic cost 0.46% / 0.590 to 1.04% / 0.974).
- Max drawdown rose (zero cost 0.95% to 1.55%; realistic cost 0.975% to 1.595%).
- Volatility rose: zero cost `0.03130863062230232` to `0.04292966906928981`; realistic cost `0.03119077259430384` to `0.04280284585302278`.
- Realistic-cost transaction costs rose from `86.6100` to `216.7800`. The zero-cost scenario reports `0.0000` in both runs, because that scenario adds no transaction costs.
- Ownership-blocked exits rose from 2 to 4 in A and in B. Scenario C stayed at 0.
- STRICT Shariah rejections rose from 47 to 132. Both runs produced 0 trades.
- Profit factor was slightly lower on the full scan (1.49 to 1.47 zero cost; 1.42 to 1.40 realistic cost). The return and Sharpe increases do not extend to every metric.

These are portfolio outcomes. Entries share one cash balance and a position limit (`max_positions` 3 in these runs), so a trade in an added symbol can change which other trades are taken, their size, and their exits. The ablation shows what the book did when the scan grew from four symbols to eight. It does not assign a performance change to any one added symbol.

This verifies that the full-universe scan runs and that widening the scan changes trades, rejections, costs and risk on this sample. It is software behavior on synthetic data. It is not evidence that the strategy is profitable, and it is not a forecast.

### Limitations (apply to every figure in this section)

- The prices are synthetic demo data, not real market history. `evidence_grade` is `demo` and `data_provenance.kind` is `synthetic` in both files.
- The dataset is 8 symbols and 520 bars, about two years, and the reported window is `2026-08-03` to `2026-10-30`.
- STRICT Shariah produced no trades because the demo dataset has no point-in-time COMPLIANT snapshots for these entries. The 47 and 132 counts are screening rejections.
- The figures are regression output. They are not evidence of live or future performance.
- The realistic-cost scenario is a configured cost scenario in the backtest. It is not a measurement of actual brokerage or tax charges.
- F-4 (runtime scaling on a real universe) stays open. Section 7.4 records the single-run timings. Those timings do not close F-4. The elapsed times in both files were measured before the section 9 breadth cache and are not current runtime figures.

---

## 9. F-4 breadth runtime: profiling and run-scoped cache

Status: **implemented and verified on 2026-11-27 (section 9.6); not yet committed.** Strategy rules, the breadth formula, cost defaults and baseline values were not changed.

### 9.1 Where breadth is computed and how often

- `compute_universe_breadth(as_of_date)` (`app/regime/market_breadth.py`) runs `add_indicators` on up to 520 bars of every equity symbol (benchmarks excluded) and counts closes above SMA50.
- Its only production caller is `classify_market` (`app/regime/classifier.py`), called by `generate_unified_signal`. The simulator calls `generate_unified_signal` once per candidate per session (symbols with a bar that session, not held, not pending).
- Before the cache, one session recomputed the same as-of breadth once per candidate: up to (candidates × equity symbols) indicator passes, where (equity symbols) passes give the same answer. In database mode each recomputation also loaded every equity's candles.

### 9.2 Measurement method and results

In-memory demo mode only (`DATABASE_URL=""`), with the fixed anchored demo bars that `freeze_m14_baseline.py` installs (8 equities × 520 bars, last bar 2026-11-20). Throwaway script outside the repo; no repository code was modified for profiling. Each figure is a single run on one machine.

| Measurement | Configuration | Result |
|---|---|---|
| One breadth call | as of 2026-10-15, 8 equities, mean of 20 calls after 2 warm-ups | **245.7 ms per call** |
| cProfile of one backtest | scenario A settings (`RESEARCH_ONLY`, `ZERO`, `max_positions` 3), window 2026-10-01 to 2026-10-30 | 22 sessions, 7 trades, 70 signal evaluations, 51.78 s under the profiler |
| Breadth share | same run | 70 breadth calls for only **11 distinct as-of dates** (up to 8 per date); breadth cumulative **34.27 s of 51.78 s (66%)** |
| Other costs, same run | same run | `add_indicators` 770 calls 40.6 s (560 of them inside breadth); `build_context` 140 calls 10.5 s; `ensure_benchmark_history` 280 calls 3.1 s, of which `bar_fingerprints` 3.0 s |
| Per-date memo prototype | same run, no profiler, same process, breadth memoised by as-of date only | uncached **29.13 s**, memoised **13.61 s** (53.3% less); trades, metrics and equity curve identical |

Conclusion: repeated breadth computation was the largest single cost of a real-signal backtest on this data, and almost all of it was redundant within a session. A cache is justified. The prototype keyed only by date was a measurement aid; the implementation below adds the universe and data fingerprint to the key, which costs one fingerprint pass per call (about 11 ms per call in memory mode in this profile). Post-implementation timing is in section 9.6; it is a single run and not a same-process comparison.

### 9.3 Cache design and invalidation rules

- **Scope:** `breadth_cache_scope()` (context manager in `market_breadth.py`, held in a `ContextVar`). `run_backtest` wraps the whole run in it. The memo is created when the scope opens and discarded when it closes, so a run never sees another run's breadth and results cannot depend on run order. Nested scopes share the outer memo.
- **Not cached:** any call outside a scope (live `/regime` and `/market` endpoints, signal APIs), and latest-bar breadth (`as_of_date=None`).
- **Key:** `(as_of_date, sorted equity symbols with registered benchmarks removed, sorted (symbol, stored-bar fingerprint) pairs)`. Fingerprints come from the Phase 1.1 `repository.bar_fingerprints`: a digest of each in-memory frame in demo mode, and one grouped aggregate query (`persistence.candle_fingerprints`) in database mode. No candles are loaded to build the key.
- **Invalidation:** a different as-of date, an added or removed equity, a benchmark-registry change (`BENCHMARK_SYMBOLS`), or any added, removed or edited equity bar produces a different key and a recompute. The fingerprint covers each equity's whole stored series, so an edit after the as-of date also recomputes (conservative; the result is unchanged). Benchmark bars are outside the key and cannot invalidate or enter equity breadth.
- **Values:** the stored dict holds only scalars; every hit returns a fresh copy, so a caller mutating its result cannot change the memo.
- **Separate from the proxy cache:** `_PROXY_CACHE` in `regime/benchmark.py` and `clear_benchmark_cache()` are unchanged and share nothing with the breadth memo except the fingerprint function.
- **Known gap inherited from Phase 1.1:** a raw SQL edit that only moves a middle bar's date without changing any value, count or `updated_at` is not detected by `candle_fingerprints` (documented in that function).

### 9.4 Tests

`backend/tests/test_breadth_cache_m14.py` (new, 13 tests): cached equals uncached over five sessions with one computation per session; nothing cached outside a scope or for latest-bar breadth; as-of date change; equity added and removed; benchmark-registry change; edited as-of bars (forced to 100% and 0% above SMA50) and restored bars; edited future bar; benchmark bars excluded and not invalidating; no mutation of shared sample data or of the memo; nested and consecutive scopes; a backtest with the cache equal to one with the scope disabled (trades, metrics, equity curve, breadth seen by each candidate) with fewer computations; consecutive backtests not sharing a memo; database mode (SQLite) where a hit loads no candles and an edited bar with unchanged `updated_at` recomputes.

Existing tests were not modified. `test_scenario_order_does_not_change_symbols_breadth_trades_or_metrics` still records breadth inputs per scenario because the memo ends with each run.

### 9.5 What F-4 still leaves open

- Breadth work per run is now (sessions with candidates × equity symbols) instead of (candidates × equity symbols). It still grows with universe size; nothing has been measured on a real universe.
- Other per-signal costs remain: `build_context` runs twice per signal (`evaluate_all_strategies` and `generate_unified_signal`), and `ensure_benchmark_history` fingerprints every equity about four times per signal. These belong to the Phase 5 runtime budget (B-24) and were not changed.
- The baseline elapsed times in section 8 predate the cache. Baseline values are unchanged by design; the `--compare` check in section 9.6 confirms it.

### 9.6 Verification (2026-11-27)

Run by the maintainer on the working tree (uncommitted), from `backend/`:

- **New cache tests:** `tests/test_breadth_cache_m14.py`: **13 passed**.
- **Focused breadth, M14 and point-in-time tests:** 13 + 12 + 27 + 9 = **61 passed**.
- **Full backend suite:** **144 passed, 2 errors**, 146 collected. Both errors are PostgreSQL-marked tests, `test_postgres_reconcile_smoke` (`test_integration_m12.py`) and `test_postgres_snapshot_persisted` (`test_valuation_m13.py`). They could not connect to `localhost:5432` because no PostgreSQL server was running. Neither test calls the breadth code or the simulator. No test failed. The earlier figure of 133 passed was recorded with PostgreSQL running, so these two tests are **not verified** in this run.
- **Baseline identity:** `scripts.freeze_m14_baseline --compare tests/baselines/m14_post_phase1_1.json /tmp/m14_post_f4.json` printed `scenarios_sha256 equal: True`, and "no differences" for A, B and C. That covers metrics, trades and the equity-curve `sha256`. The committed baseline files were not modified. This is the strongest evidence that the cache leaves real backtest output unchanged.
- **Timing (single runs, from the freeze output):** A 34.1 s, B 33.7 s, C 64.2 s, against 76.7 s, 86.0 s and 159.9 s recorded in the committed baseline. The machine and load differ between those runs, so this is not a same-process measurement and does not establish the speedup. The paired same-process timing from section 9.2 was not repeated, because the script `/tmp/f4_profile.py` is no longer on disk.
