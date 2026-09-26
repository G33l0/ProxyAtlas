"""Shared handles (paths, settings, db, cipher, the managers) passed around the
UI, CLI and workers. Built once in bootstrap().
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.config import Settings
from app.core.paths import AppPaths
from app.database.engine import Database
from app.discovery.manager import DiscoveryManager
from app.intelligence.manager import IntelligenceManager
from app.services.credentials import CredentialCipher
from app.services.jobs import JobManager


@dataclass
class AppContext:
    paths: AppPaths
    settings: Settings
    database: Database
    cipher: CredentialCipher
    discovery: DiscoveryManager
    intelligence: IntelligenceManager
    jobs: JobManager
    database_path: str = ""
    storage_notice: str = ""

    def testing_settings(self) -> dict:
        """Flattened testing settings used by the validation pipeline."""
        section = self.settings.section("testing")
        return {
            "timeout": section.get("timeout", 12.0),
            "concurrency": section.get("concurrency", 40),
            "retries": section.get("retries", 0),
            "retry_backoff": section.get("retry_backoff", 1.5),
            "protocol_autodetect": section.get("protocol_autodetect", False),
            "validation_endpoints": section.get("validation_endpoints", []),
            "judge_endpoint": section.get("judge_endpoint"),
            "default_profile": section.get("default_profile", "standard"),
        }

    def custom_profiles(self) -> dict[str, dict]:
        return self.settings.get("testing", "custom_profiles", {}) or {}

    def intelligence_enabled(self) -> bool:
        return bool(self.settings.get("intelligence", "enabled", True))
