"""M12 — single book, legacy lockdown, reconciliation, fill idempotency."""

from datetime import date
from decimal import Decimal
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from sqlalchemy import select

from app.core.config import settings
from app.core.database import SessionLocal
from app.execution import store
from app.execution.fill_processor import apply_fill_to_book, apply_overlay_sync, process_simulated_fill
from app.execution.order_manager import create_order
from app.execution.reconcile import reconcile_all, reconcile_report, sync_overlay_from_book
from app.execution.schemas import FillRecord, OrderSide, OrderType, PaperOrder, OrderState
from app.main import app
from app.models.portfolio_risk import PortfolioBook
from app.models.shariah_execution import ExecutionStateRow
from app.portfolio import store as portfolio_store
from app.portfolio.money import D
from app.shariah.business_activity import submit_activity
from app.shariah.schemas import OwnershipPossessionState
from app.shariah.screening import run_screening

client = TestClient(app)


def _postgres_configured() -> bool:
    return bool(settings.database_enabled and SessionLocal is not None)


def _compliant(symbol: str = "TCS"):
    submit_activity(symbol, [{"category": "it_services", "prohibited": False, "source": "test", "verified_at": "2026-01-01"}])
    run_screening(
        symbol,
        financials={
            "data_source": "test",
            "reporting_period": "FY2025",
            "interest_bearing_debt": 1000,
            "market_capitalization": 100000,
            "non_compliant_income": 100,
            "revenue": 50000,
        },
    )


def test_legacy_buy_always_forbidden():
    r = client.post("/api/portfolio/buy", json={"symbol": "TCS", "quantity": 1, "price": 100})
    assert r.status_code == 403


def test_v1_trades_sell_forbidden():
    r = client.post("/api/v1/trades/sell", json={"symbol": "TCS", "quantity": 1, "price": 100})
    assert r.status_code == 403


def test_legacy_get_portfolio_uses_research_book():
    r = client.get("/api/portfolio")
    assert r.status_code == 200
    assert r.json().get("scope") == "research_book"


def test_buy_fill_book_matches_overlay():
    _compliant()
    order = PaperOrder(
        order_id=1,
        symbol="TCS",
        sleeve="swing",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=3,
        reserved_cash=D(0),
        state=OrderState.APPROVED,
    )
    store.save_order(order)
    fill = FillRecord(order_id=1, quantity=3, price=D("400"), slippage=D(0), fees=D("15"), trade_date=date.today())
    apply_fill_to_book(order, fill)
    apply_overlay_sync(order)
    book = portfolio_store.load_book()
    bh = next(h for h in book.holdings_swing if h.symbol == "TCS")
    ov = store.get_holding("TCS", "swing")
    assert ov is not None
    assert ov.quantity == bh.quantity == 3


def test_reconcile_endpoint_ok_after_workflow():
    test_buy_fill_book_matches_overlay()
    r = client.get("/api/v1/portfolio/reconciliation")
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_fill_idempotent_retry():
    _compliant()
    order = PaperOrder(
        order_id=2,
        symbol="TCS",
        sleeve="swing",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=2,
        state=OrderState.APPROVED,
    )
    store.save_order(order)
    fill = FillRecord(order_id=2, quantity=2, price=D("100"), slippage=D(0), fees=D("5"), trade_date=date.today())
    apply_fill_to_book(order, fill)
    book1 = portfolio_store.load_book().balances["swing"]
    apply_fill_to_book(order, fill)
    book2 = portfolio_store.load_book().balances["swing"]
    assert book1 == book2


