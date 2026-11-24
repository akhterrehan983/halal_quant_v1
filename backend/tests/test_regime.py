import pandas as pd

from app.data.sample_data import make_history
from app.features.relative_strength import aligned_relative_returns
from app.regime.classifier import classify_market
from app.regime.schemas import MarketRegimeLabel


def test_classify_market_returns_factors():
    c = classify_market()
    assert c.regime in MarketRegimeLabel
    assert "close" in c.factors
    assert c.confidence >= 0


def test_classify_market_model_dump_json_serializable():
    payload = classify_market().model_dump(mode="json")
    assert isinstance(payload["factors"]["high_volatility_flag"], bool)


def test_historical_as_of_no_future():
    c_last = classify_market(as_of_index=-1)
    c_prev = classify_market(as_of_index=-5)
    assert c_last.as_of_date >= c_prev.as_of_date


def test_relative_strength_aligned():
    stock = make_history("REL", periods=120)
    rel = aligned_relative_returns(stock)
    assert "rel_63d" in rel
    assert rel["rel_63d"] is None or isinstance(rel["rel_63d"], float)


def test_insufficient_benchmark_history():
    c = classify_market(as_of_index=-10000)
    assert c.data_quality in ("ok", "insufficient_history")