from collections.abc import Generator
from typing import Any

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

SQLITE_BUSY_TIMEOUT_MS = 5_000
SQLITE_WAL_AUTOCHECKPOINT_PAGES = 1_000
SQLITE_JOURNAL_SIZE_LIMIT_BYTES = 64 * 1024 * 1024


def _configure_sqlite_connection(dbapi_connection: Any, database_url: str) -> None:
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute(f"PRAGMA busy_timeout={SQLITE_BUSY_TIMEOUT_MS}")
        if ":memory:" not in database_url:
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.execute(f"PRAGMA wal_autocheckpoint={SQLITE_WAL_AUTOCHECKPOINT_PAGES}")
            cursor.execute(f"PRAGMA journal_size_limit={SQLITE_JOURNAL_SIZE_LIMIT_BYTES}")
    finally:
        cursor.close()


def create_database_engine(database_url: str) -> Engine:
    """Create an engine from an already-resolved URL without reading process settings."""
    connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    database_engine = create_engine(
        database_url,
        pool_pre_ping=True,
        connect_args=connect_args,
    )
    if database_url.startswith("sqlite"):

        @event.listens_for(database_engine, "connect")
        def _on_sqlite_connect(dbapi_connection: Any, _connection_record: Any) -> None:
            _configure_sqlite_connection(dbapi_connection, database_url)

    return database_engine


settings = get_settings()
engine = create_database_engine(settings.database_url)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db_session() -> Generator[Session, None, None]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
