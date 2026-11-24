from fastapi import APIRouter

from app.core.config import settings

router = APIRouter(tags=["health"])


@router.get("/health")
def health_v1():
    return {
        "status": "ok",
        "app": settings.app_name,
        "version": settings.version,
        "environment": settings.environment,
        "database_enabled": settings.database_enabled,
        "demo_mode": not settings.database_enabled,
        "data_notice": "Synthetic demo data unless imported via CSV or persisted market data.",
    }