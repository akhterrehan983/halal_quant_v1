# Halal Quant V1 — Frontend Architecture (Milestone 8)

## Application shell

- **`AppProvider`** (`src/context/AppContext.jsx`) — shared navigation view, symbol, horizon, legacy scan/portfolio data, health, theme.
- **`MainLayout`** — grouped **Sidebar**, **Header** (page title, API status, Demo/PostgreSQL chip, theme toggle, refresh), scrollable main content, footer.
- **No React Router** — view switching via `view` state (keeps M1–M7 deployment simple).

## Navigation groups

| Group | Views |
|-------|--------|
| Research | Overview, Market Data, Strategy Explorer, Signal Center |
| Portfolio | Portfolio, Risk Dashboard, Paper Trading |
| Compliance | Shariah Compliance |
| Analytics | Backtesting Lab |
| System | Settings |

## Pages

Each major workspace lives under `src/pages/` with local state for view-specific API calls. Shared selections (`symbol`, `horizon`) come from context where needed.

| Page | Primary APIs |
|------|----------------|
| Overview | Legacy scan/signals/portfolio + regime, book summary, active unified signals |
| Market Data | CSV validate/import, quality, candles, import history |
| Strategy Explorer | `/api/v1/strategies`, evaluate, toggle |
| Signal Center | Regime, unified signals, generate, detail |
| Portfolio | Book summary, holdings, proposals, allocate |
| Risk Dashboard | Limits, exposure, events, drawdown from book |
| Shariah Compliance | Standards, screening, evaluate, snapshots |
| Paper Trading | Orders, approve/simulate, settlements, holdings |
| Backtesting Lab | Create backtest, metrics, equity curve, validation |
| Settings | Risk config PATCH, strategy enable toggles |

## Shared components

- **Common:** `MetricCard`, `StatusBadge`, `LoadingState`, `EmptyState`, `ErrorState`, `PageHeader`
- **Charts:** `EquityCurve` (Recharts); overview price chart remains inline.
- **Utils:** `src/utils/format.js` — INR `money`, `pct`

## API client

Single module `src/lib/api.js` (legacy + v1). Milestone 8 added `riskConfig` / `patchRiskConfig`. Mutations refresh page-local lists after success.

## State & UX patterns

- **Loading:** skeleton text via `LoadingState` / inline “Loading…”
- **Errors:** `ShellError` banner with retry on several pages; mutations surface server `detail` in page messages
- **Empty:** tables use muted row; holdings use `EmptyState` styling
- **Auth safety:** SELL and ownership flows only through execution APIs (no UI bypass)

## Theming

`data-theme` on `documentElement` (`light` | `dark`), persisted in `localStorage` key `hq-theme`. Dark mode adjusts surfaces and grid strokes; hero retains brand gradient.

## Testing

```bash
cd frontend && npm run test
```

Vitest: `format.test.js`, `navigation.test.jsx` (sidebar title map).

## Known limitations

- No client-side router deep links; refresh returns to default Overview.
- Large JSON debug panels on several research pages (intentional for M8 transparency).
- Walk-forward / Monte Carlo / sensitivity UIs show backend payloads when run; not all analytics panels are fully visualized.
- Legacy Overview paper trade remains separate from v1 paper execution book.