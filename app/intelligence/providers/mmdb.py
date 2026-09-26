"""Offline GeoIP intelligence provider backed by MaxMind/DB-IP ``.mmdb`` files.

Uses local MMDB databases (GeoLite2-City / GeoLite2-Country and GeoLite2-ASN, or
the equivalent DB-IP Lite files) so geolocation, ASN and ISP resolution work
without any network calls or rate limits. ProxyAtlas does not bundle these
licensed databases — the user supplies the file paths under
Settings → Providers. When ``geoip2`` is not installed or no database is
configured, the provider simply returns an empty result and the pipeline falls
back to the online providers.

Runs at the highest priority so, when present, it answers first and the network
providers only fill any gaps.
"""

from __future__ import annotations

import logging
from typing import Any

from app.core.models import IntelligenceResult
from app.intelligence.asn import normalize_asn
from app.intelligence.base import IntelligenceProvider
from app.intelligence.geoip import country_name, is_private_or_reserved
from app.intelligence.isp import clean_org

logger = logging.getLogger(__name__)


class MmdbProvider(IntelligenceProvider):
    kind = "geoip"
    priority = 10  # offline-first: runs before network providers

    def __init__(self) -> None:
        self._config: dict[str, Any] = {}
        self._city_reader = None
        self._asn_reader = None
        self._available = False
        self._loaded = False

    def name(self) -> str:
        return "mmdb"

    def description(self) -> str:
        return "Offline MaxMind/DB-IP GeoIP database lookup (no network, no rate limits)."

    def configure(self, config: dict[str, Any]) -> None:
        self._config = dict(config or {})
        self._loaded = False  # force reload on next lookup
        self._close()

    def validate_configuration(self) -> tuple[bool, str]:
        city = self._config.get("city_db") or self._config.get("country_db")
        asn = self._config.get("asn_db")
        if not city and not asn:
            return True, "No offline database configured (optional)."
        try:
            import geoip2.database  # noqa: F401
        except ImportError:
            return False, "geoip2 is not installed (pip install geoip2)."
        from pathlib import Path

        for label, path in (("city/country", city), ("asn", asn)):
            if path and not Path(path).expanduser().exists():
                return False, f"{label} database not found: {path}"
        return True, "Offline GeoIP database ready."

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        city = self._config.get("city_db") or self._config.get("country_db")
        asn = self._config.get("asn_db")
        if not city and not asn:
            return
        try:
            import geoip2.database
        except ImportError:
            logger.info("geoip2 not installed; offline GeoIP disabled")
            return
        from pathlib import Path

        try:
            if city and Path(city).expanduser().exists():
                self._city_reader = geoip2.database.Reader(str(Path(city).expanduser()))
            if asn and Path(asn).expanduser().exists():
                self._asn_reader = geoip2.database.Reader(str(Path(asn).expanduser()))
            self._available = bool(self._city_reader or self._asn_reader)
        except Exception as exc:  # noqa: BLE001 - bad file, wrong format, etc.
            logger.warning("Failed to open MMDB database: %s", exc)
            self._available = False

    async def lookup(self, ip: str) -> IntelligenceResult:
        result = IntelligenceResult(ip=ip, provider=self.name())
        if not ip or is_private_or_reserved(ip):
            return result
        self._ensure_loaded()
        if not self._available:
            return result

        if self._city_reader is not None:
            try:
                self._read_city(ip, result)
            except Exception:  # noqa: BLE001 - address not in DB / lookup error
                pass
        if self._asn_reader is not None:
            try:
                self._read_asn(ip, result)
            except Exception:  # noqa: BLE001
                pass
        return result

    def _read_city(self, ip: str, result: IntelligenceResult) -> None:
        import geoip2.errors

        try:
            # Works for both City and Country databases (city() tolerates both on
            # newer readers; fall back to country() otherwise).
            try:
                rec = self._city_reader.city(ip)
                result.city = rec.city.name or None
                if rec.location:
                    result.latitude = rec.location.latitude
                    result.longitude = rec.location.longitude
                    result.timezone = rec.location.time_zone
                if rec.subdivisions and rec.subdivisions.most_specific:
                    result.region = rec.subdivisions.most_specific.name
            except (ValueError, AttributeError):
                rec = self._city_reader.country(ip)
            result.country_code = rec.country.iso_code or None
            result.country = rec.country.name or country_name(result.country_code)
        except geoip2.errors.AddressNotFoundError:
            return

    def _read_asn(self, ip: str, result: IntelligenceResult) -> None:
        import geoip2.errors

        try:
            rec = self._asn_reader.asn(ip)
        except geoip2.errors.AddressNotFoundError:
            return
        org = clean_org(rec.autonomous_system_organization)
        if rec.autonomous_system_number:
            result.asn = normalize_asn(f"AS{rec.autonomous_system_number}")
        result.organization = result.organization or org
        result.isp = result.isp or org

    def _close(self) -> None:
        for reader in (self._city_reader, self._asn_reader):
            try:
                if reader is not None:
                    reader.close()
            except Exception:  # noqa: BLE001
                pass
        self._city_reader = None
        self._asn_reader = None
        self._available = False
