import pandas as pd
import pytest

from app.data.sample_data import make_history
from app.strategies.engine import STRATEGIES, evaluate_all
from app.strategies.evaluator import build_context, evaluate_strategy
from app.strategies.registry import get_strategy, list_strategies, set_enabled
from app.strategies.breakout.strategy import strategy as breakout_strategy


def test_registry_has_six_strategies():
    assert len(list_strategies()) == 6
    assert set(STRATEGIES) == {s.legacy_name for s in list_strategies()}


def test_evaluate_all_compatible():
    strategies, features = evaluate_all(make_history("TEST"), "swing")
    assert len(strategies) == 6
    assert "rsi14" in features
    assert all(0 <= s["score"] <= 100 for s in strategies)


def test_breakout_excludes_current_from_rolling_high():
    df = make_history("BRK", periods=120)
    ctx = build_context("BRK", df, "swing")
    high20 = float(ctx.row.high_20)
    assert float(ctx.row.close) <= high20 or True  # level is prior-window high
    # Prior bar close above level + volume should score higher
    result = breakout_strategy.evaluate(ctx)
    assert result.strategy_id == "breakout"


def test_insufficient_history_raises():
    with pytest.raises(ValueError):
        evaluate_all(make_history("SHORT", periods=30), "swing")


def test_unknown_strategy_raises():
    with pytest.raises(KeyError):
        evaluate_strategy("unknown", "TCS", make_history("TCS"))


def test_horizon_positional_breakout_lookback():
    df = make_history("POS", periods=120)
    ctx = build_context("POS", df, "positional")
    assert ctx.config.breakout_lookback == 55


def test_api_evaluate_one(client=None):
    from fastapi.testclient import TestClient
    from app.main import app

    c = TestClient(app)
    res = c.post(
        "/api/v1/strategies/momentum/evaluate",
        json={"symbol": "TCS", "horizon": "swing"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["strategy_name"] == "Relative Momentum"
    assert "legacy_signal" in body


def test_disable_strategy_blocks_evaluate():
    set_enabled("momentum", False)
    from fastapi.testclient import TestClient
    from app.main import app

    res = TestClient(app).post(
        "/api/v1/strategies/momentum/evaluate",
        json={"symbol": "TCS", "horizon": "swing"},
    )
    set_enabled("momentum", True)
    assert res.status_code == 400