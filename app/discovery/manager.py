"""Discovery manager and provider registry.

Maps provider identifiers to provider classes, builds providers from stored
:class:`ProxySource` configuration, and runs discovery fault-tolerantly: a
single bad record or provider error never aborts the batch. All results funnel
through normalization + dedup and are emitted as candidates for the shared
validation pipeline.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from typing import Any

from app.core.enums import SourceType
from app.core.models import ProxyCandidate
from app.discovery.base import DiscoveryProvider
from app.discovery.deduplicator import dedupe_batch
from app.discovery.providers.api_provider import ApiProvider
from app.discovery.providers.custom_provider import CustomListProvider, load_plugin_provider
from app.discovery.providers.feed_provider import FeedProvider
from app.discovery.providers.file_provider import FileProvider
from app.discovery.providers.internet_provider import InternetDiscoveryProvider

logger = logging.getLogger("proxyatlas.discovery")


PROVIDER_REGISTRY: dict[str, type[DiscoveryProvider]] = {
    "file": FileProvider,
    "feed": FeedProvider,
    "api": ApiProvider,
    "custom": CustomListProvider,
    "internet": InternetDiscoveryProvider,
}


@dataclass
class DiscoveryOutcome:
    candidates: list[ProxyCandidate]
    errors: list[str]
    provider: str


class DiscoveryManager:
    """Builds and runs discovery providers."""

    def __init__(self) -> None:
        self._registry = dict(PROVIDER_REGISTRY)

    def register_provider(self, key: str, cls: type[DiscoveryProvider]) -> None:
        self._registry[key] = cls

    def available_providers(self) -> dict[str, type[DiscoveryProvider]]:
        return dict(self._registry)

    def build(self, provider_key: str, config: dict[str, Any]) -> DiscoveryProvider:
        if provider_key == "plugin":
            module_path = config.get("module", "")
            return load_plugin_provider(module_path, config)
        cls = self._registry.get(provider_key)
        if cls is None:
            raise ValueError(f"Unknown discovery provider: {provider_key}")
        provider = cls(config)
        provider.configure(config)
        return provider

    async def run(
        self,
        provider: DiscoveryProvider,
        on_candidate: Callable[[ProxyCandidate], None] | None = None,
        should_stop: Callable[[], bool] | None = None,
        dedupe: bool = True,
    ) -> DiscoveryOutcome:
        """Run a provider to completion (fault tolerant)."""
        collected: list[ProxyCandidate] = []
        errors: list[str] = []
        ok, msg = provider.validate_configuration()
        if not ok:
            return DiscoveryOutcome([], [f"Configuration invalid: {msg}"], provider.name())

        try:
            async for candidate in provider.discover():
                if should_stop and should_stop():
                    logger.info("Discovery stopped early for %s", provider.name())
                    break
                collected.append(candidate)
                if on_candidate:
                    try:
                        on_candidate(candidate)
                    except Exception:  # noqa: BLE001 - callback isolation
                        logger.exception("on_candidate callback failed")
        except Exception as exc:  # noqa: BLE001 - provider-level failure
            logger.exception("Provider %s failed", provider.name())
            errors.append(f"{provider.name()}: {exc}")

        if dedupe and collected:
            before = len(collected)
            collected = dedupe_batch(collected)
            logger.info(
                "Discovery %s: %d candidates (%d after dedupe)",
                provider.name(), before, len(collected),
            )
        return DiscoveryOutcome(collected, errors, provider.name())

    async def discover_iter(
        self, provider: DiscoveryProvider
    ) -> AsyncIterator[ProxyCandidate]:
        """Yield candidates one at a time (for streaming UIs)."""
        try:
            async for candidate in provider.discover():
                yield candidate
        except Exception:  # noqa: BLE001
            logger.exception("discover_iter failed for %s", provider.name())

    def default_sources(self) -> list[dict[str, Any]]:
        """Seed source definitions offered on first run (all disabled)."""
        return [
            {
                "name": "Local file import",
                "source_type": SourceType.FILE.value,
                "provider": "file",
                "config": {"path": "", "default_protocol": "http"},
                "enabled": False,
            },
            {
                "name": "Custom feed",
                "source_type": SourceType.FEED.value,
                "provider": "feed",
                "config": {"url": "", "format": "auto", "default_protocol": "http"},
                "enabled": False,
            },
            {
                "name": "Internet discovery (example range)",
                "source_type": SourceType.INTERNET.value,
                "provider": "internet",
                "config": {"cidrs": "", "ports": "8080,3128,1080", "max_candidates": 1000},
                "enabled": False,
            },
        ]
