# Shariah Compliance & Paper Execution (Milestone 6)

Educational simulation only. **Not** investment advice, **not** a Shariah ruling, **not** exchange execution.

---

## Screening standards

Built-in **config templates** (`aaoifi_demo_v1`, `ftse_shariah_demo_v1`) — thresholds are configurable placeholders requiring user/Shariah board approval before any production use.

Profiles (`default`, user-defined) select standards and combine via:
- `PRIMARY` (default)
- `ALL_STANDARDS`
- `ANY_STANDARD`

---

## Financial ratios (user-supplied inputs)

| Ratio | Numerator / denominator |
|-------|-------------------------|
| Interest-bearing debt | debt ÷ market cap (or total assets) |
| Non-compliant income | non-compliant income ÷ revenue |
| Cash + receivables (AAOIFI template) | (cash + receivables) ÷ market cap |

Missing inputs → `UNKNOWN` / `INSUFFICIENT_DATA` — never treated as pass.

---

## Business activity

Classifications must be submitted via API (source + verification date). Unknown → blocks new BUY orders.

---

## Historical snapshots

Each `POST …/evaluate` appends an immutable snapshot (demo memory + `shariah_snapshots` table in PostgreSQL).

---

## Ownership & possession (conservative_delivery)

State machine ending in `SELL_AUTHORIZED` only after manual `POST /execution/ownership/{id}/verify` steps:
`SETTLED_PENDING_VERIFICATION` → `OWNERSHIP_VERIFIED` → `POSSESSION_VERIFIED` → `SELL_AUTHORIZED`.

**SELL orders are rejected** unless state is `SELL_AUTHORIZED`.

Settlement completion alone does **not** grant sell rights.

---

## Execution matching

- **Market:** next session **open** after signal date (+ configurable slippage bps); no fill on signal close bar.
- **Limit BUY:** next session open ≤ limit, or low touches limit (daily-bar approximation documented).

Costs: `zero_cost_demo` default; optional Indian charge template in `execution/costs.py`.

Settlement: T+1 business-day approximation via pandas `BDay`.

---

## Integration

- BUY requires M5 **allocation proposal** + risk re-validation + current **COMPLIANT** screening.
- Cash reserved on valid order create; released on cancel/reject.
- Fills update M5 sleeve cash and holdings; execution holdings track ownership state separately.

---

## Known limitations

- No licensed fundamental data feed.
- Daily OHLCV cannot model intraday queue priority.
- Manual ownership verification API — not demat integration.
- Purification is display-only.
- Partial fills minimal in M6.