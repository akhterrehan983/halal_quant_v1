"""M13 — valuation snapshots, drawdown audit, APIs."""

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from app.core.exceptions import HalalQuantError
from app.main import app
from app.portfolio import snapshots
from app.portfolio import store as portfolio_store
from app.portfolio.drawdown_audit import max_drawdown_over_period
from app.portfolio.money import D
from app.portfolio.snapshots import clear_mem_snapshots_for_tests, generate_snapshot
from app.portfolio.valuation import compute_portfolio_valuation, resolve_holdings_prices
from app.portfolio.valuation_schemas import SnapshotTrigger
from app.execution import store as exec_store

client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_valuation_state():
    clear_mem_snapshots_for_tests()
    portfolio_store._BOOK_MEM = None  # noqa: SLF001
    exec_store._STATE = exec_store._empty()  # noqa: SLF001
    yield
    clear_mem_snapshots_for_tests()


def test_equity_reconciles_cash_plus_invested():
    state = portfolio_store.load_book()
    resolution = resolve_holdings_prices(state.all_holdings(), strict=True)
    m = compute_portfolio_valuation(state, resolution)
    eq = m["portfolio_equity"]
    implied = m["available_cash"] + m["invested_market_value"]
    assert abs(eq - implied) < D("0.02")


def test_snapshot_immutable_second_daily_returns_same():
    s1 = generate_snapshot(trigger=SnapshotTrigger.DAILY, valuation_date=date.today())
    s2 = generate_snapshot(trigger=SnapshotTrigger.DAILY, valuation_date=date.today())
    assert s1.snapshot_id == s2.snapshot_id
    assert s1.portfolio_equity == s2.portfolio_equity


def test_drawdown_peak_tracking():
    state = portfolio_store.load_book()
    initial_peak = state.peak_value
    snap = generate_snapshot(trigger=SnapshotTrigger.ON_DEMAND)
    assert snap.equity_peak_at_snapshot >= initial_peak
    assert snap.drawdown_pct >= D(0)


def test_missing_price_strict_fails():
    state = portfolio_store.load_book()
    portfolio_store.update_book(
        lambda b: portfolio_store._merge_holding(b, "swing", "NOTAREAL", 1, D("1"))  # noqa: SLF001
    )
    state = portfolio_store.load_book()
    with pytest.raises(HalalQuantError):
        resolve_holdings_prices(state.all_holdings(), strict=True)


def test_performance_history_api_empty():
    r = client.get("/api/v1/portfolio/performance-history")
    assert r.status_code == 200
    assert r.json()["points"] == []
    assert "backtest" in r.json()["notice"].lower() or "not backtest" in r.json()["notice"].lower()


def test_snapshot_post_and_list():
    r = client.post("/api/v1/portfolio/valuations/snapshot", json={"trigger": "on_demand"})
    assert r.status_code == 200
    r2 = client.get("/api/v1/portfolio/valuations")
    assert r2.status_code == 200
    assert r2.json()["total"] >= 1


def test_max_drawdown_from_stored_equity():
    from datetime import datetime, timezone

    from app.portfolio.valuation_schemas import ValuationSnapshotRecord

    base = date.today() - timedelta(days=2)
    zero = D(0)

    def row(i: int, eq: str) -> ValuationSnapshotRecord:
        return ValuationSnapshotRecord(
            snapshot_id=i,
            book_name="default",
            valued_at=datetime.now(timezone.utc),
            valuation_date=base + timedelta(days=i),
            trigger=SnapshotTrigger.ON_DEMAND,
            portfolio_equity=D(eq),
            available_cash=zero,
            reserved_cash=zero,
            invested_market_value=D(eq),
            realized_pnl=zero,
            unrealized_pnl=zero,
            total_pnl=zero,
            swing_equity=zero,
            positional_equity=zero,
            cash_reserve=zero,
            equity_peak_prior=D("100000"),
            equity_peak_at_snapshot=D("100000"),
            drawdown_amount=zero,
            drawdown_pct=zero,
        )

    recs = [row(0, "100000"), row(1, "80000"), row(2, "100000")]
    dd = max_drawdown_over_period(recs)
    assert dd == D("0.2")


@pytest.mark.postgres
def test_postgres_snapshot_persisted():
    from app.core.config import settings
    from app.core.database import SessionLocal
    from sqlalchemy import select
    from app.models.portfolio_valuation import PortfolioValuationSnapshot

    if not (settings.database_enabled and SessionLocal):
        pytest.skip("PostgreSQL not configured")
    snap = generate_snapshot(trigger=SnapshotTrigger.ON_DEMAND)
    with SessionLocal() as session:
        row = session.get(PortfolioValuationSnapshot, snap.snapshot_id)
        assert row is not None
        assert float(row.portfolio_equity) == float(snap.portfolio_equity)