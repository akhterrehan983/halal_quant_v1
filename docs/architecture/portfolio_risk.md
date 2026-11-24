# Portfolio & Risk Engine (Milestone 5)

Converts M4 **research signals** into **allocation proposals**. No broker execution, no automatic liquidation, no shorting or margin.

---

## Architecture

```text
app/portfolio/     manager, allocator, position_sizing, exposure, cash, store, …
app/risk/          limits, stop_loss, liquidity, drawdown, validation, manager, …
```

- **Research book** (`/api/v1/portfolio/*`) — Decimal ledger, sleeves, proposals.
- **Legacy paper** (`/api/portfolio/*`) — unchanged in-memory buys/sells on Overview.

---

## Sleeves

| Sleeve | Default capital % | Typical horizon |
|--------|------------------:|-----------------|
| Swing | 40% | 2–15 sessions |
| Positional | 40% | 15–120 sessions |
| Cash reserve | 20% | Unallocated |

`RiskConfiguration.validate_allocations()` ensures swing + positional + reserve ≤ 100%.

---

## Position sizing

```text
risk_amount = sleeve_equity × risk_per_trade_pct
risk_per_share = entry − stop   (long-only, stop < entry)
quantity = floor(min(risk_amount/risk_per_share, cash/entry, exposure caps))
```

Whole shares only; zero quantity → explicit rejections (no upward rounding).

Default risk per trade: swing 0.75%, positional 0.5% (configurable, not optimized).

---

## Stops

Priority: signal stop → ATR (2×ATR14) → structure (recent swing low). Trailing stops never move down for longs. Missing data → no fabricated stop → proposal rejected.

---

## Risk validation

Independent `risk/validation.py` checks: drawdown lock, duplicate holding, stock/sector caps, open-risk cap, ADV participation, missing liquidity data (conservative reject).

High signal scores **do not** bypass validation.

---

## Drawdown

Peak portfolio value tracked on each summary. If drawdown ≥ `max_drawdown_pct` (default 15%), `drawdown_locked` blocks new proposals; existing holdings untouched.

---

## Persistence

- Demo: JSON `BookState` in memory (`portfolio/store.py`).
- PostgreSQL: `portfolio_books.state_json` + auxiliary tables for proposals/events/config.
- Migration: `0e419f811f08_milestone5_portfolio_risk`.

---

## Known limitations

- Holdings in the research book start empty (M6 paper execution will bridge proposals → fills).
- Sector map covers demo symbols only; others = `UNCLASSIFIED` with tighter cap.
- Session-based expiry from M4 is separate from portfolio risk.
- Correlation interface warnings only; no optimizer.
- Rebalancing outputs **proposals**, not trades.