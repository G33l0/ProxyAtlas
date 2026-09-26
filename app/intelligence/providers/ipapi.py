"""ip-api.com lookup (free, no key): geo, ASN, ISP, org and a hosting flag.
Network errors are swallowed and surfaced through provider status.
"""

from __future__ import annotations

from typing import Any

from app.core.models import IntelligenceResult
from app.intelligence.asn import normalize_asn
from app.intelligence.base import IntelligenceProvider
from app.intelligence.geoip import is_private_or_reserved
from app.intelligence.isp import clean_org

_FIELDS = "status,message,country,countryCode,regionName,city,lat,lon,timezone,isp,org,as,hosting,mobile,query"


class IpApiProvider(IntelligenceProvider):
    kind = "geoip"
    priority = 50

    def __init__(self) -> None:
        self._config: dict[str, Any] = {}
        self._base = "http://ip-api.com/json/"

    def name(self) -> str:
        return "ip-api"

    def description(self) -> str:
        return "ip-api.com free geolocation, ASN and ISP lookup."

    def configure(self, config: dict[str, Any]) -> None:
        self._config = dict(config or {})
        if config.get("base_url"):
            self._base = str(config["base_url"])

    async def lookup(self, ip: str) -> IntelligenceResult:
        result = IntelligenceResult(ip=ip, provider=self.name())
        if is_private_or_reserved(ip):
            return result
        import httpx

        url = f"{self._base}{ip}?fields={_FIELDS}"
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                resp = await client.get(url)
            data = resp.json()
        except Exception:  # noqa: BLE001
            return result

        if not isinstance(data, dict) or data.get("status") != "success":
            return result

        result.country = data.get("country")
        result.country_code = data.get("countryCode")
        result.region = data.get("regionName")
        result.city = data.get("city")
        result.latitude = data.get("lat")
        result.longitude = data.get("lon")
        result.timezone = data.get("timezone")
        result.isp = data.get("isp")
        result.organization = clean_org(data.get("org"))
        result.asn = normalize_asn(data.get("as"))
        result.hosting = bool(data.get("hosting"))
        result.evidence["mobile_flag"] = bool(data.get("mobile"))
        result.evidence["hosting_flag"] = bool(data.get("hosting"))
        result.evidence["raw_as"] = data.get("as")
        return result
