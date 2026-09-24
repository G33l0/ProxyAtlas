"""ipinfo.io intelligence provider (optional token).

Configured with an API token under Settings > Providers or the ``IPINFO_TOKEN``
environment variable. Without a token it still works at a reduced rate limit.
"""

from __future__ import annotations

import os
from typing import Any

from app.core.models import IntelligenceResult
from app.intelligence.asn import normalize_asn
from app.intelligence.base import IntelligenceProvider
from app.intelligence.geoip import country_name, is_private_or_reserved
from app.intelligence.isp import clean_org


class IpInfoProvider(IntelligenceProvider):
    kind = "geoip"
    priority = 60

    def __init__(self) -> None:
        self._config: dict[str, Any] = {}
        self._token = os.environ.get("IPINFO_TOKEN", "")

    def name(self) -> str:
        return "ipinfo"

    def description(self) -> str:
        return "ipinfo.io geolocation and ASN lookup (optional API token)."

    def configure(self, config: dict[str, Any]) -> None:
        self._config = dict(config or {})
        self._token = config.get("token") or os.environ.get("IPINFO_TOKEN", "")

    def validate_configuration(self) -> tuple[bool, str]:
        return True, "Token optional; higher limits when set."

    async def lookup(self, ip: str) -> IntelligenceResult:
        result = IntelligenceResult(ip=ip, provider=self.name())
        if is_private_or_reserved(ip):
            return result
        import httpx

        url = f"https://ipinfo.io/{ip}/json"
        headers = {"Authorization": f"Bearer {self._token}"} if self._token else {}
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                resp = await client.get(url, headers=headers)
            data = resp.json()
        except Exception:  # noqa: BLE001
            return result

        if not isinstance(data, dict) or data.get("error"):
            return result

        result.country_code = data.get("country")
        result.country = country_name(data.get("country"))
        result.region = data.get("region")
        result.city = data.get("city")
        result.timezone = data.get("timezone")
        result.organization = clean_org(data.get("org"))
        result.asn = normalize_asn(data.get("org"))
        result.isp = clean_org(data.get("org"))
        loc = data.get("loc")
        if loc and "," in loc:
            try:
                lat, lon = loc.split(",", 1)
                result.latitude = float(lat)
                result.longitude = float(lon)
            except ValueError:
                pass
        return result
