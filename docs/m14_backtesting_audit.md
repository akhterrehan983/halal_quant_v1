# M14 Phase 1 — Backtesting Methodology Audit and Implementation Plan

**Status:** Written as an audit-only document on 2026-11-26. Implementation progress is recorded in the **Implementation status** section below. Sections 1 to 14 are the original audit and plan and are kept as written, except for passages marked **[Status update]**.
**Date:** 2026-11-26
**Scope:** `backend/app/backtesting/`, the signal, strategy, regime, feature, market-data, Shariah, and portfolio modules that the backtest calls, plus the related tests and docs.

---

## Implementation status (actual scope delivered)

Phase 2 and later have **not** started. Nothing here claims research-grade results; all runs use synthetic demo data.

**Delivered in Phase 1** (details and baseline-diff review in `docs/m14_phase1_review.md`):

| Finding | Planned phase | Delivered | Note |
|---|---|---|---|
| B-01 as-of data reads | 1 | Phase 1 | Point-in-time loaders and breadth; no 520-bar tail truncation |
| B-02 stop/target enforcement | 1 | Phase 1 | Stop-first on a bar that hits both; ownership-restricted stop breaches exit at the first authorised open, with breach date, stop, fill and loss beyond stop reported |
| B-03 signal-time sizing, fill-time validation | 1 | Phase 1 | Quantity can only be reduced at fill |
| B-08 stale marks | 1 | Phase 1 | Counted, warned, limit flagged |
| B-09 excluded symbols (surfacing only) | 1 | Phase 1 | Listings/delistings are **not** fixed (M15) |
| B-28 provenance, evidence grade | 1 | Phase 1 | Synthetic runs labelled `demo` in storage, API and UI |
| B-30 coverage warnings | 1 | Phase 1 | |
| **B-12 four-symbol scan cap removed** | **3** | **Phase 1 (pulled forward)** | Decision 5. Full eligible universe is scanned. Demo scenario runtime rose from about 51 s to 62–112 s in one measured run (noisy, not a controlled benchmark); real-universe scaling is unmeasured |
| **B-14 benchmark excluded from the tradable universe** | **4** | **Phase 1 (pulled forward)** | Needed because removing the cap would make the proxy tradable. Documentation of the proxy and the survivor-bias disclosure remain Phase 4; the full fix is M15 |

**Delivered in Phase 1.1** (narrow correction, no strategy, cost or ownership change):

| Review finding | Fix |
|---|---|
| F-1 run-order dependence | Building the benchmark proxy no longer mutates the stored symbol list or history store; the proxy is a pure function of stored equity histories, built in sorted order and cached by a content fingerprint of the symbols and their stored bars (database and memory mode), so a changed bar with an identical symbol set rebuilds it. The tradable universe and the benchmark are independent of scenario and run order |
| F-2 benchmark counted in breadth | Registered benchmarks are excluded from breadth (as-of and latest paths). Breadth stays point-in-time and causal |
| F-3 hardcoded benchmark set | Explicit registry (`app/market_data/benchmarks.py`) with a `BENCHMARK_SYMBOLS` configuration setting. `list_universe_symbols()` now returns the equity universe only, so signal scans, valuation and API listings also exclude benchmarks. A registered benchmark is rejected as a BUY order |

**Still open (not claimed as resolved):** survivorship bias (M15), benchmark-relative metrics (B-13), REALISTIC cost default and cost accounting (Phase 3, rates to be verified), walk-forward (Phase 2), and all other findings not listed above.

---

## 1. Executive summary

The backtest engine is a **research sandbox, not a research-grade engine**. Passing tests do not change that.

What is sound:

- Signals use only data up to the session close, and fills happen at the next session's open. Regime and breadth are point-in-time (M11).
- Backtests have no leverage, no short selling, and no intraday logic.
- Backtests keep their own accounting (`SimBook`) and never write to the live portfolio book, so the M12 single-book architecture is preserved.
- STRICT Shariah mode rejects entries without a point-in-time COMPLIANT snapshot.

What blocks credible research:

1. **The price loader keeps only the latest 520 bars per symbol, regardless of the backtest date.** Over a multi-year history, sessions before that window silently produce no signals. Latent in the demo (520 bars is nearly the whole demo history); active as soon as real multi-year data is loaded.
2. **Stop-loss and target levels are computed but never enforced.** Exits are purely time-based, so the simulated strategy is not the strategy that was evaluated.
3. **Walk-forward reports train and test periods blended together** while its notice describes the results as out-of-sample. No out-of-sample metric is isolated.
4. **Costs are understated.** Buy-side costs are missing from trade-level P&L and from the reported cost metric. The default cost scenario is ZERO, so default headline results are cost-free.
5. **Execution is asymmetric and unconstrained.** Entries fill at next open plus slippage; exits fill at the same-session close with no slippage. There is no liquidity (ADV) cap, and open positions are never liquidated at the end.
6. **Survivorship is not handled.** Symbols are filtered to those with data across the whole range, which removes listings and delistings mid-window. The universe is today's list, and the benchmark is an equal-weight average of that same survivor set.
7. **Shariah point-in-time is weaker than it looks.** `screening_date` is the date the screen was run, not the date financial data was published. Nothing re-checks a holding after entry.
8. **Monte Carlo is degenerate.** Shuffling trade order does not change the sum of trade P&L, so the p5, p50, and p95 are always identical. Confirmed by running it.
9. **Benchmark-relative metrics are absent.** `benchmark_return` is always `None`, and Sortino is declared but never computed.

**Overall verdict:** Current backtest output must be labelled as a software demo, not evidence of strategy performance. Phases 1 to 3 below are required before any result can be presented as research-grade. Several of the remaining gaps need M15 data (point-in-time membership, delisting, adjusted prices, publication dates) and cannot be fixed inside M14 alone.

---

## 2. Scope and method

