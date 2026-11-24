from collections.abc import Generator

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db as _get_db


def get_settings():
    return settings


def get_db_session() -> Generator[Session, None, None]:
    yield from _get_db()