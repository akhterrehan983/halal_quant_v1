from datetime import date, timedelta

import pytest

from app.backtesting.data import index_as_of, next_session_row, slice_as_of
from app.backtesting.execution import fill_market_next_session
from app.backtesting.monte_carlo import monte_carlo_trade_returns
from app.backtesting.schemas import BacktestConfig, CompletedTrade, ShariahBacktestMode
from app.backtesting.simulator import run_backtest
from app.data.sample_data import make_history


def test_slice_no_future():
    df = make_history("BT", periods=100)
    as_of = df.iloc[50].date.date() if hasattr(df.iloc[50].date, "date") else df.iloc[50].date
    sub = slice_as_of(df, as_of)
    assert len(sub) == 51


def test_next_session_after_signal():
    from app.market_data.repository import get_history_dataframe

    df = get_history_dataframe("TCS", limit=120)
    sig_d = __import__("pandas").to_datetime(df.iloc[40]["date"]).date()
    row = next_session_row(df, sig_d)
    assert row is not None
    fill = fill_market_next_session("TCS", sig_d, 10)
    assert fill is not None
    _px, td = fill
    assert td > sig_d


def test_backtest_runs_demo():
    end = date.today() - timedelta(days=5)
    start = end - timedelta(days=45)
    cfg = BacktestConfig(
        name="test_bt",
        start_date=start,
        end_date=end,
        horizon="swing",
        shariah_mode=ShariahBacktestMode.RESEARCH_ONLY,
        max_positions=2,
    )
    run = run_backtest(cfg)
    assert run.status.value == "COMPLETED"
    assert len(run.equity_curve) > 0


def test_monte_carlo_seed():
    trades = [
        CompletedTrade(
            symbol="X",
            strategy="u",
            horizon="swing",
            entry_date=date.today(),
            entry_price=100,
            quantity=1,
            net_pnl=10,
        ),
        CompletedTrade(
            symbol="Y",
            strategy="u",
            horizon="swing",
            entry_date=date.today(),
            entry_price=100,
            quantity=1,
            net_pnl=-5,
        ),
    ]
    a = monte_carlo_trade_returns(trades, simulations=100, seed=1)
    b = monte_carlo_trade_returns(trades, simulations=100, seed=1)
    assert a["final_pnl_p50"] == b["final_pnl_p50"]


def test_backtest_api():
    from fastapi.testclient import TestClient
    from app.main import app

    end = date.today() - timedelta(days=5)
    start = end - timedelta(days=40)
    res = TestClient(app).post(
        "/api/v1/backtests?run_now=true",
        json={
            "name": "api_bt",
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "horizon": "swing",
            "shariah_mode": "RESEARCH_ONLY",
        },
    )
    assert res.status_code == 200
    assert res.json()["status"] == "COMPLETED"