**Read (static audit):** `backtesting/` (simulator, schemas, metrics, execution, costs, data, universe, compliance, portfolio, walk_forward, validation, validation_sensitivity, monte_carlo, store, config, events, engine); `strategies/` (evaluator, context, indicators, config, registry); `signals/generator.py`; `regime/benchmark.py`; `features/` (trend, momentum, volatility, relative_strength, pipeline); `market_data/repository.py`; `data/sample_data.py`; `shariah/eligibility.py`, `snapshots.py`, `screening.py`, `store.py`; `portfolio/position_sizing.py`; `execution/costs.py`, `settlement.py`; `api/v1/backtests.py`; `frontend/src/pages/BacktestingLab.jsx`; `tests/test_backtesting.py`, `tests/test_integration_m9.py`; docs `backtesting.md`, `technical_debt.md` (TD-H3, TD-H4, TD-H6, TD-M5, TD-M6), `implementation_roadmap.md` (M14, M15), `prd_gap_analysis.md` §8.

**Empirical check (demo data, one run, `DATABASE_URL` empty, so in-memory mode):**

| Run | Result |
|---|---|
| RESEARCH_ONLY, REALISTIC costs, 90-day window ending 10 days ago, max 3 positions | 8 trades; total return 0.39%; CAGR 1.58%; Sharpe 0.52; reported costs ₹78.53; 107.7 s |
| Symbols that produced trades | HDFCBANK, RELIANCE only |
| Open position value at window end | ₹9,635.92 invested (~9.6% of capital), still open, excluded from trade stats |
| Monte Carlo on those 8 trades | p5 = p50 = p95 = 392.09 (degenerate) |
| STRICT mode, same window | 0 trades; 43 Shariah rejections |
| `list_universe_symbols()` | includes `NIFTY500_PROXY` alongside the 8 demo stocks |
| `sortino` in result | `None` |
| `benchmark_return` in result | `None` |

Findings marked **Confirmed by run** were reproduced. Findings marked **Confirmed by reading** come from code inspection and need a test to prove them. Findings marked **Potential** need verification before they are treated as defects.

---

## 3. Current architecture and execution path

```
market_data.repository.get_history_dataframe(symbol, limit=520)       [data load: latest 520 bars]
  └─ backtesting.data.slice_as_of / index_as_of                        [as-of slice]
       └─ signals.generator.generate_unified_signal(sub, as_of_index=-1)
            ├─ regime.classifier.classify_market(as_of_date=eval)      [benchmark + breadth, PIT per M11]
            ├─ features.relative_strength.aligned_relative_returns      [PIT per M11]
            ├─ strategies.evaluator (6 strategies, indicators on sub)  [backward-looking windows]
            └─ scoring → category, stop_reference, target_reference
       └─ backtesting.compliance.check_entry (STRICT / RESEARCH_ONLY)   [Shariah PIT]
       └─ backtesting.execution.fill_market_next_session               [next open + slippage]
       └─ portfolio.position_sizing.compute_position_quantity          [risk-based sizing, uses fill price]
       └─ pending_entries → processed at entry_date                     [cash check, costs]
  └─ exits: time-based only (hold_days, ownership-authorized date)     [fill at session close, no slippage]
  └─ backtesting.portfolio.SimBook                                     [own cash / positions / equity]
  └─ backtesting.metrics.compute_metrics                               [CAGR, vol, Sharpe, DD, WR, PF]
  └─ backtesting.validation.build_validation_report                    [static warnings]
```

Sensitivity (`validation_sensitivity.py`), walk-forward (`walk_forward.py`), and Monte Carlo (`monte_carlo.py`) are wrappers around this same run loop.

Key constants: `BacktestConfig.cost_scenario = ZERO`, `slippage_bps = 10`, `max_positions = 5`, `min_signal_score = 0`, `hold_days` defaults to 10 (swing) or 60 (positional), in **calendar** days. `syms[:4]` caps the entry scan to four symbols per session.

---

## 4. Confirmed positives (checked, no defect found)

| ID | Area | Finding |
|---|---|---|
| P-01 | Signal timing | Signal uses bars up to session close (`index_as_of`, `df.iloc[: idx + 1]`). Fill is on the next session's open (`next_session_row`, `td > signal_date`). No signal-close fill. |
| P-02 | Indicators | Rolling and EWM features are backward-looking. Breakout excludes the current bar via `shift(1)`. Indicators are computed on the as-of slice only. |
| P-03 | Regime / breadth | M11 point-in-time: `evaluation_date()` caps benchmark and breadth; covered by `tests/test_regime_point_in_time.py`. |
| P-04 | Relative strength | `aligned_relative_returns` inner-joins the stock to the benchmark, so no benchmark date after the stock's last visible bar can enter (verified by reading). `build_context` calls it without `as_of_date`, which is fragile but not leaking today (see B-26). |
| P-05 | Leverage / shorting | Entry requires `total <= book.cash`. No short logic exists. |
| P-06 | Isolation from live book | Backtest imports `portfolio.money` and `position_sizing` only. It does not call the portfolio book, execution, or broker code. M12 single-book is preserved. |
| P-07 | Shariah STRICT | Entry requires a COMPLIANT snapshot with `screening_date <= session`. RESEARCH_ONLY is labelled in warnings and `shariah_mode`. |
| P-08 | Ownership | Exits are blocked until `sell_authorized_date`; blocked exits are counted in `ownership_blocked_exits`. |
| P-09 | Drawdown | `max_drawdown` is the maximum over the daily equity curve, computed from a running peak. |

---

## 5. Findings (severity-ranked)

Severity scale: **Critical** (invalidates results or misstates what was tested), **High** (materially biases results or blocks a claim), **Medium** (misleading or incomplete, not directly invalidating), **Low** (hygiene).
"Blocks credible research" means the finding must be fixed or disclosed before any backtest result is shown as evidence.

### Critical

