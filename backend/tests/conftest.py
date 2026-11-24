"""Pytest defaults: in-memory demo mode even when project root .env has DATABASE_URL."""

from __future__ import annotations

import pytest
from sqlalchemy import delete, select

from app.core.config import get_settings

# Modules that bind `from app.core.config import settings` at import time
_SETTINGS_PATCH_TARGETS = (
    "app.core.config",
    "app.portfolio.store",
    "app.execution.store",
    "app.signals.persistence",
    "app.backtesting.store",
    "app.shariah.store",
    "app.shariah.snapshots",
    "app.market_data.repository",
    "app.market_data.persistence",
    "app.market_data.ingestion",
    "app.market_data.quality",
    "app.api.v1.health",
    "app.api.v1.market_data",
    "app.api.v1.portfolio",
    "app.api.legacy",
    "app.portfolio.service",
    "app.api.dependencies",
)


def _postgres_test(request: pytest.FixtureRequest) -> bool:
    return request.node.get_closest_marker("postgres") is not None


def reset_persisted_default_rows() -> None:
    from app.core.database import SessionLocal
    from app.models.portfolio_risk import PortfolioBook
    from app.models.shariah_execution import ExecutionStateRow

    if SessionLocal is None:
        return
    with SessionLocal() as session:
        session.execute(delete(PortfolioBook).where(PortfolioBook.name == "default"))
        session.execute(delete(ExecutionStateRow).where(ExecutionStateRow.name == "default"))
        session.commit()


def _apply_demo_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "")
    get_settings.cache_clear()
    demo_settings = get_settings()
    for target in _SETTINGS_PATCH_TARGETS:
        monkeypatch.setattr(f"{target}.settings", demo_settings, raising=False)
    import app.core.database as db

    monkeypatch.setattr(db, "engine", None, raising=False)
    monkeypatch.setattr(db, "SessionLocal", None, raising=False)


@pytest.fixture(autouse=True)
def isolate_demo_mode(request, monkeypatch):
    """Force demo persistence for all tests except those marked ``postgres``."""
    if _postgres_test(request):
        yield
        return
    _apply_demo_settings(monkeypatch)
    yield
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def reset_in_memory_stores():
    from app.execution import store as exec_store
    from app.portfolio import store as portfolio_store

    portfolio_store._BOOK_MEM = None  # noqa: SLF001
    exec_store._STATE = exec_store._empty()  # noqa: SLF001
    yield


@pytest.fixture(autouse=True)
def reset_persisted_stores_when_postgres(request):
    if not _postgres_test(request):
        yield
        return
    reset_persisted_default_rows()
    yield


@pytest.fixture()
def sqlite_session():
    """Isolated in-memory DB for persistence unit tests."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.core.database import Base

    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)


def pytest_configure(config):
    config.addinivalue_line("markers", "postgres: test requires DATABASE_URL and live PostgreSQL")