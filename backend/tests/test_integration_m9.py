"""Milestone 9 integration — financial integrity and paper workflow."""

from datetime import date, timedelta
from decimal import Decimal

import pandas as pd
import pytest

from app.backtesting.schemas import BacktestConfig, ShariahBacktestMode
from app.backtesting.simulator import run_backtest
from app.backtesting.validation_sensitivity import sensitivity_grid
from app.core.exceptions import ConcurrentBookUpdate
from app.execution import store
from app.execution.schemas import FillRecord, OrderSide, OrderState, OrderType, PaperOrder
from app.execution.sell_authorization import evaluate_sell
from app.execution.settlement import process_settlements
from app.portfolio import store as portfolio_store
from app.portfolio.money import D
from app.shariah.business_activity import submit_activity
from app.shariah.schemas import OwnershipPossessionState
from app.shariah.screening import run_screening


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


def test_book_optimistic_version_conflict():
    state = portfolio_store.load_book()
    state.balances["swing"] = D("1")
    with pytest.raises(ConcurrentBookUpdate):
        portfolio_store.save_book(state, expected_version=state.state_version + 99)


def test_buy_fill_merges_average_cost():
    _compliant()

    def seed_holding(book):
        portfolio_store._merge_holding(book, "swing", "TCS", 10, D("100"))  # noqa: SLF001

    portfolio_store.update_book(seed_holding)
    order = PaperOrder(
        order_id=1,
        symbol="TCS",
        sleeve="swing",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=5,
        reserved_cash=D(0),
    )
    fill = FillRecord(order_id=1, quantity=5, price=D("200"), slippage=D(0), fees=D("10"), trade_date=date.today())
    store.apply_buy_fill(order, fill, fill.fees)
    book = portfolio_store.load_book()
    h = book.holdings_swing[0]
    assert h.quantity == 15
    expected = (D(10) * D(100) + D(5) * D(200)) / D(15)
    assert abs(h.average_entry - expected) < D("0.02")


def test_sell_authorization_quantity_cap():
    from app.execution.schemas import ExecutionHolding

    portfolio_store.update_book(lambda b: portfolio_store._merge_holding(b, "swing", "TCS", 10, D(100)))  # noqa: SLF001
    store.upsert_holding(
        ExecutionHolding(
            symbol="TCS",
            sleeve="swing",
            quantity=10,
            sellable_quantity=10,
            avg_price=D(100),
            ownership_state=OwnershipPossessionState.SELL_AUTHORIZED,
            authorized_sell_qty=3,
        )
    )
    assert not evaluate_sell("TCS", 5).granted


def test_backtest_can_exit_after_authorization():
    end = date.today() - timedelta(days=5)
    start = end - timedelta(days=80)
    cfg = BacktestConfig(
        name="m9_exit",
        start_date=start,
        end_date=end,
        horizon="swing",
        shariah_mode=ShariahBacktestMode.RESEARCH_ONLY,
        hold_days=5,
        max_positions=3,
    )
    run = run_backtest(cfg)
    assert run.status.value == "COMPLETED"
    # M14 Phase 1: stops/targets are now enforced, so demo exits may be stop/target as well as time exits.
    allowed = {"time_exit_authorized", "stop", "target", "stop_ownership_delayed"}
    assert all(t.exit_reason in allowed for t in run.trades)
    assert all(t.exit_date >= (pd.Timestamp(t.entry_date) + pd.offsets.BDay(3)).date() for t in run.trades)


def test_sensitivity_changes_hold_days():
    end = date.today() - timedelta(days=5)
    start = end - timedelta(days=50)
    cfg = BacktestConfig(name="sens", start_date=start, end_date=end, shariah_mode=ShariahBacktestMode.RESEARCH_ONLY)
    out = sensitivity_grid(cfg, hold_days_grid=[5, 20], min_score_grid=[90])
    assert len(out["grid"]) == 3
    assert out["grid"][0]["parameter"] == "hold_days"


def test_paper_workflow_buy_updates_portfolio_book():
    _compliant()
    book_before = portfolio_store.load_book()
    cash_before = book_before.balances["swing"]
    order = PaperOrder(
        order_id=1,
        symbol="TCS",
        sleeve="swing",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=2,
        reserved_cash=D("1000"),
    )
    fill = FillRecord(order_id=1, quantity=2, price=D("500"), slippage=D(0), fees=D("20"), trade_date=date.today())
    store.apply_buy_fill(order, fill, fill.fees)
    book_after = portfolio_store.load_book()
    assert book_after.balances["swing"] < cash_before
    assert any(h.symbol == "TCS" and h.quantity == 2 for h in book_after.holdings_swing)