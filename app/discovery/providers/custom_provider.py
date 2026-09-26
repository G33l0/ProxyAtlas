"""Loads a third-party discovery provider: a module (in future_providers/ or
importable) exposing build(config) or a PROVIDER class. Also has an inline
list provider handy for scripts and tests.
"""

from __future__ import annotations

import importlib
import importlib.util
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from app.core.enums import Protocol, SourceType
from app.core.models import ProxyCandidate
from app.discovery.base import DiscoveryProvider
from app.discovery.normalizer import candidate_from_endpoint
from app.proxy.parser import parse_proxy


class CustomListProvider(DiscoveryProvider):
    """Yield candidates from an inline newline/space separated list."""

    source_type = SourceType.CUSTOM

    def name(self) -> str:
        return self._config.get("name", "custom-list")

    def description(self) -> str:
        return "Yield proxies from an inline list (scripting/plugin friendly)."

    def config_schema(self) -> dict[str, Any]:
        return {
            "entries": {"type": "textarea", "label": "Proxy entries (one per line)"},
            "default_protocol": {"type": "protocol", "label": "Default protocol"},
        }

    async def discover(self) -> AsyncIterator[ProxyCandidate]:
        entries = self._config.get("entries") or []
        if isinstance(entries, str):
            entries = entries.splitlines()
        default_proto = Protocol.from_value(self._config.get("default_protocol"), Protocol.HTTP)
        source = self.name()
        for raw in entries:
            raw = str(raw).strip()
            if not raw:
                continue
            try:
                ep = parse_proxy(raw, default_proto)
            except Exception:  # noqa: BLE001
                continue
            yield candidate_from_endpoint(ep, source)


def load_plugin_provider(module_path: str, config: dict[str, Any]) -> DiscoveryProvider:
    """Load a plugin provider from a dotted module name or a .py file path."""
    module = None
    path = Path(module_path)
    if path.suffix == ".py" and path.exists():
        spec = importlib.util.spec_from_file_location(path.stem, path)
        if spec and spec.loader:
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
    else:
        module = importlib.import_module(module_path)

    if module is None:
        raise ImportError(f"Could not load provider plugin: {module_path}")

    if hasattr(module, "build"):
        provider = module.build(config)
    elif hasattr(module, "PROVIDER"):
        provider = module.PROVIDER(config)
    else:
        raise ImportError("Plugin must expose build(config) or PROVIDER class")

    if not isinstance(provider, DiscoveryProvider):
        raise TypeError("Plugin did not return a DiscoveryProvider")
    return provider
