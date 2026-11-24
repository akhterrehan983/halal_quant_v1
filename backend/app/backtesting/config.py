from datetime import date, timedelta

from app.backtesting.schemas import BacktestConfig

DEFAULT_BACKTEST = BacktestConfig(
    name="demo_universe_swing",
    start_date=date.today() - timedelta(days=180),
    end_date=date.today() - timedelta(days=30),
)