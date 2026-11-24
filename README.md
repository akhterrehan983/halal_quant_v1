# Halal Quant V1 — Swing & Positional Research Prototype

A local full-stack starter application with a FastAPI backend and React/Vite dashboard. It implements six explainable, rule-based strategy families over daily OHLCV data and includes a basic in-memory paper portfolio.

> **Important:** The included market series are synthetic demo data. They are not NSE quotes. Shariah status is unverified. Strategy outputs are educational research signals, not investment advice. Paper trades do not establish ownership or possession. No broker connection or live order execution is included.

## Features

- Swing and positional profiles (configurable lookbacks/holding horizon).
- Relative momentum, breakout, pullback, mean reversion, trend following and 52-week-high momentum.
- EMA20, EMA50, SMA200, RSI14, ATR14, ADX14, Bollinger Bands, relative volume and multi-period returns.
- Benchmark market regime classifier (M4) with historical as-of support.
- Unified signal engine: strategy consensus, transparent 0–100 scoring, lifecycle persistence.
- Per-stock legacy signal scores, entry reference, ATR stop and illustrative target.
- Universe scan and stock detail dashboard.
- In-memory virtual buy/sell portfolio.
- OHLCV CSV upload endpoint.

## Folder structure

```text
halal_quant_v1/
├── backend/
│   ├── app/
│   │   ├── core/                 # configuration
│   │   ├── data/                 # synthetic demo universe
│   │   ├── strategies/           # indicators and strategy rules
│   │   ├── portfolio/            # paper portfolio service
│   │   ├── api/                  # API package (routes currently in main.py)
│   │   └── main.py               # FastAPI endpoints
│   ├── tests/
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── components/           # layout, common, charts
│   │   ├── pages/                # Overview, Market Data, Signal Center, …
│   │   ├── context/AppContext.jsx
│   │   ├── lib/api.js            # backend client
│   │   ├── App.jsx               # shell + view router
│   │   ├── main.jsx
│   │   └── style.css
│   ├── package.json
│   └── vite.config.js
├── data/                         # place local CSV files here
├── README.md
└── .gitignore
```

## Requirements

- Python 3.12+ recommended
- Node.js **20.19+** (see `frontend/.nvmrc`) and npm
- Optional: Docker for local PostgreSQL persistence

## Run on Ubuntu/Linux

### Optional: PostgreSQL (Milestone 1+ persistence)

```bash
cd halal_quant_v1
cp .env.example .env          # uncomment DATABASE_URL (match docker-compose postgres service)
docker compose up -d postgres
cd backend && source .venv/bin/activate
alembic upgrade head          # reads DATABASE_URL from root .env (same as FastAPI)
python -m scripts.seed_demo_to_db   # optional: synthetic OHLCV into ohlcv_candles
python -m scripts.verify_postgres_setup   # connectivity, tables, portfolio/execution persist + reload
```

FastAPI and Alembic both load `../.env` from the project root (`backend/app/core/config.py`, `migrations/env.py`).

**Health:** `GET /api/v1/health` → `database_enabled: true` when `DATABASE_URL` is set.

Without `DATABASE_URL`, the API runs in **demo mode** (in-memory synthetic data; state resets on restart).

**Known limits (PostgreSQL mode):** portfolio book and execution overlay are separate JSON rows (`portfolio_books`, `execution_state`); fills are not one cross-store DB transaction. Legacy `paper_portfolios` / `paper_trades` tables exist but M12 uses `portfolio_books` only. Rebalance proposals live in book JSON; `rebalance_proposals` table is largely unused. Market reads fall back to in-memory demo if `ohlcv_candles` is empty until you seed or import CSV.

### 1. Backend

```bash
cd halal_quant_v1/backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

API docs: http://localhost:8000/docs  
Legacy health: http://localhost:8000/api/health  
Versioned health: http://localhost:8000/api/v1/health  

Architecture audit: `docs/architecture/current_state.md`  
Market data: `docs/architecture/market_data.md` · CSV format: `docs/csv_import_format.md`  
Progress: `docs/progress.md`

### CSV historical data (Milestone 2)

```bash
# Validate only
curl -F "file=@TCS.csv" http://localhost:8000/api/v1/market-data/validate

