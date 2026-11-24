# Halal Quant V1 — Current State Audit

**Last updated:** 2026-11-20 (post Milestone 9)  
**Repository path:** `halal_quant_v1`

---

## Milestone 4 snapshot (current)

| Area | Status |
|------|--------|
| PostgreSQL + Alembic | Optional via `DATABASE_URL`; migrations through `86bcb02a62c5_milestone4_signals` |
| Market data | CSV ingest, repository, features (`docs/architecture/market_data.md`) |
| Strategies | Six modular strategies + registry (`docs/architecture/strategies.md`) |
| Regime | `app/regime/` benchmark classifier, `/api/v1/regime/*` |
| Signals | `app/signals/` unified engine, lifecycle, persistence, `/api/v1/signals/*` |
| Portfolio & risk | `app/portfolio/` + `app/risk/`, allocation proposals, `/api/v1/portfolio/*`, `/api/v1/risk/*` |
| Frontend | M8 research shell: Overview, Market data, Strategy explorer, Signal center, **Portfolio**, **Risk dashboard**, Shariah, Paper trading, Backtesting lab, **Settings** (`docs/architecture/frontend.md`) |
| Legacy API | `/api/*` + `evaluate_all()` + in-memory paper trades preserved |
| Shariah & execution | Screening (user data), paper orders, settlement, ownership FSM |
| Backtesting | Event-driven simulator, APIs, Backtesting lab |
| M9 reliability | Optimistic portfolio locking, sell qty authorization, backtest exit fix |
| Not in scope | Licensed point-in-time universe/regime, intraday fills, live broker, public auth |

See `docs/architecture/signal_engine.md` for methodology and known limitations.

---

## 1. Executive summary (original M1 audit — partially superseded)

The repository began as a **v0.1.0 prototype** with in-memory synthetic OHLCV. **Milestones 1–4** added versioned APIs, optional Postgres, market data infrastructure, modular strategies, benchmark regime classification, and a unified research signal engine.

**Refactor principle:** Preserve existing `/api/*` endpoints and frontend overview behavior while extending `/api/v1` and optional persistence.

---

## 2. Repository layout (as found)

```text
halal_quant_v1/
├── backend/
│   ├── app/
│   │   ├── main.py              # All HTTP routes (monolith)
│   │   ├── core/config.py       # Static Pydantic model
│   │   ├── api/                 # Empty package
│   │   ├── data/sample_data.py  # Synthetic universe + HISTORIES
│   │   ├── portfolio/service.py # In-memory paper portfolio
│   │   └── strategies/
│   │       ├── engine.py        # Six strategies + simple regime
│   │       └── indicators.py    # Technical features
│   └── tests/test_engine.py     # One unit test
├── frontend/                    # Single App.jsx dashboard
├── data/                        # Placeholder for CSV files (minimal)
└── README.md
```

**Missing vs target architecture:** `universe/`, `market_data/`, `features/`, `regime/`, `signals/`, `risk/`, `shariah/`, `execution/`, `backtesting/`, `reporting/`, `models/`, `migrations/`, `configs/`, `docs/`, `docker-compose.yml`, versioned API routers, frontend pages/router.

---

## 3. Backend implementation

### 3.1 Entry point and middleware

- **FastAPI** app in `app/main.py` with title/version from settings.
- **CORS** limited to `http://localhost:5173`.
- No structured logging, auth, rate limits, or request IDs.

### 3.2 Configuration (`app/core/config.py`)

| Field | Default | Notes |
|--------|---------|--------|
| `app_name` | Halal Quant API | Used in OpenAPI |
| `version` | 0.1.0 | |
| `cors_origins` | localhost:5173 | |
| `starting_cash` | 100,000 | **Not wired** — `PaperPortfolio()` hardcodes 100,000 |

No environment variables or secrets management.

### 3.3 Data layer (`app/data/sample_data.py`)