**B-01 — Price loader keeps only the latest 520 bars, regardless of backtest date**
- **Evidence:** `market_data/repository.py` `get_history_dataframe`: `df.tail(limit)` (lines 83 and 92). Backtest calls use `limit=520`: `simulator._marks`, the entry scan, `execution.fill_market_next_session`, `repository.iter_symbol_histories` (used by `universe.symbols_with_data` and by `regime/market_breadth.compute_universe_breadth`). Only `trading_dates` uses `limit=2000`.
- **Confirmed by reading.**
- **Why it matters:** The window is anchored to the most recent bar, not the session. For any session older than the window, `index_as_of` returns -1 and the session is skipped as `idx < 60`, so the backtest silently produces no entries and marks fall back to entry price. Breadth for those sessions is empty. `symbols_with_data` tests coverage on the same 520-bar window, so its answer is also window-dependent. In the demo, 520 bars is almost the entire history, so this is latent. With multi-year real data it becomes a silent truncation of the requested range.
- **Remediation:** Make every backtest data read take an explicit `end` (as-of) bound and a lookback length. The DB path already accepts `start`/`end` and should be used; the in-memory path must be checked to honour them. Add a coverage check that fails loudly (or warns) when the requested range is not fully covered by the loaded history.
- **Blocks credible research:** Yes.

**B-02 — Stop-loss and target are computed but never enforced**
- **Evidence:** `simulator.py` sets `stop = D(sig.stop_reference)` and stores it in `SimPosition.stop`, and `sizing` uses it. The exit loop (lines ~100–130) checks only `entry_date + hold_days` and the ownership date. `pos.stop` is never read after entry. `execution.exit_signal_price` is defined and never called.
- **Confirmed by reading.**
- **Why it matters:** The strategies define risk exits (`atr_stop_mult`, `atr_target_mult`), but the simulator holds every position for the full hold period regardless of price. The simulated strategy is not the evaluated strategy, and drawdowns and tail losses are understated.
- **Remediation:** Add daily-bar stop and target checks at the session level. Document the intrabar ambiguity rule (if both are hit on one bar, assume the stop first). Decide whether `hold_days` remains a hard cap.
- **Blocks credible research:** Yes.

**B-17 — Walk-forward reports blended train and test metrics, labelled as out-of-sample**
- **Evidence:** `walk_forward.py` sets `start_date = train_start` and `end_date = test_end`, runs one simulation over the whole span, and returns its metrics. `train_end` and `val_end` are never used. The response notice says "Out-of-sample segments embedded per fold end_date."
- **Confirmed by reading.**
- **Why it matters:** The metrics include the training period. The result is presented as OOS when it is not. This is the exact failure mode TD-H6 and the M14 acceptance criteria are meant to prevent.
- **Remediation:** Run train, validation, and test segments as separate simulations with frozen parameters. Report segment metrics separately and never blend them into a headline. Only test-window trades may count toward OOS metrics.
- **Blocks credible research:** Yes.

### High

**B-03 — Position sizing uses the next session's open, which is future information**
- **Evidence:** `simulator.py` calls `fill_market_next_session` at signal time to obtain `entry_px`, then passes `entry_price=entry_px` to `compute_position_quantity`. The quantity is therefore computed from a price that is not known at the signal close.
- **Confirmed by reading.** Magnitude is probably small, but it breaks the stated no-look-ahead rule.
- **Remediation:** Size on the signal close with an explicit assumed-fill rule (close × (1 + slippage)). Re-validate quantity at the actual fill. Add a test that changing the next open does not change the signal-time quantity.

**B-04 — Buy-side costs are missing from trade P&L and from the cost metric**
- **Evidence:** On entry, `fees` (buy cost) is added to `book.costs_paid` and deducted from cash, but `SimPosition` does not carry it. On exit, `CompletedTrade.costs = fees` (sell cost only), and `net = notional − qty × entry_price − fees` (sell cost only). `compute_metrics` sums `t.costs`, so `transaction_costs` excludes buy costs.
- **Confirmed by reading.** The run's reported costs (₹78.53) equal the sum of trade costs, so buy costs are excluded from the metric.
- **Why it matters:** Equity and total return are correct because cash is debited, but per-trade net P&L, profit factor, and the cost metric are overstated or understated as a result.
- **Remediation:** Carry buy costs on the position and include them in trade `costs` and `net_pnl`. Add a reconciliation test: `sum(net_pnl) == final_capital − initial_capital` when no positions are open at the end.

**B-05 — Default cost scenario is ZERO, so default results are cost-free**
- **Evidence:** `schemas.BacktestConfig.cost_scenario = CostScenario.ZERO`. `BacktestingLab.jsx` does not set it. `costs.scenario_config(REALISTIC)` has `brokerage_pct = 0`, so REALISTIC also omits brokerage.
- **Confirmed by reading.**
- **Remediation:** Change the default only after the user approves it (see Section 13). Add a visible cost-scenario label to every result. Confirm and document the rate table.

**B-06 — Exit fills are optimistic and asymmetric**
- **Evidence:** Entries fill at next open plus `slippage_bps`. Exits use `marks[sym]` (same-session close) with no slippage and no next-session delay.
- **Confirmed by reading.**
- **Remediation:** Apply the same fill convention to exits (next-session open plus slippage, or a documented close-based convention applied symmetrically).

**B-07 — No liquidity or ADV constraint; `max_adv_participation` is unused**
- **Evidence:** `BacktestConfig.max_adv_participation` is defined; no code reads it. Fill quantity is limited only by cash and risk.
- **Confirmed by reading.**
- **Remediation:** Cap quantity at a fraction of trailing ADV (volume is already loaded). Record rejections as `liquidity_rejections`.

**B-08 — Missing bars are silently marked at entry price**
- **Evidence:** `simulator._marks` wraps every symbol read in `except Exception: continue`. `SimBook.equity` defaults to `entry_price` for symbols with no mark. The same pattern appears in `trading_dates`.
- **Confirmed by reading.** This is the same class of issue M13 fixed with strict price resolution.
- **Remediation:** Use last-known-price with a staleness limit and count stale marks. Exclude or flag the symbol when the staleness limit is exceeded. Never silently fall back to cost.

