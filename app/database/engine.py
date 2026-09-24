"""Database engine and session management.

Provides a thread-safe :class:`Database` wrapper around a SQLAlchemy engine
with SQLite tuned for concurrent read/write (WAL, foreign keys, busy timeout).
Sessions are short-lived and obtained via a context manager.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.exceptions import DatabaseError
from app.database.models import Base

logger = logging.getLogger(__name__)


def _configure_sqlite(dbapi_connection, _record) -> None:
    """Apply pragmas to every new SQLite connection."""
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA busy_timeout=10000")
    finally:
        cursor.close()


class Database:
    """Owns the engine and produces sessions."""

    def __init__(self, url: str) -> None:
        self.url = url
        self.engine: Engine = create_engine(
            url,
            future=True,
            echo=False,
            connect_args={"check_same_thread": False, "timeout": 15},
        )
        if url.startswith("sqlite"):
            event.listen(self.engine, "connect", _configure_sqlite)
        self._session_factory = sessionmaker(
            bind=self.engine, expire_on_commit=False, class_=Session, future=True
        )

    def create_all(self) -> None:
        """Create all tables (used when Alembic is unavailable/first run)."""
        try:
            Base.metadata.create_all(self.engine)
        except Exception as exc:  # pragma: no cover - defensive
            raise DatabaseError(f"Failed to create schema: {exc}") from exc

    @contextmanager
    def session(self) -> Iterator[Session]:
        """Transactional session scope."""
        session = self._session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def new_session(self) -> Session:
        """Return a raw session the caller must manage."""
        return self._session_factory()

    def dispose(self) -> None:
        self.engine.dispose()


_default_db: Database | None = None


def init_database(url: str) -> Database:
    global _default_db
    _default_db = Database(url)
    return _default_db


def get_database() -> Database:
    if _default_db is None:
        raise DatabaseError("Database not initialized. Call init_database() first.")
    return _default_db
