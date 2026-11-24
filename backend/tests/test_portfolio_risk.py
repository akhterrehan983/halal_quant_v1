from decimal import Decimal

import pytest

from app.portfolio.money import D
from app.portfolio.position_sizing import compute_position_quantity
from app.portfolio.store import BookState, _default_book, load_book, save_book
from app.risk.drawdown import breach_drawdown, drawdown_pct
from app.risk.schemas import RiskConfiguration
from app.risk.stop_loss import trailing_stop_update
from app.risk.validation import validate_allocation
from app.portfolio.schemas import AllocationProposal, SleeveHolding
from app.signals.generator import generate_unified_signal
from app.signals.persistence import persist_signal
from app.data.sample_data import make_history
from app.portfolio import allocator


@pytest.fixture
def fresh_book(monkeypatch):
    monkeypatch.setattr("app.portfolio.store._BOOK_MEM", None)
    return load_book()


def test_position_sizing_normal():
    r = compute_position_quantity(
        sleeve_equity=D(100000),
        risk_per_trade_pct=D("0.01"),
        entry_price=D(100),
        stop_price=D(95),
        available_cash=D(50000),
    )
    assert r.quantity > 0
    assert r.notional <= D(50000)


def test_position_sizing_stop_above_entry():
    r = compute_position_quantity(
        sleeve_equity=D(100000),
        risk_per_trade_pct=D("0.01"),
        entry_price=D(100),
        stop_price=D(101),
        available_cash=D(50000),
    )
    assert r.quantity == 0
    assert r.rejections


def test_risk_config_sum():
    cfg = RiskConfiguration()
    cfg.validate_allocations()


def test_trailing_stop_never_down():
    assert trailing_stop_update(D(90), D(88)) == D(90)
    assert trailing_stop_update(D(90), D(92)) == D(92)


def test_drawdown_breach():
    assert breach_drawdown(D("0.16"), D("0.15"))


def test_allocation_from_signal(fresh_book):
    sig = persist_signal(generate_unified_signal("TCS", make_history("TCS"), "swing"))
    prop = allocator.build_proposal_from_signal(sig)
    assert prop.symbol == "TCS"
    assert prop.stop_reference < prop.entry_reference or prop.rejections


def test_api_portfolio_summary():
    from fastapi.testclient import TestClient
    from app.main import app

    res = TestClient(app).get("/api/v1/portfolio/summary")
    assert res.status_code == 200
    assert "swing" in res.json()


def test_generate_proposals_endpoint():
    from fastapi.testclient import TestClient
    from app.main import app

    persist_signal(generate_unified_signal("INFY", make_history("INFY"), "swing"))
    res = TestClient(app).post("/api/v1/portfolio/allocate", json={"horizon": "swing", "limit": 5})
    assert res.status_code == 200