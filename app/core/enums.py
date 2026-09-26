"""Shared enums. Plain str enums so they drop straight into SQLite, JSON,
exports and Qt item-data.
"""

from __future__ import annotations

from enum import Enum


class StrEnum(str, Enum):
    """String enum whose `str()` is the value (Py3.10 compatible)."""

    def __str__(self) -> str:  # pragma: no cover - trivial
        return str(self.value)

    @classmethod
    def from_value(cls, value: object, default: StrEnum | None = None) -> StrEnum | None:
        """Return a member for `value` (case-insensitive) or `default`."""
        if value is None:
            return default
        if isinstance(value, cls):
            return value
        text = str(value).strip().lower()
        for member in cls:
            if member.value.lower() == text or member.name.lower() == text:
                return member
        return default

    @classmethod
    def values(cls) -> list[str]:
        return [m.value for m in cls]


class Protocol(StrEnum):
    """Supported proxy protocols."""

    HTTP = "http"
    HTTPS = "https"
    SOCKS4 = "socks4"
    SOCKS5 = "socks5"


class ValidationStatus(StrEnum):
    """Lifecycle states for a proxy candidate / endpoint."""

    DISCOVERED = "discovered"
    TESTING = "testing"
    WORKING = "working"
    FAILED = "failed"
    TIMEOUT = "timeout"
    AUTH_REQUIRED = "auth_required"
    INVALID = "invalid"
    UNSUPPORTED = "unsupported"
    UNKNOWN = "unknown"


class Classification(StrEnum):
    """Evidence-based proxy classification categories."""

    RESIDENTIAL = "residential"
    MOBILE = "mobile"
    DATACENTER = "datacenter"
    ISP = "isp"
    BUSINESS = "business"
    EDUCATIONAL = "educational"
    GOVERNMENT = "government"
    UNKNOWN = "unknown"


class Anonymity(StrEnum):
    """Observed anonymity level of a proxy."""

    TRANSPARENT = "transparent"
    ANONYMOUS = "anonymous"
    ELITE = "elite"  # highly anonymous
    UNKNOWN = "unknown"


class DnsStatus(StrEnum):
    """Outcome of DNS behaviour analysis."""

    OK = "ok"
    LEAK_SUSPECTED = "leak_suspected"
    MISMATCH = "mismatch"
    UNTESTED = "untested"
    ERROR = "error"


class JobType(StrEnum):
    DISCOVERY = "discovery"
    VALIDATION = "validation"
    INTELLIGENCE = "intelligence"
    MONITORING = "monitoring"
    EXPORT = "export"
    REPORT = "report"


class JobState(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class SourceType(StrEnum):
    FILE = "file"
    FEED = "feed"
    API = "api"
    CUSTOM = "custom"
    INTERNET = "internet"


class ValidationProfileName(StrEnum):
    QUICK = "quick"
    STANDARD = "standard"
    DEEP = "deep"
    CUSTOM = "custom"


class ExportFormat(StrEnum):
    TXT = "txt"
    CSV = "csv"
    JSON = "json"
    HTML = "html"


# Human-friendly labels for UI display.
PROTOCOL_LABELS = {
    Protocol.HTTP: "HTTP",
    Protocol.HTTPS: "HTTPS",
    Protocol.SOCKS4: "SOCKS4",
    Protocol.SOCKS5: "SOCKS5",
}

CLASSIFICATION_LABELS = {
    Classification.RESIDENTIAL: "Residential",
    Classification.MOBILE: "Mobile",
    Classification.DATACENTER: "Datacenter",
    Classification.ISP: "ISP",
    Classification.BUSINESS: "Business",
    Classification.EDUCATIONAL: "Educational",
    Classification.GOVERNMENT: "Government",
    Classification.UNKNOWN: "Unknown",
}

STATUS_LABELS = {
    ValidationStatus.DISCOVERED: "Discovered",
    ValidationStatus.TESTING: "Testing",
    ValidationStatus.WORKING: "Working",
    ValidationStatus.FAILED: "Failed",
    ValidationStatus.TIMEOUT: "Timeout",
    ValidationStatus.AUTH_REQUIRED: "Auth Required",
    ValidationStatus.INVALID: "Invalid",
    ValidationStatus.UNSUPPORTED: "Unsupported",
    ValidationStatus.UNKNOWN: "Unknown",
}
