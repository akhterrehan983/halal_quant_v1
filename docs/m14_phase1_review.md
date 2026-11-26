# M14 Phase 1 — Review Notes

Status: Phase 1 and the Phase 1.1 correction (section 7) are implemented and awaiting commit. Phase 2 has **not** been started.
Data caveat: every number below comes from **synthetic demo data**. It is software-regression output, not performance evidence. Nothing here is a research-grade claim.

Sources: `backend/tests/baselines/m14_pre_phase1.json` (clean tree at commit `08c1680`) and `backend/tests/baselines/m14_post_phase1.json` (uncommitted Phase 1 tree, so not reproducible from the commit alone). Both baselines were produced by `backend/scripts/freeze_m14_baseline.py`.

Test status after this review round: `tests/test_backtest_phase1_m14.py` 27 passed (23 original + 4 stop-breach reporting tests); full backend suite 121 passed in 541.6s. An earlier full-suite run of 117 tests took 258.7s. The 541.6s figure is not a code-caused doubling: the only code changed between those runs was reporting (no trading logic), and the run timings are not comparable without a clean measurement (see section 7.4). Frontend tests (5) and build passed in the previous round; the frontend was not changed in this round.

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

Existing baseline events: the post baseline contains two ownership-delayed exits (RELIANCE entered 2026-10-15, exit 2026-10-20 at 133.5484; COALINDIA entered 2026-10-27, exit 2026-10-30 at 262.3408). The baseline JSON predates the new fields, so their stop prices and loss beyond stop are **not known from the files**. They appear when the clean baseline is regenerated.

## 3. Baseline diff explanation (A: zero cost, B: realistic cost, C: STRICT)

Headline changes: A trades 8 to 22, A total return 0.44% to 1.29%; B total return 0.34% to 1.04% and costs 78.29 to 216.78; C trades 0 to 0 and Shariah rejections 47 to 132. The higher returns are **not** evidence of improvement. They come from changed mechanics on synthetic data.

Rule applied below: **Verified** means shown by the baseline files, the code, or both. **Hypothesis** means plausible but not isolated; no causality is claimed without an ablation.

### B-12 full-universe scan (and benchmark exclusion)
- Verified: pre-Phase 1 code scanned `syms[:4]`. The demo universe order is TCS, INFY, RELIANCE, HDFCBANK, SUNPHARMA, TATAMOTORS, BEL, COALINDIA. Pre trades are only HDFCBANK (4) and RELIANCE (4), both within the first four.
- Verified: 14 of the 22 post trades are in TATAMOTORS (5), COALINDIA (8) and SUNPHARMA (1), symbols the capped scan could not reach. TCS, INFY and BEL have no trades in either run.
- Verified: the earliest divergence is COALINDIA entered 2026-08-04, one day before the first common trade.
- Hypothesis: most of the 8 to 22 trade increase comes from B-12. Later trades are path dependent (max 3 positions, shared cash), so the per-trade split between B-12 and the other effects is not known.
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

### What an ablation would establish (plan, not yet run)
Baselines should be regenerated after the Phase 1 commit (clean tree):

```
cd backend
.venv/bin/python -m scripts.freeze_m14_baseline --out tests/baselines/m14_post_phase1_clean.json
.venv/bin/python -m scripts.freeze_m14_baseline --symbols TCS,INFY,RELIANCE,HDFCBANK --out tests/baselines/m14_ablation_first4.json
.venv/bin/python -m scripts.freeze_m14_baseline --compare tests/baselines/m14_pre_phase1.json tests/baselines/m14_ablation_first4.json
.venv/bin/python -m scripts.freeze_m14_baseline --compare tests/baselines/m14_ablation_first4.json tests/baselines/m14_post_phase1_clean.json
```

Reading the two comparisons:
- `pre` vs `ablation_first4`: same four symbols as the old cap, new code. Differences come from B-01, B-02, B-03 and the session-order change **combined** (not separable by this run).
- `ablation_first4` vs `post_phase1_clean`: same code, four versus eight symbols. Differences are attributable to B-12.
- If C's Shariah rejections equal 47 on the first-four run, the rise to 132 is entirely the wider scan, and signal inputs for those four symbols were unchanged.
- Separating B-02 from B-03 and B-01 would require temporary toggles in the simulator. That has not been done and is not proposed here.

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
- Still open: F-4, the runtime budget for a real universe (section 7.4). The baseline must be regenerated after the commit; `m14_post_phase1.json` is superseded (section 7.3).

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

### 7.3 Baseline impact (not yet measured)

- `m14_post_phase1.json` was produced before Phase 1.1 and is **superseded**. Do not use it as the Phase 1 baseline.
- Hypothesis (unverified until the clean baseline is regenerated): the demo baseline may differ from `m14_post_phase1.json` because (a) breadth no longer includes the proxy (F-2; the breadth sample was 8 or 9 symbols depending on run order), and (b) the proxy is summed in sorted symbol order, which can change its last floating-point digits (F-1). Any difference must be attributed to F-1 or F-2 from the data, not assumed.
- The earlier ablation plan (section 3) still applies, with one change: the comparison between the pre-Phase 1 baseline and the first-four-symbol run now also includes the F-2 breadth change, so it is no longer limited to B-01, B-02 and B-03.

### 7.4 Remaining runtime concern (F-4, still open)

- Verified (timings only): the full backend suite took 541.6 s for 121 tests (18:41 run) and 258.7 s for 117 tests (17:32 run). The 308.7 s run of 20 tests overlapped with a baseline freeze, so its timing is contaminated. The phase-1 test file alone took 2.4 s, because its signal generator is stubbed.
- Not established: the cause of the 541.6 s vs 258.7 s difference. The code changed between them was reporting only, so environment load is more likely. Needs a clean `--durations` measurement.
- Verified (from code): each real signal evaluation calls `classify_market`, which recomputes breadth over every equity symbol. A backtest session therefore does up to (scanned symbols × equity symbols) indicator recomputations, with no caching. Real backtests run this path. Stubbed tests do not.
- Verified (from the freeze output): one real 8-symbol demo scenario took 62 to 112 s in the measured run. Phase 1.1 did not change that cost and did not measure it on a real universe. A runtime budget and caching belong to Phase 5 (B-24).
- Phase 1.1 adds a per-signal cost when no stored benchmark exists: symbol-list filtering plus the input fingerprint. After the 7.1a fix the fingerprint covers bar content, so in memory mode it hashes every equity frame on each call, and in database mode it runs one grouped aggregate query (plus the symbol-list query) on each call. This is more work than the first Phase 1.1 version did. It is not measured. The approved breadth-caching follow-up is intended to share the same fingerprint query and reduce repeated work; it is not part of this change.

### 7.5 Files changed in Phase 1.1

`app/market_data/benchmarks.py` (new; call-time settings binding), `app/market_data/persistence.py` (`candle_fingerprints`), `app/core/config.py`, `app/market_data/repository.py` (`bar_fingerprints`), `app/regime/benchmark.py`, `app/regime/market_breadth.py`, `app/regime/config.py`, `app/backtesting/universe.py`, `app/backtesting/simulator.py`, `app/backtesting/schemas.py`, `app/execution/order_manager.py`, `tests/test_backtest_phase1_1_m14.py` (new), `docs/m14_phase1_review.md`, `docs/m14_backtesting_audit.md`.