def test_failure_before_book_mutation_then_idempotent_recovery():
    _compliant()
    order = PaperOrder(
        order_id=5,
        symbol="TCS",
        sleeve="swing",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=1,
        state=OrderState.APPROVED,
    )
    store.save_order(order)
    fill = FillRecord(order_id=5, quantity=1, price=D("50"), slippage=D(0), fees=D("1"), trade_date=date.today())
    calls = {"n": 0}

    def flaky_apply(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise ValueError("simulated book failure")
        return store.apply_buy_fill(*args, **kwargs)

    with patch("app.execution.store.apply_buy_fill", side_effect=flaky_apply):
        with pytest.raises(ValueError):
            apply_fill_to_book(order, fill)
    apply_fill_to_book(order, fill)
    apply_overlay_sync(order)
    assert reconcile_report()["ok"]


def test_failure_before_persist_flag():
    _compliant()
    order = PaperOrder(
        order_id=3,
        symbol="TCS",
        sleeve="swing",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=1,
        state=OrderState.APPROVED,
    )
    store.save_order(order)
    with patch("app.execution.fill_processor.simulate_market_fill", return_value=(1, D("50"), date.today())):
        with pytest.raises(RuntimeError):
            process_simulated_fill(order, raise_before_persist=True)
    order = store.get_order(3)
    fill = FillRecord(order_id=3, quantity=1, price=D("50"), slippage=D(0), fees=D("1"), trade_date=date.today())
    apply_fill_to_book(order, fill)
    apply_overlay_sync(order)
    assert reconcile_report()["ok"]


def test_failure_skip_overlay_then_reconcile():
    _compliant()
    order = PaperOrder(
        order_id=4,
        symbol="TCS",
        sleeve="swing",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=2,
        state=OrderState.APPROVED,
    )
    store.save_order(order)
    fill = FillRecord(order_id=4, quantity=2, price=D("60"), slippage=D(0), fees=D("2"), trade_date=date.today())
    apply_fill_to_book(order, fill)
    sync_overlay_from_book("TCS", "swing")
    assert reconcile_all()["ok"]


def test_reconcile_never_increases_authorized_sell_qty():
    from app.execution.schemas import ExecutionHolding

    _compliant()
    store.upsert_holding(
        ExecutionHolding(
            symbol="TCS",
            sleeve="swing",
            quantity=99,
            sellable_quantity=99,
            avg_price=D(1),
            ownership_state=OwnershipPossessionState.SELL_AUTHORIZED,
            authorized_sell_qty=2,
        )
    )
    portfolio_store.update_book(lambda b: portfolio_store._merge_holding(b, "swing", "TCS", 5, D("100")))  # noqa: SLF001
    sync_overlay_from_book("TCS", "swing")
    ov = store.get_holding("TCS", "swing")
    assert ov.quantity == 5
    assert ov.authorized_sell_qty <= 5
    assert ov.authorized_sell_qty == 2


@pytest.mark.postgres
@pytest.mark.skipif(not _postgres_configured(), reason="PostgreSQL not configured (.env DATABASE_URL)")
def test_postgres_reconcile_smoke():
    """With DATABASE_URL in .env: reconcile API + portfolio/execution rows in PostgreSQL."""
    _compliant()
    order = PaperOrder(
        order_id=9001,
        symbol="TCS",
        sleeve="swing",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=2,
        state=OrderState.APPROVED,
    )
    store.save_order(order)
    fill = FillRecord(order_id=9001, quantity=2, price=D("100"), slippage=D(0), fees=D("5"), trade_date=date.today())
    apply_fill_to_book(order, fill)
    apply_overlay_sync(order)
    r = client.get("/api/v1/portfolio/reconciliation?repair=true")
    assert r.status_code == 200
    body = r.json()
    assert body.get("repaired") is not None or "mismatches" in body or "status" in body

    with SessionLocal() as session:
        book = session.execute(select(PortfolioBook).where(PortfolioBook.name == "default")).scalar_one_or_none()
        assert book is not None
        swing = [h for h in book.state_json.get("holdings_swing", []) if h.get("symbol") == "TCS"]
        assert swing and int(swing[0]["quantity"]) >= 2
        erow = session.execute(select(ExecutionStateRow).where(ExecutionStateRow.name == "default")).scalar_one()
        holds = [h for h in erow.state_json.get("holdings", []) if h.get("symbol") == "TCS"]
        assert holds and int(holds[0]["quantity"]) == int(swing[0]["quantity"])

    portfolio_store._BOOK_MEM = None  # noqa: SLF001
    store._STATE = None  # noqa: SLF001
    reloaded = portfolio_store.load_book()
    assert any(h.symbol == "TCS" and h.quantity >= 2 for h in reloaded.holdings_swing)