- **8 demo symbols:** TCS, INFY, RELIANCE, HDFCBANK, SUNPHARMA, TATAMOTORS, BEL, COALINDIA.
- **`make_history(symbol, periods=520)`:** Deterministic RNG from symbol name; business-day OHLCV with regime shifts.
- **Global mutable state:** `HISTORIES`, `SYMBOLS` at import time.
- **CSV upload** merges into `HISTORIES` (max 3000 rows, min 60 rows); symbol from filename stem.
- Labeled **synthetic demo data** in API responses — not NSE data.

### 3.4 Indicators (`app/strategies/indicators.py`)

Computed on pandas DataFrames (no look-ahead in rolling windows):

- EMA 20/50, SMA 200, Bollinger, RSI 14, ATR 14, ADX 14
- Volume SMA, relative volume
- Returns 1M/3M/6M/12M
- 52-week high/low, 20/55-day high/low bands

**Gaps vs spec:** MACD, SMA 50/100, skip-month momentum, OBV, historical volatility percentiles, feature store persistence.

### 3.5 Strategy engine (`app/strategies/engine.py`)

Six strategies in one module (not independent `BaseStrategy` subclasses):

| Strategy | Swing vs positional | Output |
|----------|---------------------|--------|
| Relative Momentum | Shared | BUY/WATCHLIST/NO ACTION, score 0–100 |
| Breakout | 20d vs 55d high | Same |
| Pullback | Shared | Same |
| Mean Reversion | Partial horizon tweak | Same |
| Trend Following | Shared | Same |
| 52-Week High Momentum | 85% vs 90% proximity | Same |

Each result includes entry (last close), ATR-based stop (2×ATR), target (3×ATR), risk/reward.

**Regime:** Per-symbol only (`Bullish` / `Bearish` / `Mixed / Sideways`) from price vs SMA200 — not Nifty 500 index regime engine.

**Gaps:** No strategy versioning, no externalized parameters, no signal IDs/lifecycle, strategies can be invoked only via HTTP evaluation paths (no order path — good).

### 3.6 Portfolio (`app/portfolio/service.py`)

- In-memory singleton `portfolio`.
- Weighted average cost positions; trade log (last 50 in snapshot).
- **Buy/sell** snapshots use only traded symbol price — other holdings use average until full `GET /api/portfolio`.
- No swing/positional sleeves, no risk sizing, no Shariah/ownership gates, no decimal types.

### 3.7 API contracts (legacy `/api/*`)

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/health` | Liveness |
| GET | `/api/universe` | Demo symbols + `shariah_status: UNVERIFIED` |
| GET | `/api/history/{symbol}` | OHLCV JSON |
| GET | `/api/signals/{symbol}?horizon=` | All strategies + features |
| GET | `/api/scan?horizon=` | Cross-section rank (horizon not validated) |
| GET | `/api/portfolio` | Paper snapshot |
| POST | `/api/portfolio/buy` | Paper buy |
| POST | `/api/portfolio/sell` | Paper sell |
| POST | `/api/data/upload` | CSV → memory |

**Backward compatibility:** Frontend (`src/lib/api.js`) depends on these paths and response shapes. Any v1 API must not break them.

### 3.8 Tests

- `tests/test_engine.py`: Asserts six strategies return with valid scores and `rsi14` in features.
- **Not tested:** HTTP layer, portfolio, upload, indicators edge cases.
- `pytest` not listed in `requirements.txt` (may exist in venv).

### 3.9 Dependencies

`fastapi`, `uvicorn`, `pandas`, `numpy`, `python-multipart`, `pydantic` — no SQLAlchemy, Alembic, PostgreSQL driver, httpx.

---

## 4. Frontend implementation

### 4.1 Stack

- React + Vite 8, Recharts, Lucide.
- Single file UI: `src/App.jsx` (~full dashboard).
- API client: `src/lib/api.js` → `VITE_API_URL` or `http://localhost:8000`.

### 4.2 Features implemented

- Portfolio KPIs, stock selector, swing/positional toggle.
- Price chart + indicator strip.
- Strategy cards, universe scanner table, paper buy/sell.
- Error banner on API failure.

