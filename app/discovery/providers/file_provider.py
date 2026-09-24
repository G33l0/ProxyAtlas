"""File-based discovery provider (TXT / CSV / JSON)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from app.core.enums import Protocol, SourceType
from app.core.models import ProxyCandidate
from app.discovery.base import DiscoveryProvider
from app.discovery.normalizer import normalize_csv, normalize_json, normalize_lines


class FileProvider(DiscoveryProvider):
    source_type = SourceType.FILE

    def name(self) -> str:
        return self._config.get("name", "file")

    def description(self) -> str:
        return "Import proxies from a local TXT, CSV or JSON file."

    def config_schema(self) -> dict[str, Any]:
        return {
            "path": {"type": "path", "label": "File path", "required": True},
            "default_protocol": {"type": "protocol", "label": "Default protocol"},
        }

    def validate_configuration(self) -> tuple[bool, str]:
        path = self._config.get("path")
        if not path:
            return False, "File path is required"
        if not Path(path).expanduser().exists():
            return False, f"File not found: {path}"
        return True, "OK"

    async def discover(self) -> AsyncIterator[ProxyCandidate]:
        path = Path(self._config["path"]).expanduser()
        default_proto = Protocol.from_value(
            self._config.get("default_protocol"), Protocol.HTTP
        )
        source = f"file:{path.name}"
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            raise RuntimeError(f"Cannot read file: {exc}") from exc

        suffix = path.suffix.lower()
        if suffix == ".json":
            candidates, _ = normalize_json(text, source, default_proto)
        elif suffix == ".csv":
            candidates, _ = normalize_csv(text, source, default_proto)
        else:
            candidates, _ = normalize_lines(text.splitlines(), source, default_proto, str(path))

        for cand in candidates:
            yield cand