**B-09 — Survivorship: coverage filter removes mid-window listings and delistings**
- **Evidence:** `universe.symbols_with_data` keeps only symbols where `dates.min() <= start and dates.max() >= end`. Symbols that listed after `start` or delisted before `end` are dropped. The fallback `out or [...]` returns any symbol with data if none qualify. Universe is `list_universe_symbols()`, the current list.
- **Confirmed by reading.** This selects on future information and removes the cases that matter most for survivorship.
- **Remediation (Phase 1, inside M14):** Stop silent exclusion; record every dropped symbol and its reason in `warnings`. Phase 2 of M15 supplies the real membership fix.
- **Blocks credible research:** Yes, until M15 membership data is available.

**B-10 — Shariah point-in-time is weaker than it appears**
- **Evidence:** `shariah/eligibility.evaluate_for_standard` sets `verified_at = as_of`, where `as_of` defaults to `date.today()` in `run_screening`. `snapshots.append_snapshot` sets `screening_date = rec.verified_at`. Financial inputs (`financials`) carry no publication or filing date. `compliance.snapshot_as_of` falls back to `get_latest_eligibility`, which is the newest record regardless of when it was created. Nothing re-checks a holding after entry, and `check_entry` runs only on entry candidates.
- **Confirmed by reading.** The date tested is the screen run date, not the date the financial data existed.
- **Why it matters:** A snapshot created today can carry a `screening_date` the backtest treats as known at an earlier session only if that date was entered explicitly. More importantly, the backtest cannot tell whether a financial period was published before the session. STRICT mode therefore overstates how well Shariah point-in-time is enforced.
- **Remediation:** Record `financial_period_end` and `published_at` for every financial input; use `published_at <= session` in compliance checks. Add a periodic (or per-session) compliance check for held positions that can force exit or flag. This must not weaken any existing Shariah safeguard.
- **Blocks credible research:** Yes, for STRICT claims. Requires publication-date data (see Section 9).

**B-11 — Monte Carlo is degenerate**
- **Evidence:** `monte_carlo.monte_carlo_trade_returns` shuffles the list of trade `net_pnl` values and sums them. The sum is invariant to order, so every simulation returns the same value.
- **Confirmed by run:** p5 = p50 = p95 = 392.09.
- **Remediation:** Bootstrap trades with replacement, or use a block bootstrap of daily equity returns. Report distributions of CAGR and max drawdown, not only final P&L.

**B-12 — Entry scan capped to four symbols, dependent on list order**
- **Evidence:** `simulator.py` loops `for sym in syms[:4]`. TD-M5 already records this. The order of `syms` comes from `list_universe_symbols()` (sorted) filtered by `symbols_with_data`.
- **Confirmed by reading.** The effective entry universe is four symbols, and which four depends on alphabetical order and on the coverage filter. The demo run traded only two symbols.
- **Remediation:** Remove the cap, or scan the full universe with a documented performance budget. Report the number of symbols scanned per session.
- **[Status update]** Implemented in **Phase 1** (pulled forward from Phase 3, decision 5). The cap is gone and every eligible symbol is scanned. Correction to the evidence above: `list_universe_symbols()` is sorted only in database mode; in demo mode it follows `sample_data.SYMBOLS`. A performance budget for a real universe is still undefined (see B-24).

**B-13 — Benchmark-relative metrics are absent**
- **Evidence:** `simulator.run_backtest` passes `benchmark_return=None`. No alpha, beta, excess return, or information ratio is computed. TD-M6 records this.
- **Confirmed by run:** `benchmark_return` is `None`.
- **Remediation:** Compute the benchmark series over exactly the backtest range (`benchmark_slice` with start and end). Report total and annualized excess return, beta, and tracking error. Label the benchmark's construction (see B-14).

**B-28 — No data provenance on results**
- **Evidence:** `BacktestRun` has no data-source or synthetic-data field. Demo prices come from `data/sample_data.make_history`, a seeded random walk. The only signal is the frontend notice about survivorship.
- **Confirmed by reading.** The stock API already exposes `is_synthetic`; backtests do not.
- **Remediation:** Add `data_provenance` (synthetic / imported / source name, with import date) and `evidence_grade` to every run. Show both in the UI and API.

**B-29 — No corporate-action adjustment on the backtest price path**
- **Evidence:** `get_history_dataframe` returns raw OHLCV. `load_candles_with_adjusted` and `apply_adjustments` exist in `market_data/adjustments.py` but are not called from the backtest path. The simulator uses `close` only.
- **Confirmed by reading (path); needs verification with real data.** With demo data this is inert.
- **Remediation:** Use an adjusted series for returns and marks, with raw prices kept for cash and fill logic. This depends on M15/M16 data completeness.

### Medium

**B-14 — Benchmark is an equal-weight average of the current survivor universe**
- **Evidence:** `regime/benchmark._build_equal_weight_proxy` averages returns across `list_universe_symbols()`. `NIFTY500_PROXY` is cached into `sample_data.HISTORIES` and appears in the universe list (confirmed by run).
- **Confirmed by run (universe list); Potential (proxy traded).** If `NIFTY500_PROXY` ever enters `syms[:4]`, it can generate a BUY signal on the benchmark itself.
- **Remediation:** Exclude benchmark symbols from the tradable universe. Document the proxy's construction and its survivorship bias.
- **[Status update]** The exclusion was pulled forward from Phase 4 to **Phase 1** and made registry-driven in **Phase 1.1**. Registered benchmarks are never scanned, sampled for breadth, or bought. The proxy no longer writes itself into the stored symbol list or history store. Still open: the proxy remains an equal-weight survivor average; documenting it in results is Phase 4 and the full fix needs historical constituents (M15).

**B-15 — Open positions at the end are not liquidated**
- **Evidence:** `final_marks = _marks(syms, config.end_date)` is computed and never used. Open positions are included in total return but not in trade statistics.
- **Confirmed by run:** ₹9,635.92 invested at the window end, excluded from trades.
- **Remediation:** Add an explicit end-of-backtest policy: liquidate at the last available close with costs (default), or report open positions and exclude them from trade statistics. Show both unrealized and realized P&L.

