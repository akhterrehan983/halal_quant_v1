# Historical Backtesting (Milestone 7)

Event-driven **research** backtests — not proof of future profitability.

---

## Architecture

`app/backtesting/` orchestrates:
- **data** — as-of slices, trading dates
- **universe** — current demo symbols + survivorship warning
- **simulator** — daily session loop
- **compliance** — point-in-time Shariah snapshots (`STRICT` vs `RESEARCH_ONLY`)
- **execution** — next-session open fills (reuses M6 rules)
- **metrics**, **walk_forward**, **monte_carlo**, **validation**

Reuses M3 `generate_unified_signal`, M5 position sizing, M6 costs — no duplicate formulas.

---

## Event sequence (per session)

1. Mark portfolio at session close  
2. Process pending entries (fills on their entry date)  
3. Time-based exits with ownership sell-authorization delay  
4. Generate signals (as-of index) → Shariah → size → queue next-session entry  

No fill on signal close.

---

## Look-ahead controls

- `slice_as_of` / `index_as_of` on OHLCV  
- Unified signals: `evaluation_date()` caps benchmark (`benchmark_slice(as_of_date=)`) and breadth (`compute_universe_breadth(as_of_date=)`) to the stock evaluation bar (M11)  
- Shariah: snapshots with `screening_date <= session` only  

---

## Known limitations

- Survivorship: uses today's universe list  
- No authoritative NSE holiday calendar for settlement  
- Daily OHLCV limit-order priority ambiguous  
- Corporate actions: inherited from M2 adjusters when data present — else warned  
- Long backtests are CPU-heavy (cap 4 symbols/session in demo engine)  
- Walk-forward / sensitivity are framework stubs expanding per window  

---

## Persistence

`backtest_runs` table (JSON payload) or in-memory demo store.