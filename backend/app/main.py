from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.legacy import router as legacy_router
from app.api.v1.router import api_v1_router
from app.core.config import settings
from app.core.exceptions import HalalQuantError, halal_quant_exception_handler
from app.core.logging import setup_logging

setup_logging()

app = FastAPI(
    title=settings.app_name,
    version=settings.version,
    description="Halal Quant V1 — research and paper-trading platform (modular monolith)",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_exception_handler(HalalQuantError, halal_quant_exception_handler)
app.include_router(legacy_router)
app.include_router(api_v1_router)