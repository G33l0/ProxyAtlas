"""Offline built-in intelligence provider.

Requires no external service or API key. It performs a reverse-DNS lookup and
derives hosting indicators from the PTR record, plus private-range detection.
This guarantees the pipeline always has *some* intelligence even with no
network providers configured.
"""

from __future__ import annotations

import asyncio
import socket
from typing import Any

from app.core.models import IntelligenceResult
from app.intelligence.asn import DATACENTER_KEYWORDS, match_keywords
from app.intelligence.base import IntelligenceProvider
from app.intelligence.geoip import is_private_or_reserved


class BuiltinIntelligenceProvider(IntelligenceProvider):
    """Reverse-DNS + heuristics; always available, no configuration."""

    kind = "network"
    priority = 200  # runs after online providers so it only fills gaps

    def __init__(self) -> None:
        self._config: dict[str, Any] = {}

    def name(self) -> str:
        return "builtin"

    def description(self) -> str:
        return "Offline reverse-DNS and hosting heuristics (no API key required)."

    async def lookup(self, ip: str) -> IntelligenceResult:
        result = IntelligenceResult(ip=ip, provider=self.name())
        if is_private_or_reserved(ip):
            result.evidence["note"] = "private/reserved address"
            return result

        ptr = await self._reverse_dns(ip)
        if ptr:
            result.reverse_dns = ptr
            dc = match_keywords(ptr, DATACENTER_KEYWORDS)
            if dc:
                result.hosting = True
                result.evidence["ptr_hosting_keywords"] = dc
        return result

    async def _reverse_dns(self, ip: str) -> str | None:
        if not self._config.get("reverse_dns", True):
            return None
        loop = asyncio.get_running_loop()
        try:
            host, _, _ = await asyncio.wait_for(
                loop.run_in_executor(None, socket.gethostbyaddr, ip), timeout=4.0
            )
            return host
        except (socket.herror, socket.gaierror, OSError, asyncio.TimeoutError):
            return None
