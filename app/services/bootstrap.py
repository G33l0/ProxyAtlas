"""Application bootstrap / startup sequence.

Implements the first-launch and later-launch steps: create directories,
configure logging, run migrations, load settings, initialize the credential
cipher, build managers and register providers, and seed default discovery
sources on first run. Returns a fully wired :class:`AppContext`.
"""

from __future__ import annotations

import logging

from app.core.config import Settings
from app.core.logging_config import configure_logging
from app.core.paths import AppPaths
from app.core.paths import paths as default_paths
from app.database import repository as repo
from app.database.engine import Database
from app.database.migrator import run_migrations
from app.discovery.manager import DiscoveryManager
from app.intelligence.manager import IntelligenceManager
from app.services.app_context import AppContext
from app.services.credentials import CredentialCipher
from app.services.jobs import job_manager


def bootstrap(app_paths: AppPaths | None = None) -> AppContext:
    """Run the full startup sequence and return the application context."""
    app_paths = (app_paths or default_paths).ensure()

    settings = Settings.load(app_paths.config_path)

    log_cfg = settings.section("logging")
    configure_logging(
        app_paths.logs_dir,
        level=log_cfg.get("level", "INFO"),
        max_bytes=int(log_cfg.get("max_bytes", 2_000_000)),
        backup_count=int(log_cfg.get("backup_count", 5)),
    )
    logger = logging.getLogger(__name__)
    logger.info("Starting ProxyAtlas bootstrap")

    from app.services.storage import resolve_storage

    storage = resolve_storage(settings, app_paths)
    database_url = storage.url
    if storage.used_fallback:
        logger.warning(storage.message)
    else:
        logger.info(storage.message or "Using default database location")
    first_run = not storage.path.exists()

    run_migrations(database_url)
    database = Database(database_url)

    cipher = CredentialCipher.from_key_file(app_paths.key_path)

    discovery = DiscoveryManager()

    intelligence = IntelligenceManager()
    intelligence.register_defaults(settings.get("intelligence", "providers", {}) or {})

    ctx = AppContext(
        paths=app_paths,
        settings=settings,
        database=database,
        cipher=cipher,
        discovery=discovery,
        intelligence=intelligence,
        jobs=job_manager,
        database_path=str(storage.path),
        storage_notice=storage.message if storage.used_fallback else "",
    )

    if first_run:
        _seed_defaults(ctx)

    logger.info("Bootstrap complete (first_run=%s)", first_run)
    return ctx


def _seed_defaults(ctx: AppContext) -> None:
    """Seed default (disabled) discovery sources on first launch."""
    with ctx.database.session() as session:
        existing = {s.name for s in repo.list_sources(session)}
        for src in ctx.discovery.default_sources():
            if src["name"] in existing:
                continue
            repo.upsert_source(
                session,
                name=src["name"],
                source_type=src["source_type"],
                provider=src["provider"],
                config=src["config"],
                enabled=src["enabled"],
            )
        repo.add_audit(session, "first_run", "Seeded default sources")


def is_database_empty(ctx: AppContext) -> bool:
    with ctx.database.session() as session:
        return repo.count_proxies(session) == 0
