from fastapi import APIRouter

from app.api.v1 import backtests, execution, health, market, market_data, portfolio, regime, risk, shariah, signals, strategies, stocks

api_v1_router = APIRouter(prefix="/api/v1")
api_v1_router.include_router(health.router)
api_v1_router.include_router(stocks.router)
api_v1_router.include_router(market.router)
api_v1_router.include_router(market_data.router)
api_v1_router.include_router(strategies.router)
api_v1_router.include_router(regime.router)
api_v1_router.include_router(signals.router)
api_v1_router.include_router(portfolio.router)
api_v1_router.include_router(risk.router)
api_v1_router.include_router(shariah.router)
api_v1_router.include_router(execution.router)
api_v1_router.include_router(backtests.router)