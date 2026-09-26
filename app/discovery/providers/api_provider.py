"""Pulls proxies from a JSON API. Optional auth header (from settings, never
logged) and a dotted records_key to find the list inside the response.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from app.core.enums import Protocol, SourceType
from app.core.models import ProxyCandidate
from app.discovery.base import DiscoveryProvider
from app.discovery.normalizer import _endpoint_from_dict, candidate_from_endpoint
from app.proxy.parser import parse_proxy

_MAX_BYTES = 8 * 1024 * 1024


class ApiProvider(DiscoveryProvider):
    source_type = SourceType.API

    def name(self) -> str:
        return self._config.get("name", "api")

    def description(self) -> str:
        return "Fetch proxies from a JSON API with optional authentication."

    def config_schema(self) -> dict[str, Any]:
        return {
            "url": {"type": "url", "label": "API URL", "required": True},
            "auth_header": {"type": "text", "label": "Auth header name (e.g. Authorization)"},
            "auth_value": {"type": "secret", "label": "Auth header value / API key"},
            "records_key": {"type": "text", "label": "Records key (dotted path)"},
            "default_protocol": {"type": "protocol", "label": "Default protocol"},
            "timeout": {"type": "number", "label": "Timeout (s)"},
        }

    def validate_configuration(self) -> tuple[bool, str]:
        url = self._config.get("url", "")
        if not url.startswith(("http://", "https://")):
            return False, "A valid API URL is required"
        return True, "OK"

    async def discover(self) -> AsyncIterator[ProxyCandidate]:
        import httpx

        url = self._config["url"]
        timeout = float(self._config.get("timeout", 20.0))
        default_proto = Protocol.from_value(self._config.get("default_protocol"), Protocol.HTTP)
        source = self._config.get("name") or f"api:{url}"

        headers = {"User-Agent": "ProxyAtlas/1.0", "Accept": "application/json"}
        auth_header = self._config.get("auth_header")
        auth_value = self._config.get("auth_value")
        if auth_header and auth_value:
            headers[auth_header] = auth_value

        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            data = resp.json()

        records = self._locate_records(data, self._config.get("records_key"))
        for rec in records:
            try:
                if isinstance(rec, str):
                    ep = parse_proxy(rec, default_proto)
                elif isinstance(rec, dict):
                    ep = _endpoint_from_dict(rec, default_proto)
                else:
                    continue
            except Exception:  # noqa: BLE001
                continue
            yield candidate_from_endpoint(ep, source)

    @staticmethod
    def _locate_records(data: Any, key: str | None) -> list:
        if key:
            node: Any = data
            for part in key.split("."):
                if isinstance(node, dict):
                    node = node.get(part)
                else:
                    node = None
                    break
            if isinstance(node, list):
                return node
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            for candidate_key in ("proxies", "data", "results", "items"):
                if isinstance(data.get(candidate_key), list):
                    return data[candidate_key]
        return []
