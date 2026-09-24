"""Filesystem path resolution for ProxyAtlas.

All runtime data (database, logs, exports, reports, keys, config) lives under
a single platform-appropriate data directory, overridable with the
``PROXYATLAS_DATA_DIR`` environment variable. Kept dependency-free so it can
be imported very early during startup.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

APP_DIRNAME = "ProxyAtlas"


def _platform_data_root() -> Path:
    """Return the base per-user data directory for the current platform."""
    override = os.environ.get("PROXYATLAS_DATA_DIR")
    if override:
        return Path(override).expanduser()

    if sys.platform.startswith("win"):
        base = os.environ.get("APPDATA") or (Path.home() / "AppData" / "Roaming")
        return Path(base) / APP_DIRNAME
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_DIRNAME
    # Linux / other: respect XDG.
    base = os.environ.get("XDG_DATA_HOME") or (Path.home() / ".local" / "share")
    return Path(base) / APP_DIRNAME


class AppPaths:
    """Resolved application paths, created on demand."""

    def __init__(self, root: Path | None = None) -> None:
        self.data_dir: Path = root or _platform_data_root()
        self.logs_dir: Path = self.data_dir / "logs"
        self.exports_dir: Path = self.data_dir / "exports"
        self.reports_dir: Path = self.data_dir / "reports"
        self.config_path: Path = self.data_dir / "config.json"
        self.database_path: Path = self.data_dir / "proxyatlas.sqlite"
        self.key_path: Path = self.data_dir / ".secret.key"

    def ensure(self) -> "AppPaths":
        """Create all directories (idempotent)."""
        for directory in (self.data_dir, self.logs_dir, self.exports_dir, self.reports_dir):
            directory.mkdir(parents=True, exist_ok=True)
        return self

    @property
    def database_url(self) -> str:
        return f"sqlite:///{self.database_path}"


def package_root() -> Path:
    """Path to the ``app`` package directory (works frozen and unfrozen)."""
    if getattr(sys, "frozen", False):  # PyInstaller bundle
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent.parent


def assets_dir() -> Path:
    """Path to bundled assets (logo, icons, images)."""
    root = package_root()
    # In a PyInstaller bundle assets sit beside the package; in dev they are
    # one level up from ``app``.
    candidate = root / "assets"
    if candidate.exists():
        return candidate
    return root.parent / "assets"


# Default singleton used throughout the app.
paths = AppPaths()
