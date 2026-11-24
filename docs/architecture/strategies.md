# Strategy architecture (Milestone 3)

## Overview

Six independent rule-based strategies live under `app/strategies/<name>/strategy.py`. They share:

- `BaseStrategy` interface (`base.py`)
- `StrategyContext` (OHLCV + precomputed features)
- `StrategyResultModel` (`schemas.py`) — includes `to_legacy_dict()` for `/api/signals`
- `registry.py` — registration, enable/disable, lookup
- `evaluator.py` — builds context from market data repository inputs
- `config.py` — swing vs positional parameters (`HorizonConfig`)

## Strategies

| ID | Legacy name | Entry idea (simplified) |
|----|-------------|-------------------------|
| `momentum` | Relative Momentum | 3M/6M returns > 0, price > EMA50 |
| `breakout` | Breakout | Close > prior 20/55d high, rel vol ≥ 1.2 |
| `pullback` | Pullback | Uptrend + touch EMA20 + RSI band |
| `mean_reversion` | Mean Reversion | Below lower BB, RSI < 35, trend context |
| `trend_following` | Trend Following | SMA200 + EMA20>EMA50 + ADX ≥ 18 |
| `high_momentum` | 52-Week High Momentum | Near 52w high + 3M return + EMA50 |

Stops/targets: ATR multiples from `HorizonConfig` (2× / 3× default).

## Horizons

- **Swing:** 20-day breakout window, 85% 52w proximity.
- **Positional:** 55-day breakout window, 90% 52w proximity.

## Signal directions

`BUY`, `SELL`, `HOLD`, `NO_SIGNAL` — legacy API maps to `BUY` / `WATCHLIST` / `NO ACTION` via score thresholds (not calibrated probabilities).

## API

- `GET /api/v1/strategies`
- `GET /api/v1/strategies/{id}`
- `PATCH /api/v1/strategies/{id}` — enable/disable (in-memory session)
- `POST /api/v1/strategies/{id}/evaluate`
- `POST /api/v1/strategies/evaluate`

`evaluate_all()` in `engine.py` delegates to the registry.

## Limitations

- Enable/disable not persisted across API restarts.
- No benchmark-relative momentum yet (context hook reserved).
- SELL is analytical only (long-only platform).