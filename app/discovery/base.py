"""Discovery provider interface.

Every discovery source implements :class:`DiscoveryProvider`. Providers yield
:class:`ProxyCandidate` objects that all enter the *same* validation pipeline —
no provider performs its own validation. New providers can be registered with
the manager without modifying the core engine.
"""

from __future__ import annotations

import abc
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

from app.core.enums import SourceType
from app.core.models import ProxyCandidate


@dataclass
class ProviderMetadata:
    name: str
    source_type: SourceType
    description: str = ""
    config_schema: dict[str, Any] = field(default_factory=dict)


class DiscoveryProvider(abc.ABC):
    """Common interface for all discovery providers."""

    source_type: SourceType = SourceType.CUSTOM

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._config: dict[str, Any] = dict(config or {})

    @abc.abstractmethod
    def name(self) -> str:
        ...

    def description(self) -> str:
        return ""

    def configure(self, config: dict[str, Any]) -> None:
        self._config = dict(config or {})

    def validate_configuration(self) -> tuple[bool, str]:
        """Return (ok, message). Override to validate required fields."""
        return True, "OK"

    def metadata(self) -> ProviderMetadata:
        return ProviderMetadata(
            name=self.name(),
            source_type=self.source_type,
            description=self.description(),
            config_schema=self.config_schema(),
        )

    def config_schema(self) -> dict[str, Any]:
        """Describe configurable fields for the UI (field -> {type,label})."""
        return {}

    @abc.abstractmethod
    async def discover(self) -> AsyncIterator[ProxyCandidate]:
        """Yield discovered candidates. Must not raise for individual records."""
        raise NotImplementedError
        yield  # pragma: no cover - marks this an async generator
