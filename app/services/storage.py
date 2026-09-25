"""Database storage location management (incl. external drives).

ProxyAtlas can keep its SQLite database on an external drive or any custom
folder so the machine's system disk isn't consumed by large proxy datasets.
This module resolves and validates that location, falls back gracefully when an
external drive is not mounted, and can relocate an existing database.

A custom database path may be given as a directory (the DB file name is
appended) or a full ``*.sqlite`` file path.
"""

from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass
from pathlib import Path

from app.core.config import Settings
from app.core.paths import AppPaths

logger = logging.getLogger(__name__)

DB_FILENAME = "proxyatlas.sqlite"
# SQLite WAL/SHM sidecar files that must travel with the main database file.
_SIDECARS = ("-wal", "-shm", "-journal")


@dataclass
class ResolvedStorage:
    """Outcome of resolving the configured database location."""

    path: Path
    url: str
    is_custom: bool
    used_fallback: bool = False
    message: str = ""


def normalize_db_path(raw: str) -> Path:
    """Turn a user-provided path into a concrete ``*.sqlite`` file path.

    A directory (existing, or ending with a separator, or extension-less)
    receives the default DB filename; a file path is used as-is.
    """
    p = Path(raw).expanduser()
    if p.is_dir() or raw.endswith(("/", "\\")) or p.suffix == "":
        return p / DB_FILENAME
    return p


def validate_db_location(raw: str) -> tuple[bool, str]:
    """Check whether a custom DB location is usable (parent writable).

    Returns ``(ok, message)``. Does not create the database, only verifies the
    target directory exists (or can be created) and is writable — the key check
    for an external drive that may be unmounted.
    """
    if not raw or not raw.strip():
        return True, "Using default location"
    try:
        db_path = normalize_db_path(raw.strip())
        parent = db_path.parent
        if not parent.exists():
            try:
                parent.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                return False, f"Cannot create folder (drive not mounted?): {exc}"
        # Probe writability without leaving artifacts.
        probe = parent / ".proxyatlas_write_test"
        try:
            probe.write_text("ok", encoding="utf-8")
            probe.unlink()
        except OSError as exc:
            return False, f"Folder is not writable: {exc}"
        return True, f"Database will be stored at {db_path}"
    except Exception as exc:  # noqa: BLE001 - defensive
        return False, f"Invalid path: {exc}"


def resolve_storage(settings: Settings, app_paths: AppPaths) -> ResolvedStorage:
    """Resolve the database location, falling back to default if unusable.

    A configured external/custom path that is currently unavailable (e.g. the
    drive is unplugged) does not crash startup — the app falls back to the
    default location and reports it via ``ResolvedStorage.message``.
    """
    custom = (settings.get("database", "path", "") or "").strip()
    if not custom:
        return ResolvedStorage(
            path=app_paths.database_path, url=app_paths.database_url, is_custom=False
        )

    ok, message = validate_db_location(custom)
    if not ok:
        logger.warning("Custom database location unavailable (%s); using default", message)
        return ResolvedStorage(
            path=app_paths.database_path,
            url=app_paths.database_url,
            is_custom=True,
            used_fallback=True,
            message=f"Configured database location unavailable: {message}. "
            f"Using default location instead.",
        )

    db_path = normalize_db_path(custom)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return ResolvedStorage(
        path=db_path,
        url=f"sqlite:///{db_path}",
        is_custom=True,
        message=f"Using database at {db_path}",
    )


def relocate_database(
    current_path: Path, destination_raw: str, settings: Settings
) -> tuple[bool, str]:
    """Copy an existing database (and WAL/SHM sidecars) to a new location.

    Updates the ``database.path`` setting on success. The application must
    reopen the database (typically on restart) for the change to take effect.
    Returns ``(ok, message)``.
    """
    ok, message = validate_db_location(destination_raw)
    if not ok:
        return False, message
    dest = normalize_db_path(destination_raw.strip())
    dest.parent.mkdir(parents=True, exist_ok=True)

    if dest.resolve() == current_path.resolve():
        return False, "Destination is the same as the current location"

    try:
        if current_path.exists():
            shutil.copy2(current_path, dest)
            for suffix in _SIDECARS:
                side = current_path.with_name(current_path.name + suffix)
                if side.exists():
                    shutil.copy2(side, dest.with_name(dest.name + suffix))
        settings.set("database", "path", str(dest))
        settings.save()
        return True, f"Database copied to {dest}. Restart to use the new location."
    except OSError as exc:
        return False, f"Failed to relocate database: {exc}"
