"""Application configuration.

Settings are persisted to a JSON file in the data directory. Provider
credentials are *not* stored here in plaintext — they are handled by
:mod:`app.services.credentials`. Defaults are defined once in
:data:`DEFAULT_SETTINGS` so the Settings UI and the engines share one source
of truth.
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.core.paths import AppPaths
from app.core.paths import paths as default_paths

DEFAULT_SETTINGS: dict[str, Any] = {
    "general": {
        "auto_recover_jobs": True,
        "confirm_destructive": True,
        "results_page_size": 200,
    },
    "appearance": {
        "theme": "dark",  # light | dark | midnight
    },
    "discovery": {
        "auto_dedupe": True,
        "auto_validate_after_discovery": False,
        "default_feed_timeout": 20.0,
    },
    "testing": {
        "timeout": 12.0,
        "concurrency": 40,
        "retries": 0,  # opt-in; >0 retries transient failures with backoff
        "retry_backoff": 1.5,
        "protocol_autodetect": False,
        "default_profile": "standard",
        "validation_endpoints": [
            "https://httpbin.org/ip",
            "https://api.ipify.org?format=json",
            "https://icanhazip.com",
        ],
        "judge_endpoint": "https://httpbin.org/get",
    },
    "monitoring": {
        "default_interval_minutes": 30,
        "history_retention_days": 90,
    },
    "intelligence": {
        "enabled": True,
        "geoip_provider": "builtin",
        "reverse_dns": True,
    },
    "database": {
        "path": "",  # empty -> default location
        "batch_size": 500,
    },
    "reports": {
        "output_dir": "",  # empty -> default reports dir
    },
    "logging": {
        "level": "INFO",
        "max_bytes": 2_000_000,
        "backup_count": 5,
    },
}


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge ``override`` into a copy of ``base``."""
    result = dict(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


@dataclass
class Settings:
    """Mutable settings object backed by a JSON file."""

    path: Path
    data: dict[str, Any] = field(default_factory=dict)
    _lock: threading.RLock = field(default_factory=threading.RLock, repr=False)

    @classmethod
    def load(cls, config_path: Path | None = None) -> Settings:
        cfg_path = config_path or default_paths.config_path
        data: dict[str, Any] = {}
        if cfg_path.exists():
            try:
                data = json.loads(cfg_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                # Corrupt config -> fall back to defaults, keep a backup.
                try:
                    cfg_path.rename(cfg_path.with_suffix(".corrupt"))
                except OSError:
                    pass
                data = {}
        merged = _deep_merge(DEFAULT_SETTINGS, data)
        return cls(path=cfg_path, data=merged)

    def get(self, section: str, key: str, default: Any = None) -> Any:
        with self._lock:
            return self.data.get(section, {}).get(key, default)

    def section(self, section: str) -> dict[str, Any]:
        with self._lock:
            return dict(self.data.get(section, {}))

    def set(self, section: str, key: str, value: Any) -> None:
        with self._lock:
            self.data.setdefault(section, {})[key] = value

    def update_section(self, section: str, values: dict[str, Any]) -> None:
        with self._lock:
            self.data.setdefault(section, {}).update(values)

    def reset_to_defaults(self) -> None:
        with self._lock:
            self.data = json.loads(json.dumps(DEFAULT_SETTINGS))

    def save(self) -> None:
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.data, indent=2, sort_keys=True), encoding="utf-8")
            tmp.replace(self.path)

    # Convenience accessors used across the app -------------------------------

    # Database location is resolved by app.services.storage.resolve_storage,
    # which also handles external-drive validation and fallback.

    def resolved_reports_dir(self, app_paths: AppPaths) -> Path:
        custom = self.get("reports", "output_dir", "") or ""
        if custom:
            p = Path(custom).expanduser()
            p.mkdir(parents=True, exist_ok=True)
            return p
        return app_paths.reports_dir
