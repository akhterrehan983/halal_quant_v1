# Halal Quant V1 — Operations Runbook

## Startup

```bash
# Backend (demo or Postgres)
cd halal_quant_v1 && docker compose up -d postgres   # if using DB
# Set DATABASE_URL in project root .env (see .env.example — never commit .env)
cd backend && source .venv/bin/activate
alembic upgrade head   # uses same .env as uvicorn
python -m scripts.verify_postgres_setup   # optional smoke after migrate
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Frontend
cd frontend && nvm use && npm run dev
```

**Health:** `GET /api/health` and `GET /api/v1/health` — check `database_enabled` and `demo_mode`.

**Alembic head (2026-11):** `c4d2e8a91f03` — 20 application tables including `portfolio_books`, `execution_state`, `ohlcv_candles`, `research_signals`, `backtest_runs`, `shariah_*`, `risk_*`.

**M12 Postgres tests:** from `backend/`, `pytest -q tests/test_integration_m12.py` — includes `test_postgres_reconcile_smoke` when `.env` has `DATABASE_URL` (not only shell `export`).

## Postgres vs demo

| Capability | Demo (no `DATABASE_URL`) | PostgreSQL |
|------------|--------------------------|------------|
| Market CSV import persist | In-memory only | Durable |
| Signals / portfolio book | In-memory JSON | `portfolio_books`, etc. |
| Execution state | In-memory | `execution_state` row |
| Settings risk config | Resets on restart | Persisted |

If `DATABASE_URL` is set but DB is down, the app should fail at startup/migration — do not assume silent fallback.

## Backup (Postgres)

```bash
pg_dump -h localhost -U halal_quant halal_quant > backup_$(date +%F).sql
```

Restore: `psql ... < backup_*.sql` then verify `alembic current`.

## Migrations

```bash
cd backend && source .venv/bin/activate
alembic upgrade head
alembic current
```

Chain includes M5 portfolio/risk, M6 shariah/execution, M7 backtesting.

## Regression tests

```bash
cd backend && pytest -q
cd frontend && npm run test && npm run build
```

Pytest forces **demo mode** by default (overrides root `.env` `DATABASE_URL`) so integration tests stay isolated. The Postgres smoke test is marked `@pytest.mark.postgres` and uses your real DB. Optional: `pytest -q -m postgres` to run only DB-backed tests.

## Large CSV imports

Use validate endpoint first (`POST /api/v1/market-data/validate`). Import with `conflict_policy=skip|update|reject`. Monitor API logs for row rejection counts.

## Backtests

CPU-heavy; run via API or pytest with adequate timeout (~5 min subset). Monte Carlo/sensitivity multiply simulator runs — use small grids in CI.