"""Feed-based discovery provider.

Fetches proxy data from a configured URL that returns a proxy list (plain text,
CSV or JSON). Responses are treated as untrusted: they are size-capped and
parsed defensively; malformed records are skipped, never executed.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from app.core.enums import Protocol, SourceType
from app.core.models import ProxyCandidate
from app.discovery.base import DiscoveryProvider
from app.discovery.normalizer import normalize_csv, normalize_json, normalize_lines

_MAX_BYTES = 8 * 1024 * 1024  # 8 MB cap on a feed response


class FeedProvider(DiscoveryProvider):
    source_type = SourceType.FEED

    def name(self) -> str:
        return self._config.get("name", "feed")

    def description(self) -> str:
        return "Fetch a proxy list from a configurable feed URL."

    def config_schema(self) -> dict[str, Any]:
        return {
            "url": {"type": "url", "label": "Feed URL", "required": True},
            "format": {"type": "choice", "label": "Format", "choices": ["auto", "txt", "csv", "json"]},
            "default_protocol": {"type": "protocol", "label": "Default protocol"},
            "timeout": {"type": "number", "label": "Timeout (s)"},
        }

    def validate_configuration(self) -> tuple[bool, str]:
        url = self._config.get("url", "")
        if not url:
            return False, "Feed URL is required"
        if not (url.startswith("http://") or url.startswith("https://")):
            return False, "URL must start with http:// or https://"
        return True, "OK"

    async def discover(self) -> AsyncIterator[ProxyCandidate]:
        import httpx

        url = self._config["url"]
        timeout = float(self._config.get("timeout", 20.0))
        default_proto = Protocol.from_value(self._config.get("default_protocol"), Protocol.HTTP)
        fmt = (self._config.get("format") or "auto").lower()
        source = self._config.get("name") or f"feed:{url}"

        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            resp = await client.get(url, headers={"User-Agent": "ProxyAtlas/1.0"})
            resp.raise_for_status()
            content = resp.content[:_MAX_BYTES]
            text = content.decode("utf-8", errors="replace")

        content_type = resp.headers.get("content-type", "").lower()
        if fmt == "json" or (fmt == "auto" and "json" in content_type):
            candidates, _ = normalize_json(text, source, default_proto)
        elif fmt == "csv" or (fmt == "auto" and ("csv" in content_type or "," in text.splitlines()[0:1] and False)):
            candidates, _ = normalize_csv(text, source, default_proto)
        else:
            candidates, _ = normalize_lines(text.splitlines(), source, default_proto, url)

        for cand in candidates:
            yield cand
