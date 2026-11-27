from fastapi import APIRouter

from app.api.v2 import backtests

api_v2_router = APIRouter(prefix="/api/v2")
api_v2_router.include_router(backtests.router)
