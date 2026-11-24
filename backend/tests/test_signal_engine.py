import pytest

from app.data.sample_data import make_history
from app.signals.aggregator import build_contributions
from app.signals.config import DEFAULT_WEIGHTS
from app.signals.lifecycle import LifecycleError, can_transition, should_supersede, transition
from app.signals.generator import generate_unified_signal
from app.signals.persistence import persist_signal
from app.signals.schemas import LifecycleState, UnifiedSignal
from app.strategies.evaluator import evaluate_all_strategies


def test_scoring_weights_sum():
    DEFAULT_WEIGHTS.validate()


def test_correlated_strategy_consensus():
    results = evaluate_all_strategies("TCS", make_history("TCS", periods=120), "swing")
    _c, eff, _x, level = build_contributions(results)
    assert eff >= 0
    assert level in ("none", "low", "moderate", "high")


def test_unified_signal_generate():
    sig = generate_unified_signal("TCS", make_history("TCS", periods=120), "swing")
    assert sig.symbol == "TCS"
    assert len(sig.contributions) == 6
    assert 0 <= sig.overall_score <= 100


def test_lifecycle_transitions():
    sig = UnifiedSignal(
        symbol="X",
        horizon="swing",
        evaluation_date=make_history("X").iloc[-1].date.date(),
        category="WATCHLIST",
        overall_score=65,
        market_regime="MIXED",
        entry_reference=100,
        stop_reference=95,
        target_reference=110,
        score_breakdown={"total": 65},
    )
    sig = transition(sig, LifecycleState.ACTIVE, "test")
    assert sig.lifecycle_state == LifecycleState.ACTIVE
    with pytest.raises(LifecycleError):
        transition(sig, LifecycleState.CREATED, "invalid")


def test_duplicate_suppression():
    a = generate_unified_signal("TCS", make_history("TCS"), "swing")
    b = generate_unified_signal("TCS", make_history("TCS"), "swing")
    assert not should_supersede(a, b)


def test_persist_demo_mode():
    sig = generate_unified_signal("INFY", make_history("INFY"), "swing")
    saved = persist_signal(sig)
    assert saved.signal_id is not None


def test_api_generate(client=None):
    from fastapi.testclient import TestClient
    from app.main import app

    res = TestClient(app).post("/api/v1/signals/generate", json={"symbol": "TCS", "horizon": "swing"})
    assert res.status_code == 200
    assert res.json()["count"] >= 1