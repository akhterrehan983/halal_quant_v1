# Signal Engine & Market Regime (Milestone 4)

Research-only unified signals. No trade execution, no capital allocation, no profit probability claims.

---

## Market regime classifier

**Location:** `backend/app/regime/`

**Benchmark:** Configurable symbol (default Nifty 500 proxy). Uses repository benchmark series when present; otherwise equal-weight synthetic universe proxy from demo `HISTORIES` (documented in `benchmark.py`).

**Labels:** `BULLISH`, `BEARISH`, `SIDEWAYS`, `HIGH_VOLATILITY`, `MIXED`

**Factors (reproducible, as-of index):**

- Close vs SMA50 and SMA200
- EMA50 slope
- ADX trend threshold
- 20-day historical volatility vs trailing percentile (`HIGH_VOLATILITY`)
- Optional universe breadth: % of demo symbols above their SMA50, **as of the benchmark bar date** (`compute_universe_breadth(as_of_date=)` — M11)

**India VIX:** Not fabricated when no data source is configured.

**Output:** `RegimeClassification` with `factors`, `observations`, `confidence`, `data_quality`, and explicit insufficient-history handling.

**Use:** Regime adjusts scoring alignment and can hard-cap actionable categories in bearish/high-vol conditions. It is **not** a global BUY/SELL switch.

Configurable thresholds live in `regime/config.py`.

---

## Benchmark-relative strength

**Location:** `backend/app/features/relative_strength.py`

Aligned return windows (stock return minus benchmark return):

- `rel_21d` (~1 month)
- `rel_63d` (~3 months)
- `rel_126d` (~6 months)
- `rel_252d` (~12 months)

Missing benchmark bars → `None` (no imputation). Wired into `StrategyContext.benchmark_features` for Momentum and High Momentum.

---

## Signal generation pipeline

**Location:** `backend/app/signals/`

| Module | Role |
|--------|------|
| `generator.py` | Orchestrates regime (evaluation-date anchored), strategies, scoring, unified signal |
| `aggregator.py` | Strategy consensus with correlation de-duplication |
| `scoring.py` | Transparent 0–100 factor score |
| `ranking.py` | Sort candidates for research lists |
| `lifecycle.py` | Valid state transitions, supersession, expiration rules |
| `persistence.py` | PostgreSQL or explicit in-memory demo store |

Six registered strategies are evaluated per symbol; per-strategy outputs are preserved on the unified signal payload.

---

## Scoring (initial weights — not optimized)

| Factor | Weight |
|--------|-------:|
| Momentum quality | 25 |
| Trend quality | 20 |
| Strategy setup quality | 20 |
| Benchmark-relative strength | 15 |
| Volume confirmation | 10 |
| Market regime alignment | 10 |

Weights must sum to 100 (`signals/config.py`). Missing relative strength does not receive full points.

**Categories (configurable):**

- `STRONG_BUY`: 85–100
- `BUY`: 75–84
- `WATCHLIST`: 60–74
- `NO_ACTION`: below 60 or hard rejection

Hard context gate: very high scores in `BEARISH` / `HIGH_VOLATILITY` regimes are capped to `NO_ACTION` for display (future portfolio/Shariah gates still apply).

---

## Strategy consensus

Correlated groups (first BUY counts full weight; second in group ≈ 0.35):

- `momentum` + `high_momentum`
- `breakout` + `trend_following`

`consensus_effective_buys` drives agreement level (`none` / `low` / `moderate` / `high`). Conflicts surface strategies with cautious scores but no BUY.

Sub-threshold effective consensus adds a rejection note; it does not block signal creation.

---

## Lifecycle & expiration

**States:** CREATED → ACTIVE → (EXPIRED | SUPERSEDED | ENTERED → HOLDING → EXIT_TRIGGERED → CLOSED) or REJECTED

Invalid transitions raise `LifecycleError`.

**Duplicate control:** Persisting an ACTIVE signal for the same symbol+horizon supersedes when score or entry reference moves beyond configured thresholds (`lifecycle` config).

**Expiration:** `expires_after_sessions` (swing vs positional defaults). Calendar-day approximation when only daily bars exist — documented limitation vs true NSE session count.

Historical evaluations use `as_of_index` on regime, relative strength, and strategy context (no future leakage).

---

## APIs

- `GET /api/v1/regime/current`
- `GET /api/v1/regime/history`
- `GET /api/v1/signals?mode=unified` (filters: symbol, category, lifecycle)
- `GET /api/v1/signals?mode=legacy` (per-strategy M3 list — default)
- `POST /api/v1/signals/generate`, `/generate/batch`
- `GET /api/v1/signals/rankings`
- `GET /api/v1/signals/{id}`, `/signals/{id}/history`

Legacy `/api/*` and `evaluate_all()` unchanged.

---

## Database

Alembic revision `86bcb02a62c5_milestone4_signals`:

- `research_signals` (JSON payload + indexes)
- `signal_lifecycle_events`

Demo mode without `DATABASE_URL` uses in-memory signal store only (not silent DB fallback).

---

## Known limitations

- Demo/synthetic prices unless CSV + Postgres populated
- Breadth and benchmark proxy are research approximations
- No India VIX, no licensed holiday calendar for session-based expiry
- Historical Shariah point-in-time eligibility deferred to Milestone 6
- Scores and category thresholds are **initial hypotheses**, not backtested optima