**B-16 — Sortino, Calmar, and minimum-sample flags are missing**
- **Evidence:** `BacktestMetrics.sortino` is declared but never set. Calmar is not implemented. No minimum trade or window length is enforced.
- **Confirmed by run:** Sortino is `None`. Eight trades were used for a Sharpe of 0.52 with no warning.
- **Remediation:** Implement Sortino and Calmar with defined formulas. Add `sample_adequate` flags and warnings.

**B-18 — CAGR annualizes short windows without a warning**
- **Evidence:** `compute_metrics` annualizes with `years = max(days / 365.25, 0.01)`.
- **Confirmed by run:** 0.39% over 90 days becomes a 1.58% CAGR.
- **Remediation:** Suppress CAGR below a minimum window, or label it clearly as annualized from a short sample.

**B-19 — Sharpe convention is undocumented**
- **Evidence:** Sharpe uses arithmetic mean × 252 over daily equity returns, with a zero risk-free rate and no stated convention. Zero-return days from cash are included.
- **Remediation:** Document the convention; make risk-free rate a parameter; state the number of return observations.

**B-20 — Hold period counts calendar days, not sessions**
- **Evidence:** `timedelta(days=hold_days)`. Config and docs describe hold periods in sessions. Positional default is 60 calendar days.
- **Remediation:** Make hold period sessions-based (count trading dates) and document it.

**B-21 — Pending entries are not checked against position limits and can be dropped silently**
- **Evidence:** Position limit is checked before signal generation, not at fill. Pending entries are processed only when `pe["entry_date"] == session`; a fill dated after `end_date` is never processed and is not counted.
- **Confirmed by reading.**
- **Remediation:** Check `max_positions` and cash at fill. Count pending entries that expire at end-of-range as `unfilled_orders`.

**B-22 — Sensitivity grid varies only `hold_days` and `min_signal_score`**
- **Evidence:** `validation_sensitivity.sensitivity_grid`. TD-H3 and `prd_gap_analysis.md` §8 already record this.
- **Confirmed by reading.** Strategy parameters (breakout lookback, RSI bands, ATR multiples) are not varied.
- **Remediation:** See Phase 5. `HorizonConfig` is a frozen dataclass, so a parameter overlay needs an explicit design.

**B-23 — Sensitivity and walk-forward have no multiple-testing disclosure**
- **Evidence:** Each grid row is a full run. Nothing records the number of configurations tried or reports dispersion.
- **Remediation:** Report the grid size, the dispersion of metrics across the grid, and a warning that the best row is selected in-sample.

**B-24 — Walk-forward and sensitivity runtime**
- **Evidence:** A 90-day, 8-symbol run took 107.7 s. Sensitivity runs 6 full backtests; walk-forward runs one per fold. Each session re-reads every symbol history from the repository, and each signal re-reads all histories for breadth.
- **Confirmed by run (runtime); Confirmed by reading (cause).**
- **Remediation:** Cache history per run, precompute indicators once per symbol, and make breadth incremental. Must not change results (verify with baseline diff).

**B-25 — Cost model is incomplete and unsourced**
- **Evidence:** `execution/costs.py` has STT (sell), stamp duty (buy), exchange charges, and GST. `sebi_per_crore` is defined and never applied. No DP charges. Brokerage is 0 in REALISTIC and 0.1% in CONSERVATIVE. Rates are not cited.
- **Confirmed by reading.**
- **Remediation:** Apply SEBI charges. Source and cite each rate; require user confirmation. This must not be presented as an authoritative fee schedule.

**B-26 — `build_context` benchmark features are computed without an as-of cap**
- **Evidence:** `evaluator.build_context` calls `aligned_relative_returns(df.iloc[:idx+1], as_of_index=-1)` without `as_of_date`.
- **Potential (not leaking today).** The inner join bounds the result, but the reliance is implicit.
- **Remediation:** Pass `as_of_date` explicitly. Add a regression test in `test_regime_point_in_time.py`.

**B-27 — Parallel accounting in `SimBook` duplicates the portfolio's cash and position logic**
- **Evidence:** `backtesting/portfolio.py` implements its own cash, positions, and equity. Sizing and cost formulas are reused from the live modules, but the accounting is not.
- **Architectural risk.** Results can drift from the live book's rules, and Phase 3 cost changes must be made in both places unless shared.
- **Remediation:** Keep `SimBook` isolated (research must never write the live book). Share cost and sizing functions and add a test that asserts the parity of a single fill across both.

**B-30 — No check that data covers the requested end date**
- **Evidence:** `trading_dates` uses only available bars. If data ends before `end_date`, the run ends silently at the last bar.
- **Remediation:** Fail or warn on partial coverage, with the actual last date in `warnings`.

### Low

**B-31 — Unused configuration fields and dead code**
- `BacktestConfig.strategies`, `ownership_policy`, `universe_mode` (only as a label), `max_adv_participation` (see B-07), `CompletedTrade.slippage` and `ownership_delayed_exit` are never set. `final_marks` is unused. `exit_signal_price` is unused.
- **Remediation:** Remove, or wire up in the phases below. Prefer removing dead fields from the public schema only with user approval.

**B-32 — Settlement dates use a business-day approximation**
- TD-M2 already records this. `earliest_sell_date` uses `BDay(settlement_t_plus + 2)`. Not authoritative NSE holidays.
- **Remediation:** Keep, but disclose in every ownership-blocked run. Calendar sourcing belongs to M15/M16.

---

## 6. Confirmed defects vs potential risks vs known limitations

**Confirmed defects (reproduced or proven by reading):** B-01, B-02, B-03, B-04, B-05, B-06, B-07, B-08, B-09, B-11 (reproduced), B-12, B-13 (reproduced), B-15 (reproduced), B-16 (reproduced), B-17, B-18 (reproduced), B-21, B-22, B-24 (runtime reproduced), B-31.