# Import with idempotent skip (PostgreSQL required for persistence)
curl -F "file=@TCS.csv" "http://localhost:8000/api/v1/market-data/import/csv?conflict_policy=skip"
```

With `DATABASE_URL` set, imported data survives restarts. Without it, imports land in the in-memory demo universe only.

Strategy architecture: `docs/architecture/strategies.md` — explorer in dashboard sidebar **Strategy explorer**.  
Signal engine: `docs/architecture/signal_engine.md` — **Signal center** in the dashboard sidebar.  
Portfolio & risk: `docs/architecture/portfolio_risk.md` — **Portfolio** and **Risk dashboard** workspaces.  
Shariah & paper execution: `docs/architecture/shariah_execution.md` — **Shariah compliance** and **Paper trading** workspaces.  
Backtesting: `docs/architecture/backtesting.md` — **Backtesting lab**.  
Frontend architecture (M8): `docs/architecture/frontend.md`.  
M9 audit & integrity: `docs/architecture/system_audit.md`, `docs/architecture/financial_integrity.md`, `docs/operations/runbook.md`.

### 2. Frontend (new terminal)

```bash
cd halal_quant_v1/frontend
nvm use    # reads .nvmrc
npm install
npm run dev
npm run test    # Vitest (format + navigation)
npm run build   # production bundle
```

Open http://localhost:5173

## API endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/api/health` | Health check |
| GET | `/api/universe` | Demo stock universe |
| GET | `/api/history/{symbol}` | Daily OHLCV history |
| GET | `/api/signals/{symbol}?horizon=swing` | Evaluate all strategies for one stock |
| GET | `/api/scan?horizon=positional` | Rank demo universe |
| GET | `/api/portfolio` | Paper portfolio snapshot |
| POST | `/api/portfolio/buy` | Virtual buy `{ "symbol":"TCS", "quantity":2, "price":100 }` |
| POST | `/api/portfolio/sell` | Virtual sell (only shares held in virtual portfolio) |
| POST | `/api/data/upload` | Upload OHLCV CSV; filename stem becomes symbol |

CSV required columns (case-insensitive): `date,open,high,low,close,volume`. Use at least 60 daily rows. Uploads are kept in memory and reset when the backend restarts.

## Strategy logic (initial hypotheses, not validated trading rules)

- **Relative Momentum:** positive 3M and 6M returns with price above EMA50; score blends 3M/6M performance.
- **Breakout:** close above previous 20-day high for swing or 55-day high for positional, relative volume >= 1.2x and close above EMA50.
- **Pullback:** longer trend positive, intraday low touches near EMA20, close recovers above EMA20 and RSI in a defined band.
- **Mean Reversion:** close below lower Bollinger band and RSI below 35; trend context is reported.
- **Trend Following:** price above SMA200, EMA20 above EMA50 and ADX >= 18.
- **52-Week High Momentum:** price near 52-week high, positive 3M return and above EMA50.

The scoring thresholds and rules are deliberately transparent and must be calibrated with point-in-time historical data, realistic costs, slippage, walk-forward validation and out-of-sample testing before any live use. Milestone 4 adds a benchmark-based regime module (`/api/v1/regime`); legacy stock detail still exposes a simple per-symbol trend label for compatibility.

## Current limitations / next engineering steps

1. Synthetic data is generated on startup; connect a licensed/authorized NSE data source before research conclusions.
2. Paper portfolio and uploaded symbols are in-memory; persist to PostgreSQL next.
3. No point-in-time Shariah screening provider is connected. All demo symbols show `UNVERIFIED`.
4. No automated ownership/possession determination; do not use the paper portfolio as a Shariah ruling.
5. The initial score is heuristic, not a calibrated probability of success.
6. Execution uses a manually entered price and does not simulate realistic order-book fills, slippage, taxes or exchange charges.
7. Stops and targets are reference levels; no background order/exit simulator is running.
8. No automated broker integration, intraday trading or short selling.

## Tests

```bash
cd backend
source .venv/bin/activate
pip install pytest
pytest -q
```
