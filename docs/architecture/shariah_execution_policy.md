# Shariah & Execution Policy (Enforced Server-Side)

## Screening

- Missing financial or activity data → `INSUFFICIENT_DATA` / `NEEDS_REVIEW`, never silent `COMPLIANT`.
- User-supplied fixtures must declare `data_source`; demo standards are templates, not certification.
- Orders call `eligibility_for_order()` at creation; rejected orders never reserve cash.

## Ownership FSM (conservative delivery)

States progress: `NOT_OWNED` → `ORDER_PENDING` → `EXECUTED_UNSETTLED` → `SETTLED_PENDING_VERIFICATION` → `OWNERSHIP_VERIFIED` → `POSSESSION_VERIFIED` → `SELL_AUTHORIZED`.

- Settlement does **not** imply sell permission.
- `SELL_AUTHORIZED` sets `authorized_sell_qty` to current holding quantity at verification time.
- `evaluate_sell()` requires `SELL_AUTHORIZED`, sufficient sellable quantity, and quantity ≤ `authorized_sell_qty`.
- SELL order creation increments `reserved_for_sell` to prevent double-submission.

## Paper trading

- All fills are simulated; no broker integration.
- Ownership evidence is user/API supplied — not demat verification.
- Frontend cannot bypass `evaluate_sell` or screening gates; rejected payloads return server `rejections`.

## Backtesting Shariah modes

- `STRICT` — uses point-in-time snapshots when present; rejects when missing.
- `RESEARCH_ONLY` — admits entries for methodology tests; must not be presented as halal validation.