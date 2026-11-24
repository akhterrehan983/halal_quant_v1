from app.data.sample_data import make_history
from app.strategies.engine import evaluate_all

def test_all_strategies_returned():
    strategies, features = evaluate_all(make_history("TEST"), "swing")
    assert len(strategies) == 6
    assert "rsi14" in features
    assert all(0 <= s["score"] <= 100 for s in strategies)
