"""Intelligence manager: runs providers and merges results.

Providers are executed in priority order; each is isolated so a failure only
records a provider error and never stops the lookup. Non-empty fields from
earlier (higher priority) providers win; later providers fill gaps.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from app.core.models import IntelligenceResult
from app.intelligence.base import IntelligenceProvider, ProviderStatus
from app.intelligence.geoip import country_name, is_private_or_reserved
from app.intelligence.providers.builtin import BuiltinIntelligenceProvider
from app.intelligence.providers.ipapi import IpApiProvider
from app.intelligence.providers.ipinfo import IpInfoProvider

logger = logging.getLogger(__name__)


class IntelligenceManager:
    """Owns and orchestrates intelligence providers."""

    def __init__(self) -> None:
        self._providers: list[IntelligenceProvider] = []
        self._status: dict[str, ProviderStatus] = {}

    def register(self, provider: IntelligenceProvider, enabled: bool = True) -> None:
        self._providers.append(provider)
        self._providers.sort(key=lambda p: p.priority)
        self._status[provider.name()] = ProviderStatus(
            name=provider.name(), kind=provider.kind, enabled=enabled
        )

    def register_defaults(self, config: dict | None = None) -> None:
        config = config or {}
        # Offline MMDB provider runs first (priority 10) when configured.
        from app.intelligence.providers.mmdb import MmdbProvider

        mmdb = MmdbProvider()
        mmdb_cfg = config.get("mmdb", {})
        mmdb.configure(mmdb_cfg)
        ipapi = IpApiProvider()
        ipapi.configure(config.get("ip-api", {}))
        ipinfo = IpInfoProvider()
        ipinfo.configure(config.get("ipinfo", {}))
        builtin = BuiltinIntelligenceProvider()
        builtin.configure(config.get("builtin", {"reverse_dns": True}))
        # Enable MMDB only when a database path is configured.
        mmdb_enabled = bool(mmdb_cfg.get("city_db") or mmdb_cfg.get("country_db") or mmdb_cfg.get("asn_db"))
        self.register(mmdb, enabled=mmdb_cfg.get("enabled", mmdb_enabled))
        # ipinfo disabled by default unless a token is configured.
        self.register(ipapi, enabled=config.get("ip-api", {}).get("enabled", True))
        self.register(ipinfo, enabled=config.get("ipinfo", {}).get("enabled", False))
        self.register(builtin, enabled=True)

    def providers(self) -> list[IntelligenceProvider]:
        return list(self._providers)

    def status(self) -> list[ProviderStatus]:
        return list(self._status.values())

    def set_enabled(self, name: str, enabled: bool) -> None:
        if name in self._status:
            self._status[name].enabled = enabled

    async def lookup(self, ip: str) -> IntelligenceResult:
        merged = IntelligenceResult(ip=ip)
        if not ip or is_private_or_reserved(ip):
            merged.evidence["note"] = "private/reserved or empty IP"
            return merged

        for provider in self._providers:
            st = self._status.get(provider.name())
            if st and not st.enabled:
                continue
            try:
                res = await provider.lookup(ip)
                self._merge(merged, res)
                if st:
                    st.last_success = datetime.now(timezone.utc).isoformat(timespec="seconds")
                    st.last_error = None
            except Exception as exc:  # noqa: BLE001 - provider isolation
                logger.warning("Intelligence provider %s failed: %s", provider.name(), exc)
                if st:
                    st.last_error = str(exc)[:200]

        if merged.country_code and not merged.country:
            merged.country = country_name(merged.country_code)
        return merged

    @staticmethod
    def _merge(target: IntelligenceResult, src: IntelligenceResult) -> None:
        for field_name in (
            "country", "country_code", "region", "city", "latitude", "longitude",
            "timezone", "asn", "isp", "organization", "reverse_dns",
        ):
            if getattr(target, field_name) in (None, "") and getattr(src, field_name) not in (None, ""):
                setattr(target, field_name, getattr(src, field_name))
        if target.hosting is None and src.hosting is not None:
            target.hosting = src.hosting
        # Merge evidence (source-tagged).
        if src.evidence:
            target.evidence[src.provider or "provider"] = src.evidence
