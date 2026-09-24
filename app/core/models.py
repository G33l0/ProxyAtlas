"""Lightweight dataclasses that flow through the processing pipeline.

These are transport objects (not ORM rows). They keep the discovery →
validation → intelligence → classification chain decoupled from SQLAlchemy so
each engine can be tested in isolation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from app.core.enums import (
    Anonymity,
    Classification,
    DnsStatus,
    Protocol,
    ValidationStatus,
)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class Endpoint:
    """A normalized proxy endpoint identity."""

    host: str
    port: int
    protocol: Protocol
    username: str | None = None
    password: str | None = None

    @property
    def has_credentials(self) -> bool:
        return bool(self.username)

    @property
    def identity(self) -> str:
        """Stable dedupe key: protocol + host + port (credentials excluded)."""
        return f"{self.protocol.value}://{self.host}:{self.port}"

    def address(self) -> str:
        return f"{self.host}:{self.port}"

    def url(self, include_credentials: bool = True) -> str:
        if include_credentials and self.username:
            auth = self.username
            if self.password:
                auth += f":{self.password}"
            return f"{self.protocol.value}://{auth}@{self.host}:{self.port}"
        return f"{self.protocol.value}://{self.host}:{self.port}"


@dataclass
class ProxyCandidate:
    """A discovered candidate awaiting validation."""

    endpoint: Endpoint
    source: str = "unknown"
    source_reference: str | None = None
    discovered_at: datetime = field(default_factory=utcnow)
    validation_status: ValidationStatus = ValidationStatus.DISCOVERED
    raw: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def identity(self) -> str:
        return self.endpoint.identity


@dataclass
class ValidationResult:
    """Outcome of validating a single proxy."""

    endpoint: Endpoint
    status: ValidationStatus
    connect_time_ms: float | None = None
    response_time_ms: float | None = None
    latency_ms: float | None = None
    exit_ip: str | None = None
    http_success: bool = False
    auth_ok: bool | None = None
    error_category: str | None = None
    error_detail: str | None = None
    anonymity: Anonymity = Anonymity.UNKNOWN
    anonymity_evidence: dict[str, Any] = field(default_factory=dict)
    dns_status: DnsStatus = DnsStatus.UNTESTED
    dns_evidence: dict[str, Any] = field(default_factory=dict)
    validation_endpoint: str | None = None
    samples: int = 1
    successes: int = 0
    tested_at: datetime = field(default_factory=utcnow)
    raw_headers: dict[str, str] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.status == ValidationStatus.WORKING

    @property
    def reliability(self) -> float:
        if self.samples <= 0:
            return 0.0
        return round(100.0 * self.successes / self.samples, 2)


@dataclass
class IntelligenceResult:
    """Network intelligence for an exit IP."""

    ip: str
    country: str | None = None
    country_code: str | None = None
    region: str | None = None
    city: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    timezone: str | None = None
    asn: str | None = None
    isp: str | None = None
    organization: str | None = None
    hosting: bool | None = None
    reverse_dns: str | None = None
    provider: str | None = None
    evidence: dict[str, Any] = field(default_factory=dict)


@dataclass
class ClassificationResult:
    """Evidence-based classification outcome."""

    classification: Classification = Classification.UNKNOWN
    confidence: float = 0.0
    evidence: list[str] = field(default_factory=list)

    def add_evidence(self, note: str) -> None:
        self.evidence.append(note)


@dataclass
class QualityScore:
    """Explainable composite quality score (0-100)."""

    score: float = 0.0
    components: dict[str, float] = field(default_factory=dict)

    def explain(self) -> str:
        parts = [f"{k}: {v:.0f}" for k, v in self.components.items()]
        return f"Score {self.score:.0f} ({', '.join(parts)})"