### 4.3 Gaps vs target UX

- No React Router — sidebar items (Strategy lab, Shariah universe) are non-functional.
- No dedicated pages: Signals, Backtesting, Settings, Upload, Stock analysis deep-dive.
- `health()`, upload API, universe `shariah_status`/`source`, signals `notice` unused.
- No Tailwind, TanStack Query, theme toggle.
- `components/`, `pages/`, `services/` structure not created (client under `lib/`).

---

## 5. Hardcoded / sample data inventory

| Asset | Location | Mutable at runtime? |
|--------|----------|-------------------|
| Demo OHLCV | `sample_data.HISTORIES` | Yes (upload) |
| Symbol list | `sample_data.SYMBOLS` | Yes (upload) |
| Portfolio | `portfolio.service.portfolio` | Yes (trades) |
| Shariah status | Hardcoded `UNVERIFIED` in `main.py` | No logic |
| Strategy thresholds | Inline in `engine.py` | No |

---

## 6. Architectural problems

1. **Monolithic routes** — all HTTP in `main.py`; `api/` unused.
2. **No persistence** — restart loses trades and uploads (unless re-imported).
3. **Global shared state** — unsuitable for multi-user; no session isolation.
4. **Config drift** — `starting_cash` unused.
5. **Validation gaps** — `/api/scan` horizon not validated.
6. **Shariah module absent** — branding without screening or ownership lifecycle.
7. **No separation** of signal generation, portfolio decision, risk, execution.
8. **No backtesting** — largest functional gap vs spec.
9. **Survivorship / PIT universe** — single static symbol list from demo generator.
10. **Float money** — portfolio uses float, not `Decimal`.

---

## 7. Missing components (prioritized)

### P0 — Foundation

- PostgreSQL + SQLAlchemy 2 + Alembic
- Environment-based config
- Versioned `/api/v1` routers
- Core domain models + migrations
- Legacy route preservation

### P1 — Market data & features

- Provider interface (CSV + synthetic)
- OHLCV persistence, validation, corporate actions scaffold
- Expanded indicator library + unit tests

### P2 — Strategies & signals

- `BaseStrategy` modules per family
- Externalized parameters
- Signal model, scoring, ranking, lifecycle

### P3 — Portfolio, risk, Shariah, execution

- Dual sleeves, position sizing, limits
- Screening import, ownership state machine
- Paper execution pipeline with mandatory gates

### P4 — Backtesting & frontend

- Event-driven backtest engine
- Nine dashboard pages + API integration

### P5 — Scheduling, reporting, security hardening

---

## 8. Refactoring plan (incremental)

1. Extract **legacy router** from `main.py` unchanged.
2. Introduce **`/api/v1`** parallel to legacy; frontend migrates page-by-page.
3. Move indicator logic toward **`features/`** without breaking `evaluate_all` imports initially.
4. Split **strategies** into packages; keep `engine.evaluate_all` as facade during transition.
5. **Portfolio service** → execution/paper layer + DB persistence; legacy endpoints call adapter.
6. **Market data** reads from DB when available, falls back to `HISTORIES` in demo mode.

---

## 9. Backward-compatibility risks

| Change | Risk | Mitigation |
|--------|------|------------|
| Move routes | Frontend 404 | Keep `/api/*` router |
| JSON field rename | UI breaks | Additive fields only until frontend updates |
| Portfolio persistence | Different cash on restart | Document; seed from settings; migration script |
| Strategy score formula change | User confusion | Version strategies in API responses |

---

## 10. What works today (smoke test)

1. `uvicorn app.main:app` on port 8000
2. `npm run dev` on port 5173 (Node 20+)
3. View synthetic universe, signals, scan, chart, paper trades
4. CSV upload extends in-memory universe
5. `pytest tests/test_engine.py` (with venv deps)

This audit is the baseline for `docs/implementation/progress.md` and Milestone 1+ work.