# Halal Quant V1 — Implementation Progress

Track milestone completion against the engineering specification.

---

## Milestone 1 — Foundation (substantially complete)

### Completed components

- [x] Repository audit → `docs/architecture/current_state.md`
- [x] Progress tracking → this file
- [x] PostgreSQL via `docker-compose.yml`
- [x] SQLAlchemy 2 models (stocks, candles, Shariah scaffold, paper portfolio tables)
- [x] Alembic (`migrations/versions/aec82f8a19c5_initial_schema.py`)
- [x] Environment-based configuration (`pydantic-settings`, `.env.example`)
- [x] Core modules: `database`, `logging`, `exceptions`, `security` placeholder
- [x] Legacy `/api/*` preserved in `app/api/legacy.py` (+ scan horizon validation fix)
- [x] `/api/v1` routers: health, stocks, market, strategies, signals, portfolio/trades
- [x] `pyproject.toml`, updated `requirements.txt`
- [x] `frontend/.nvmrc`, `package.json` `engines`
- [x] Market data provider scaffold (`demo_provider`, `base`)
- [x] `scripts/seed_demo_to_db.py` for optional DB seed

### Files created (high level)

- `docs/architecture/current_state.md`
- `docker-compose.yml`, `.env.example`
- `backend/app/api/legacy.py`, `backend/app/api/v1/*`
- `backend/app/models/*`, `backend/app/core/*` (expanded)
- `backend/app/market_data/providers/*`
- `backend/migrations/*`, `backend/scripts/seed_demo_to_db.py`
- `backend/tests/test_api_v1.py`

### Files modified

- `backend/app/main.py` — thin app factory + dual routers
- `backend/app/core/config.py`, `backend/app/portfolio/service.py`
- `backend/requirements.txt`, `frontend/package.json`

### API endpoints added (`/api/v1`)

| Method | Path | Notes |
|--------|------|--------|
| GET | `/api/v1/health` | Includes `demo_mode` flag |
| GET | `/api/v1/stocks` | Demo universe metadata |
| GET | `/api/v1/stocks/{symbol}` | Detail + strategies |
| GET | `/api/v1/market-data/{symbol}` | OHLCV |
| GET | `/api/v1/market/regime` | Provisional cross-section proxy |
| GET | `/api/v1/strategies` | Six strategy metadata |
| GET/POST | `/api/v1/signals`, `/signals/generate` | In-memory evaluation |
| GET | `/api/v1/portfolio/summary`, `/positions` | Paper portfolio |
| POST | `/api/v1/trades/buy`, `/sell` | Paper trades |

Legacy `/api/*` unchanged for existing React client.

### Database migrations

| Revision | Description | Status |
|----------|-------------|--------|
| `aec82f8a19c5` | `initial_schema` | Applied when `DATABASE_URL` set |

### Tests executed

| Suite | Result |
|-------|--------|
| `tests/test_engine.py` | **PASS** |
| `tests/test_api_v1.py` | **PASS** (5 tests total) |

### Known limitations (post-M1)

- Default runtime remains **in-memory demo** without `DATABASE_URL`.
- DB seed does not yet drive API reads (Milestone 2).
- Most spec entities (signals DB, backtests, ownership, risk) not created.
- Frontend still on legacy `/api` only (Milestone 8).
- Six strategies still in monolithic `engine.py` (Milestone 3 refactor).

### Remaining work

- **M2:** CSV provider persistence, validation, indicator feature package
- **M3–7:** Strategies split, signals lifecycle, portfolio/risk, Shariah/execution, backtesting
- **M8–9:** Full frontend pages, E2E workflow, Definition of Done automation

---

## Milestones 2–9

Not started. Each will append a section here with the same structure.