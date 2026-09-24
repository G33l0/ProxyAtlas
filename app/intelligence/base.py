"""Interfaces for IP intelligence providers.

Every provider implements :class:`IntelligenceProvider`. The manager runs them
in priority order and merges non-empty fields, so a provider failure never
stops the pipeline.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass
from typing import Any

from app.core.models import IntelligenceResult


@dataclass
class ProviderStatus:
    name: str
    kind: str
    enabled: bool = True
    last_success: str | None = None
    last_error: str | None = None
    configured: bool = True


class IntelligenceProvider(abc.ABC):
    """Common interface for all intelligence providers."""

    kind: str = "intelligence"
    priority: int = 100  # lower runs first

    @abc.abstractmethod
    def name(self) -> str:
        ...

    def description(self) -> str:
        return ""

    def configure(self, config: dict[str, Any]) -> None:
        """Apply provider configuration (API keys etc.)."""
        self._config = dict(config or {})

    def validate_configuration(self) -> tuple[bool, str]:
        return True, "OK"

    def metadata(self) -> dict[str, Any]:
        return {"name": self.name(), "kind": self.kind, "priority": self.priority}

    @abc.abstractmethod
    async def lookup(self, ip: str) -> IntelligenceResult:
        """Return intelligence for ``ip``. Should not raise on lookup failure."""
        ...
