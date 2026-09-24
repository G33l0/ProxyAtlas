"""Programmatic Alembic runner.

Runs migrations to ``head`` against the resolved database URL during startup,
falling back to ``create_all`` if Alembic is unavailable. This keeps the schema
current whether launched from source or a frozen executable.
"""

from __future__ import annotations

import logging
from pathlib import Path

from app.core.paths import package_root

logger = logging.getLogger(__name__)


def _migrations_dir():
    """Locate the migrations directory in both dev and frozen layouts."""
    root = package_root()
    candidates = [
        root / "database" / "migrations",        # dev: package_root() == app/
        root / "app" / "database" / "migrations",  # frozen: _MEIPASS/app/...
    ]
    for candidate in candidates:
        if (candidate / "env.py").exists():
            return candidate
    return candidates[0]


def _alembic_config(database_url: str):
    from alembic.config import Config

    ini_path = package_root().parent / "alembic.ini"
    cfg = Config(str(ini_path)) if ini_path.exists() else Config()
    cfg.set_main_option("script_location", str(_migrations_dir()))
    cfg.set_main_option("sqlalchemy.url", database_url)
    return cfg


def run_migrations(database_url: str) -> bool:
    """Upgrade the database to head. Returns True on success via Alembic."""
    try:
        from alembic import command

        cfg = _alembic_config(database_url)
        command.upgrade(cfg, "head")
        logger.info("Database migrated to head")
        return True
    except Exception as exc:  # pragma: no cover - fallback path
        logger.warning("Alembic migration failed (%s); using create_all fallback", exc)
        from app.database.engine import Database

        Database(database_url).create_all()
        return False


def current_revision(database_url: str) -> str | None:
    try:
        from alembic.migration import MigrationContext
        from sqlalchemy import create_engine

        engine = create_engine(database_url)
        with engine.connect() as conn:
            ctx = MigrationContext.configure(conn)
            return ctx.get_current_revision()
    except Exception:  # pragma: no cover
        return None


def stamp_head(database_url: str) -> None:
    """Mark an existing (create_all) DB as being at head without re-running."""
    try:
        from alembic import command

        command.stamp(_alembic_config(database_url), "head")
    except Exception as exc:  # pragma: no cover
        logger.debug("Could not stamp head: %s", exc)


def ensure_alembic_ini(project_root: Path) -> None:  # pragma: no cover - helper
    """No-op placeholder kept for symmetry / future use."""
    return None
