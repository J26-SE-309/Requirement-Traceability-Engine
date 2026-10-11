"""Access to this component's own PostgreSQL database."""

from collections.abc import Iterator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    """Base class for this service's tables."""


engine = create_engine(get_settings().database_url, pool_pre_ping=True, connect_args={"connect_timeout": 2})
SessionLocal = sessionmaker(bind=engine, autoflush=False)


def get_session() -> Iterator[Session]:
    """FastAPI dependency: one database session per request."""
    with SessionLocal() as session:
        yield session


import socket
import time
from urllib.parse import urlparse

_db_last_checked = 0.0
_db_last_status = False


def _is_port_open(host: str, port: int, timeout: float = 0.05) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except Exception:
        return False


def database_ok() -> bool:
    global _db_last_checked, _db_last_status
    now = time.time()
    if not _db_last_status and (now - _db_last_checked < 30.0):
        return False
    if _db_last_status and (now - _db_last_checked < 10.0):
        return True

    _db_last_checked = now

    try:
        db_url = get_settings().database_url
        parsed = urlparse(db_url.replace("+psycopg", "").replace("+asyncpg", ""))
        host = parsed.hostname or "127.0.0.1"
        port = parsed.port or 5432
        if not _is_port_open(host, port, timeout=0.05):
            _db_last_status = False
            return False
    except Exception:
        _db_last_status = False
        return False

    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        _db_last_status = True
        return True
    except Exception:
        _db_last_status = False
        return False