**Potential risks (need verification before treating as defects):**
- B-14: whether the benchmark proxy can be selected as a trade candidate.
- B-26: benchmark feature leakage if the inner-join assumption changes.
- B-29: effect of unadjusted prices on real data (demo is inert).
- B-30: silent end-date truncation with partial real data.
- B-10: whether any backtest currently uses financials with publication dates after the session (cannot be assessed on demo data).

**Known limitations (documented and disclosed; not defects):**
- Daily OHLCV only; intrabar order ambiguity (B-02 sets the rule).
- No partial fills (B-07 defines the rule).
- Settlement approximation (B-32).
- Demo universe and synthetic prices (B-28).
- No authoritative NSE holiday calendar.
- Equity-curve drawdown is end-of-day only, so intraday drawdown is not captured.

---

## 7. Methodology limitations (by audit area)

| Area | Status | Notes |
|---|---|---|
| **A. Look-ahead / leakage** | Partially sound | Signal and fill timing sound (P-01, P-03). Sizing uses next open (B-03). Price window truncation (B-01). Shariah date semantics (B-10). Survivorship selection (B-09). No parameter-selection leakage today because no optimizer exists. |
| **B. Walk-forward** | Not implemented | Blended metrics (B-17). No train/val/test separation. No fold-level parameter freezing. |
| **C. Execution realism** | Not realistic | Stops ignored (B-02). Asymmetric fills (B-06). No ADV (B-07). Missing bars marked at cost (B-08). Partial fills and rejections only for cash and risk. |
| **D. Metrics** | Partially correct | Total return, max DD, win rate, profit factor are computed. Sortino and benchmark metrics missing (B-13, B-16). Cost metric understated (B-04). CAGR and Sharpe on small samples (B-18, B-19). |
| **E. Sensitivity / robustness** | Not implemented | Grid does not vary strategy parameters (B-22). No dispersion or multiple-testing disclosure (B-23). Monte Carlo degenerate (B-11). No regime split, strategy correlation, or strategy attribution. |
| **F. Data / universe integrity** | Not credible | Current-list universe, survivorship filter (B-09), unadjusted prices (B-29), no publication dates (B-10), no membership or delisting data (M15). |

---

## 8. Demo vs credible historical data

These two categories must never be presented as the same thing.

**Demo data (current state):**
- Prices come from `make_history`, a seeded random walk with artificial drift and regime shifts. Results describe the software, not the market.
- The universe is eight synthetic symbols plus a benchmark proxy.
- Any performance number from demo data is a **software test**, not evidence. Only the mechanics (order of operations, accounting, metric formulas) can be validated against it.

**Credible historical research requires all of:**
1. Point-in-time universe membership with listing and delisting dates (M15).
2. Corporate-action-adjusted price series, with raw prices kept for execution (M15/M16).
3. Financial data with publication or filing dates, used only when published before the session (M15/M17).
4. Daily volume for liquidity caps (available in imported data).
5. Sourced and cited cost rates, confirmed by the user.
6. Walk-forward OOS reporting with frozen parameters.
7. Benchmark computed over the backtest range.

Until all seven are satisfied, results must carry `evidence_grade = demo` or `research_sandbox` and must not be described as research-grade. Passing tests do not change this.

---

## 9. Dependencies on M15 and other milestones

| Item | Belongs to | Reason |
|---|---|---|
| Point-in-time membership, listing and delisting dates (full B-09 fix) | **M15** | Requires product-sourced membership files (blocked per roadmap). |
| Corporate-action-adjusted series (B-29) | **M15 / M16** | Requires complete corporate-action data. |
| Financial publication dates (B-10 full fix) | **M15 / M17** | Requires data sources with publication timestamps. |
| Benchmark constituent history (B-14 full fix) | **M15** | Requires historical index constituents. |
| Settlement calendar (B-32) | **M15 / M16** | Requires an authoritative holiday calendar. |
| Cost rate schedule sourcing (B-25) | **User** | Rates must be confirmed; not an engineering decision. |

**Within M14:** B-01, B-02, B-03, B-04, B-06, B-07, B-08, B-09 (surfacing only), B-12, B-13, B-15, B-16, B-17, B-18, B-21, B-22, B-24, B-27, B-28, B-30, B-31.

Items that cannot be fully fixed in M14 are disclosed in the phase plan, not claimed as resolved.

---

## 10. Proposed M14 phases

Each phase depends on the previous one unless noted. Expected numeric results will change after Phases 1 to 3. Before Phase 1, capture a **frozen baseline** (config, seed, output JSON) of the demo runs so every change can be diffed and attributed.

### Phase 1 — Critical leakage and integrity fixes

- **[Status update]** Actual delivered scope also includes B-12 (from Phase 3) and the benchmark-exclusion part of B-14 (from Phase 4); see the Implementation status section. The original scope line follows unchanged.
- **Scope:** B-01 (as-of data reads and coverage check), B-03 (size at signal, re-validate at fill), B-02 (daily stop and target enforcement with stop-first rule), B-08 (stale-mark policy with count), B-09 surfacing (record excluded symbols), B-30 (coverage warnings), B-28 (provenance fields).
- **Files:** `market_data/repository.py` (add an optional as-of bound; default behaviour unchanged), `backtesting/data.py`, `backtesting/simulator.py`, `backtesting/execution.py`, `backtesting/universe.py`, `backtesting/schemas.py` (new optional fields only), `regime/market_breadth.py` (as-of-aware loader).
- **Tests:** New `tests/test_backtest_leakage_m14.py`: synthetic 800-bar history with a backtest over its last 200 bars; a session older than the 520-bar window produces signals; sizing invariant to the next open; stop triggers exit; stop-first rule when both levels are hit; excluded symbols appear in warnings; partial coverage warns.
- **Acceptance:** All new tests pass; existing `test_backtesting.py`, `test_integration_m9.py`, `test_regime_point_in_time.py` pass (any numeric change explained against the frozen baseline).
- **Dependencies:** None.
- **Risks:** Results change materially. Breadth and regime for older sessions will now be populated, changing signals. Requires the as-of loader to be correct in both DB and in-memory paths.

### Phase 2 — Walk-forward hardening

- **Scope:** B-17. Replace the blended walk-forward with explicit train, validation, and test segments. Each segment is a separate simulation over its own date range, with frozen parameters. Report segment metrics separately; no headline blending; OOS metrics only from test-window trades.
- **Files:** `backtesting/walk_forward.py`, `backtesting/schemas.py` (segment result model), `api/v1/backtests.py` (response shape; see Section 13).
- **Tests:** Trades entered in the training window never count toward test metrics; test segment only trades inside its window; validation segment never influences test parameters; changing test-window data does not change train metrics.
- **Acceptance:** Walk-forward API returns per-segment metrics and a `oos_metrics` block containing test-window trades only; the notice is corrected.
- **Dependencies:** Phase 1 (as-of loading).
- **Risks:** Response shape change; frontend (Phase 6) must follow.

### Phase 3 — Execution realism and costs

- **Scope:** B-04 (buy costs into trade P&L and cost metric), B-05 (cost-scenario default decision; visible label), B-06 (symmetric exit fill convention), B-07 (ADV cap with `liquidity_rejections`), B-15 (end-of-backtest policy), B-21 (fill-time limit checks, expiry counting), B-25 (SEBI charges; rate source documented), B-12 (remove the four-symbol cap, or document a budget; **[Status update] cap removed in Phase 1, budget still to document**), B-27 (shared cost and sizing functions, parity test).
- **Files:** `backtesting/simulator.py`, `backtesting/costs.py`, `backtesting/portfolio.py`, `backtesting/execution.py`, `execution/costs.py` (SEBI application only, if agreed), `backtesting/schemas.py`.
- **Tests:** Reconciliation `sum(net_pnl) == final − initial` when all positions are closed; cost metric equals sum of buy and sell costs; ADV cap rejects oversized orders; exit fill convention matches entry convention; parity test between `SimBook` and live sizing for a single fill.
- **Acceptance:** Reconciliation test passes; cost scenario is shown on every result; no silent cost-free default without the label.
- **Dependencies:** Phase 1. Rate sourcing requires user input.
- **Risks:** Changing the default cost scenario changes every headline number. Removing the symbol cap increases runtime (addressed in Phase 5 / B-24).

### Phase 4 — Metrics and benchmark comparison

- **Scope:** B-13 (benchmark series over backtest range; excess return, beta, tracking error, information ratio), B-16 (Sortino, Calmar, sample flags), B-18 (short-window CAGR rule), B-19 (documented Sharpe convention and risk-free parameter), B-20 (sessions-based hold period), B-11 (Monte Carlo replacement: bootstrap or block bootstrap with CAGR and max-DD distributions), B-14 (exclude benchmark from tradable universe, document proxy; **[Status update] exclusion done in Phase 1 and Phase 1.1, proxy documentation remains**), B-31 (dead-field cleanup, with approval).
- **Files:** `backtesting/metrics.py`, `backtesting/monte_carlo.py`, `backtesting/simulator.py`, `backtesting/schemas.py`, `regime/benchmark.py` (documentation and exclusion only).
- **Tests:** Hand-computed fixtures for each metric (including zero denominators, single trade, all-winning, all-losing, flat equity); benchmark alignment test over the exact backtest range; Monte Carlo returns a non-degenerate distribution for a known trade set and is seed-reproducible.
- **Acceptance:** Every metric in `BacktestMetrics` is either computed with a documented formula or explicitly `None` with a reason.
- **Dependencies:** Phase 3 (net P&L must be correct first).
- **Risks:** Benchmark is a survivor proxy, so alpha is biased. Must be disclosed in the result (B-14).

### Phase 5 — Sensitivity and robustness

- **Scope:** B-22 (strategy parameter overlay on `HorizonConfig` via explicit passing, without mutating the registry), B-23 (grid size, dispersion, in-sample selection warning), regime-split reporting, strategy attribution (per-strategy trade counts and P&L), cost and slippage sensitivity, B-24 (history caching and precomputed indicators; results must be identical to the baseline).
- **Files:** `backtesting/validation_sensitivity.py`, `strategies/config.py` (overlay mechanism; frozen dataclass left intact), `strategies/evaluator.py` (parameter pass-through), `backtesting/simulator.py` (caching).
- **Tests:** Changing breakout lookback changes trade count (per roadmap acceptance); grid results are identical to individual runs; caching produces byte-identical results to the uncached baseline.
- **Acceptance:** Sensitivity varies strategy parameters, not only exit timing; dispersion is reported; caching gives identical outputs.
- **Dependencies:** Phases 1 to 3.
- **Risks:** Overlay touches strategy code; must not change default parameter values. Grid results are in-sample unless used with Phase 2 segments.

### Phase 6 — Frontend reporting and documentation

- **Scope:** Show evidence grade and data provenance; show cost scenario; show segment metrics (train/val/test) separately; show warnings and excluded-symbol lists; show the benchmark and its construction; remove the claim that a headline number is research-grade. Update `docs/architecture/backtesting.md`, `docs/technical_debt.md` (TD-H3, TD-H4, TD-H6, TD-M5, TD-M6 status), `docs/prd_gap_analysis.md` §8, and `docs/implementation_roadmap.md`.
- **Files:** `frontend/src/pages/BacktestingLab.jsx`, `frontend/src/lib/api.js`, `docs/*`.
- **Tests:** Vitest for the evidence-grade banner and segment rendering; `npm run build` on Node 22.
- **Acceptance:** Every result screen shows evidence grade, provenance, and cost scenario; no segment is presented as OOS unless it is test-window only.
- **Dependencies:** Phases 2, 3, 4.

---

## 11. Overall acceptance criteria for M14

A backtest result may be labelled **research-grade** only when all of the following hold:

1. No silent truncation: the requested range is fully covered or the run fails or warns (B-01, B-30).
2. Stops and targets are enforced with a documented intrabar rule (B-02).
3. No future information is used in sizing or fills (B-03).
4. Net P&L reconciles to equity change (B-04).
5. Costs are on by default or the result is labelled cost-free; the cost scenario is shown (B-05).
6. Entry and exit fill conventions are symmetric; liquidity is capped (B-06, B-07).
7. Missing prices are stale-flagged, not silently marked at cost (B-08).
8. Survivorship is handled with point-in-time membership, or the result is labelled survivor-biased (B-09, M15).
9. Shariah STRICT uses publication-dated financial inputs, or the result is labelled (B-10, M15/M17).
10. Walk-forward reports OOS from test-window trades only (B-17).
11. Sensitivity varies strategy parameters and reports dispersion (B-22, B-23).
12. Benchmark-relative metrics are computed over the backtest range (B-13).
13. Monte Carlo is non-degenerate (B-11).
14. Data provenance and evidence grade are shown on every result (B-28).

Until then, the label is **research sandbox**.

---

## 12. Test plan

**Preserve (must keep passing without modification of expectations unless explicitly updated with a documented reason):**
- `tests/test_backtesting.py`
- `tests/test_integration_m9.py` (`test_sensitivity_changes_hold_days`, `test_backtest_can_exit_after_authorization`)
- `tests/test_regime_point_in_time.py`
- `tests/test_strategies.py`
- `tests/test_valuation_m13.py` and M12 tests (regression for portfolio isolation)

**New (per phase):**
- `tests/test_backtest_leakage_m14.py` (Phase 1): window coverage; sizing invariance; stop enforcement; stop-first rule; excluded-symbol warnings; partial-coverage warning.
- `tests/test_walk_forward_m14.py` (Phase 2): segment isolation; OOS-only test trades; no parameter leakage; no blended headline.
- `tests/test_backtest_execution_m14.py` (Phase 3): cost reconciliation; ADV cap; symmetric fills; end-of-backtest policy; fill-time limits; `SimBook`/live sizing parity.
- `tests/test_backtest_metrics_m14.py` (Phase 4): hand-computed metric fixtures including zero denominators and small samples; benchmark alignment; Monte Carlo distribution and seed reproducibility.
- `tests/test_sensitivity_m14.py` (Phase 5): parameter overlay changes trade count; grid equals individual runs; caching is byte-identical to the baseline.
- Frontend Vitest (Phase 6): evidence-grade banner; segment rendering.

**Baseline:** A frozen demo-run JSON (config, seed, metrics, trades) is stored before Phase 1. Every subsequent phase must diff against it and explain each change.

**Regression rule:** No test may be weakened to pass. If an expected number changes because a defect is fixed, update the expectation with a reference to the finding ID.

---

## 13. Decisions needed from the user

1. **Default cost scenario (B-05):** Change the default from ZERO to REALISTIC, or keep ZERO and label every result as cost-free?
2. **Intrabar stop and target rule (B-02):** When both levels are inside one daily bar, assume the stop is hit first (conservative), or use another convention?
3. **Walk-forward API shape (B-17):** Replace the existing response shape (breaking change, frontend follows), or add a new endpoint and deprecate the old one?
4. **Cost rate sourcing (B-25):** Confirm the rate set to use (including SEBI charges and DP charges) and the source you want cited.
5. **Symbol cap (B-12):** Remove the four-symbol cap now (runtime increases until Phase 5 caching), or keep it until caching is in place? **[Resolved: removed in Phase 1.]**
6. **Demo results (B-28):** Should existing demo runs be marked `demo` in storage, or only labelled in the UI? **[Resolved: marked `demo` in storage, API and UI.]**

Decisions 1 to 4 as approved: REALISTIC default deferred to Phase 3 (not yet changed); stop-first on a bar that hits both (done); v2 walk-forward endpoint (Phase 2, not started); versioned, sourced cost profile (Phase 3, not started).

---

## 14. Verification commands (for the user to run; not executed)

These are read-only, use an empty `DATABASE_URL` so no database is touched, and are safe to run in any terminal from `backend/`.

**Check B-01 (how many bars the loader actually returns vs the date range):**
```
DATABASE_URL= .venv/bin/python -c "from app.market_data.repository import get_history_dataframe as g; df=g('TCS', limit=5000); print(len(df), df.date.min(), df.date.max())"
```
Expect: about 520 rows for demo data. With real multi-year data, anything above 520 means sessions before the window are dropped.

**Check B-04 and B-15 (net P&L reconciliation and open positions at end):**
```
DATABASE_URL= .venv/bin/python -c "from datetime import date,timedelta; from app.backtesting.schemas import BacktestConfig,ShariahBacktestMode,CostScenario; from app.backtesting.simulator import run_backtest; e=date.today()-timedelta(days=10); x=run_backtest(BacktestConfig(name='a',start_date=e-timedelta(days=90),end_date=e,shariah_mode=ShariahBacktestMode.RESEARCH_ONLY,cost_scenario=CostScenario.REALISTIC,max_positions=3)); print('sum_net_pnl',sum(t.net_pnl for t in x.trades),'final_minus_initial',x.metrics.final_capital-x.metrics.initial_capital,'sum_trade_costs',sum(t.costs for t in x.trades),'open_invested_end',x.equity_curve[-1].invested)"
```
Expect: if `open_invested_end` is zero, `sum_net_pnl` should equal `final_minus_initial`. Per B-04, `sum_net_pnl` will instead be higher than `final_minus_initial` by the total buy-side costs. If `open_invested_end` is non-zero, the gap also includes unrealized P&L on open positions (B-15), so the comparison is only clean with no open positions at the end.

**Check B-11 (Monte Carlo degeneracy):** rerun with the same trades; p5, p50, and p95 will be identical (already observed).

---

## Appendix A — Methodology notes

- All "Confirmed by reading" findings should receive a failing regression test in Phase 1 before any fix is written. This proves the defect and prevents a silent fix that changes results without a test trail.
- Demo results from the run in Section 2 are included only to show what the mechanics produce. They are not performance claims.
- No strategy was tuned or selected in this audit.
